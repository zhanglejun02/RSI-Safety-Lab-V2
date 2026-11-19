"""Archive old experiments without changing their contents or following links."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile


def sha256(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def inventory(root, paths, *, hashes=False):
    """Only metadata and optional content hashes; symlink targets are never read."""
    records = {}

    def visit(path):
        info = path.lstat()
        name = path.relative_to(root).as_posix()
        if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
            raise ValueError(f"Credential-like file must be handled separately: {name}")
        row = {"mode": stat.S_IMODE(info.st_mode), "mtime_ns": info.st_mtime_ns}
        if stat.S_ISLNK(info.st_mode):
            row.update(type="symlink", target=os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            row.update(type="file", size=info.st_size)
            if hashes:
                with path.open("rb") as stream:
                    row["sha256"] = sha256(stream)
        elif stat.S_ISDIR(info.st_mode):
            row["type"] = "directory"
        else:
            raise ValueError(f"Refusing special file: {name}")
        records[name] = row
        if row["type"] == "directory":
            for child in sorted(path.iterdir()):
                visit(child)

    for path in paths:
        visit(path)
    return records


def check_idle():
    listing = subprocess.run(["ps", "-axo", "pid=,command="], check=True,
                             text=True, capture_output=True).stdout
    active = []
    for line in listing.splitlines():
        if "archive_experiments" in line:
            continue
        if any(marker in line for marker in ("rsi-lab run", "rsi-lab batch", "rsi_lab.cli run",
                                            "run_natural_experiment.sh")):
            active.append(line.strip())
    if active:
        raise ValueError("Stop experiment writers before archiving: " + "; ".join(active))


def pack(stage, destination, records):
    with tarfile.open(destination, "w:gz", compresslevel=1, dereference=False) as archive:
        for name, row in records.items():
            path = stage / name
            info = archive.gettarinfo(str(path), arcname=name)
            if row["type"] == "file":
                # Store every regular file explicitly, including hard-linked files.
                info.type, info.linkname, info.size = tarfile.REGTYPE, "", row["size"]
                with path.open("rb") as stream:
                    archive.addfile(info, stream)
            else:
                archive.addfile(info)


def verify(archive_path, records):
    seen = set()
    with tarfile.open(archive_path, "r|gz") as archive:
        for member in archive:
            if member.name not in records or member.name in seen:
                raise ValueError(f"Unexpected/duplicate archive member: {member.name}")
            row = records[member.name]
            seen.add(member.name)
            if member.mode != row["mode"]:
                raise ValueError(f"Mode mismatch: {member.name}")
            if row["type"] == "file":
                if not member.isfile() or member.size != row["size"]:
                    raise ValueError(f"File metadata mismatch: {member.name}")
                with archive.extractfile(member) as stream:
                    if sha256(stream) != row["sha256"]:
                        raise ValueError(f"File digest mismatch: {member.name}")
            elif row["type"] == "directory":
                if not member.isdir():
                    raise ValueError(f"Directory mismatch: {member.name}")
            elif not member.issym() or member.linkname != row["target"]:
                raise ValueError(f"Symlink mismatch: {member.name}")
    if seen != records.keys():
        raise ValueError("Archive is missing inventory entries")


def archive_experiments(runs, exports, keep, *, execute=False):
    runs, exports = runs.resolve(), exports.resolve()
    root = runs.parent
    if exports.parent != root or runs.name != "runs" or exports.name != "exports":
        raise ValueError("Expected sibling runs/ and exports/ under the repository")
    paths = sorted(p for p in runs.iterdir() if p.name not in set(keep))
    if exports.exists():
        paths.extend(sorted(exports.iterdir()))
    records = inventory(root, paths)
    summary = {"entries": len(records), "files": sum(r["type"] == "file" for r in records.values()),
               "bytes": sum(r.get("size", 0) for r in records.values()),
               "top_level_paths": [p.relative_to(root).as_posix() for p in paths], "kept_runs": keep}
    if not execute or not paths:
        return summary

    check_idle()
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S%z")
    destination = runs / "archive" / timestamp
    stage = destination / "staging"
    destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "archive-plan.json", summary)
    # Rename, rather than copy: any interruption leaves recoverable originals here.
    for path in paths:
        target = stage / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        path.rename(target)
    staged_paths = [stage / name for name in summary["top_level_paths"]]
    print(f"Hashing {summary['files']} files ({summary['bytes']} bytes)", flush=True)
    hashed = inventory(stage, staged_paths, hashes=True)
    without_hashes = lambda rows: {k: {a: b for a, b in v.items() if a != "sha256"}
                                 for k, v in rows.items()}
    if without_hashes(hashed) != records:
        raise ValueError(f"Inputs changed; originals retained at {stage}")
    write_json(destination / "manifest.json", {"protocol": "rsi-experiment-archive-v1", "files": hashed})
    compressed = destination / "experiments.tar.gz"
    print("Compressing old artifacts", flush=True)
    pack(stage, compressed, hashed)
    print("Verifying every archived file against SHA256 manifest", flush=True)
    verify(compressed, hashed)
    if inventory(stage, staged_paths) != records:
        raise ValueError(f"Inputs changed while archiving; originals retained at {stage}")
    with compressed.open("rb") as stream:
        compressed_sha256 = sha256(stream)
    result = {**summary, "archive": str(compressed), "compressed_bytes": compressed.stat().st_size,
              "sha256": compressed_sha256, "verified": True, "originals_removed": False}
    write_json(destination / "verification.json", result)
    shutil.rmtree(stage)
    result["originals_removed"] = True
    write_json(destination / "verification.json", result)
    (destination / "RESTORE.md").write_text(
        "# Historical experiment archive\n\n"
        "This archive is excluded from the current experimental evidence. All regular files "
        "were SHA256-verified before the originals were removed. Symlinks were stored without "
        "following their targets. No result values were inspected or rewritten.\n\n"
        "Extract into an empty directory to avoid overwriting new experiments:\n\n"
        "```bash\nmkdir -p /tmp/rsi-history-restore\n"
        f"tar -xzf '{compressed}' -C /tmp/rsi-history-restore\n```\n\n"
        "The archive preserves `runs/...` and `exports/...` relative paths. "
        "Shared `runs/vendor` and `runs/datasets` remain in the repository. "
        "Absolute historical paths may need restoring at their original location to resume; "
        "do not merge old and new measurements.\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("plan", "archive"))
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--exports", type=Path, required=True)
    parser.add_argument("--keep", nargs="+", default=["archive", "current", "vendor", "datasets"])
    args = parser.parse_args()
    required = {"archive", "current", "vendor", "datasets"}
    if not required.issubset(args.keep):
        parser.error("archive/current/vendor/datasets must remain excluded")
    print(json.dumps(archive_experiments(args.runs, args.exports, args.keep,
                                        execute=args.mode == "archive"), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
