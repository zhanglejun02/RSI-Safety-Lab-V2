"""Object-level candidate state, distinct from executable policy identity.

These are read-only projections of native IDs and snapshot membership. Source
equality is never a substitute for an unknown object or deployment selection.
"""
from rsi_lab.errors import IntegrityError
from rsi_lab.serialization import decode_json, digest

PROTOCOL = "rsi-candidate-state-v2"


def generated_source(system, evidence):
    source = evidence.get("proposed_source")
    if not isinstance(source, str) and system == "openevolve" and evidence.get("model_receipt"):
        # The native worker can reject a confirmed rewrite before creating an ID.
        from openevolve.utils.code_utils import parse_full_rewrite
        source = parse_full_rewrite(evidence["model_receipt"]["content"]["response"], "python")
    return source if isinstance(source, str) else None


def _object(system, source, evidence):
    if system == "hyperagents":
        return "archive_node", evidence.get("child_id")
    if system == "openevolve":
        return "program", evidence.get("child_id")
    if system == "gepa" and evidence.get("configuration") == "persistent_per_case_pareto":
        # One reflective attempt can append at most one pool entry. A rejected
        # child has no native pool index; identical historical sources don't give it one.
        pool, before = evidence.get("native_pool"), evidence.get("pool_size_before")
        if (evidence.get("native_admitted") is True and isinstance(pool, list)
                and type(before) is int and len(pool) == before + 1
                and pool[before].get("source") == source):
            return "pool_index", before
        return "pool_index", None
    return "unobserved", None


def _membership(snapshot, system, native_id, source, meta_source):
    if snapshot is None or native_id is None:
        return None
    state = decode_json(snapshot.state_json)
    if system == "hyperagents":
        archive = state.get("archive")
        if not isinstance(archive, dict):
            return None
        row = archive.get(native_id)
        if row is None:
            return False
        files = row["files"]
        matches = files["policy.py"] == source and (meta_source is None or files["meta_agent.py"] == meta_source)
    elif system == "openevolve":
        programs = (state.get("population") or {}).get("programs")
        if programs is None:
            # An uninitialized population contains no generated native program.
            return False if "population" in state and state["population"] is None else None
        row = programs.get(native_id)
        if row is None:
            return False
        matches = row["code"] == source
    elif system == "gepa":
        search = state.get("search")
        if search is None:
            return False if "search" in state else None
        pool = search["native"]["program_candidates"]
        if type(native_id) is not int or native_id < 0:
            raise IntegrityError("Invalid GEPA candidate index")
        if native_id >= len(pool):
            return False
        matches = pool[native_id]["policy"] == source
    else:
        return None
    if not matches:
        raise IntegrityError("Native candidate identity refers to different content")
    return True


def candidate_state(system, source, evidence, *, candidate, active, committed):
    """Return policy equality and native-object status, preserving unknowns."""
    from rsi_lab.methods import method_plugin
    plugin = method_plugin(system)
    if plugin:
        from rsi_lab.sdk import candidate_projection
        return candidate_projection(plugin, source, evidence, candidate=candidate, active=active, committed=committed)
    kind, native_id = _object(system, source, evidence)
    meta_source = evidence.get("proposed_meta_source") if system == "hyperagents" else None
    retained = _membership(active, system, native_id, source, meta_source)
    deployed = False if retained is False else None
    state = decode_json(active.state_json)
    if retained is True:
        if system == "hyperagents":
            selected = state.get("active_id")
        elif system == "openevolve":
            selected = state["population"].get("best_program_id")
            if selected is not None:
                program = state["population"]["programs"].get(selected)
                if program is None or program["code"] != active.version.component("policy")["source"]:
                    raise IntegrityError("Native deployment selection differs from active policy")
        else:
            # The pool stores scores, not a deployment index. The current
            # proposal's selection evidence is authoritative only after commit.
            selected = evidence.get("selected_index") if committed else None
            if selected is not None:
                pool = state["search"]["native"]["program_candidates"]
                if (type(selected) is not int or not 0 <= selected < len(pool)
                        or pool[selected]["policy"] != active.version.component("policy")["source"]):
                    raise IntegrityError("GEPA deployment selection differs from active policy")
        if selected is not None:
            deployed = selected == native_id
    policy_matches = source == active.version.component("policy")["source"]
    if deployed is True and not policy_matches:
        raise IntegrityError("Deployed native object differs from active policy")
    return {"native_id": native_id, "identity_kind": kind,
            "object_identity_coverage": "observed" if native_id is not None else "not_observed",
            "meta_source_sha256": digest(meta_source) if meta_source is not None else None,
            "native_child_admitted": evidence.get("native_admitted"),
            "object_in_candidate_snapshot": _membership(candidate, system, native_id, source, meta_source),
            "policy_matches_deployment": policy_matches,
            "object_retained_after": retained, "object_deployed_after": deployed}
