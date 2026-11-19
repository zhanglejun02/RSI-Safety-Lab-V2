"""Discovery and source identity for explicitly installed, trusted method packages."""
from importlib import import_module, metadata
from pathlib import Path
import re
import hashlib

from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.sdk import MethodPlugin, SDK_VERSION
from rsi_lab.serialization import digest

PLUGINS, ENTRIES = {}, {}


def discover(reserved_names, reserved_systems):
    for entry in sorted(metadata.entry_points(group="rsi_lab.methods"), key=lambda e: e.name):
        plugin = entry.load()
        if (not isinstance(plugin, MethodPlugin) or plugin.sdk_version != SDK_VERSION
                or plugin.name != entry.name or not re.fullmatch(r"[a-z][a-z0-9_]*", plugin.name)
                or plugin.name in reserved_names or plugin.name in PLUGINS
                or not plugin.system_id or plugin.system_id in reserved_systems
                or plugin.system_id in {p.system_id for p in PLUGINS.values()}):
            raise ValidationError("Invalid, incompatible or duplicate method entry point: " + entry.name)
        if (not plugin.revision or not plugin.scope or not isinstance(plugin.adapter, type)
                or any(not callable(f) for f in (plugin.initial_snapshot, plugin.state_view, plugin.scripted_reply))
                or plugin.editor_response_format not in ("json_object", "text")
                or not plugin.platforms or set(plugin.platforms) - {"Darwin", "Linux"}):
            raise ValidationError("Incomplete method plugin: " + entry.name)
        declaration = plugin.capabilities
        if (type(declaration) is not dict or set(declaration) != {"mutable_state", "observations", "interventions", "limits"}
                or any(type(v) is not list or any(type(x) is not str for x in v) or len(set(v)) != len(v)
                       for v in declaration.values())
                or set(declaration["observations"]) - {"process_events", "deployed_policy", "retained_policies"}
                or set(declaration["interventions"]) - {"candidate_review", "random_reject", "observe_only"}):
            raise ValidationError("Invalid method plugin capability declaration: " + entry.name)
        PLUGINS[plugin.name], ENTRIES[plugin.name] = plugin, entry
    return PLUGINS


def source_files(names):
    """Archive regular Python extension packages and their discovery metadata."""
    files = {}
    selected = set(names) & PLUGINS.keys()
    distributions = set()
    for name in selected:
        entry = ENTRIES[name]
        if entry.dist is None:
            raise ValidationError("Method entry point lacks installed distribution metadata")
        distributions.add(entry.dist.metadata["Name"])
    # Restored metadata discovers every method from a distribution, even when a
    # run selected only one. Keep all of those method packages importable.
    selected = {name for name, entry in ENTRIES.items()
                if entry.dist is not None and entry.dist.metadata["Name"] in distributions}
    for name in sorted(selected):
        entry = ENTRIES[name]
        package = entry.value.split(":", 1)[0].split(".", 1)[0]
        module = import_module(package)
        if (package == "rsi_lab" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", package)
                or not getattr(module, "__file__", None) or Path(module.__file__).name != "__init__.py"):
            raise ValidationError("Method entry points require a separate regular Python package")
        root = Path(module.__file__).resolve().parent
        selected = [(package + "/" + p.relative_to(root).as_posix(), p) for p in root.rglob("*")
                    if p.is_file() and p.suffix in (".py", ".json", ".md", ".txt") and "__pycache__" not in p.parts]
        selected += [(str(p), Path(entry.dist.locate_file(p))) for p in entry.dist.files or ()
                     if len(p.parts) == 2 and p.parts[0].endswith(".dist-info")
                     and p.name in ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD")]
        if not any(key.endswith("/entry_points.txt") for key, _ in selected):
            raise ValidationError("Method package lacks archivable entry-point metadata")
        for key, path in selected:
            if path.is_symlink() or ".." in Path(key).parts:
                raise IntegrityError("Method sources must be regular package files")
            raw = path.read_bytes()
            if key in files and files[key] != raw:
                raise IntegrityError("Method packages collide in frozen source archive")
            files[key] = raw
    return files


def bindings(names):
    result = {}
    for name in sorted(set(names) & PLUGINS.keys()):
        plugin, entry = PLUGINS[name], ENTRIES[name]
        hashes = {key: hashlib.sha256(raw).hexdigest() for key, raw in source_files([name]).items()}
        result[name] = {"sdk_version": SDK_VERSION, "system_id": plugin.system_id,
                        "revision": plugin.revision, "entry_point": entry.value,
                        "distribution": entry.dist.metadata["Name"], "version": entry.dist.version,
                        "files": hashes, "source_sha256": digest(hashes)}
    return result
