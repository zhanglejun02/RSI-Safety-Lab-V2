"""Trusted installed methods operating on versioned executable Harness resources.

Register a MethodPlugin through the ``rsi_lab.methods`` entry-point group.
Plugins own optimization and state projection; the platform owns task isolation,
review, atomic activation, accounting and independent evaluation.
"""
from dataclasses import dataclass
from typing import Callable

from rsi_lab.api import *
from rsi_lab.agents.runtime import source as policy_source
from rsi_lab.harness import Harness, loads, validate_candidate, validate_update
from rsi_lab.contracts import CandidateOrigin
from rsi_lab.errors import (ValidationError, IntegrityError, OutcomeUnknown,
                            ModelResponseValidationError, UnsupportedCapability)
from rsi_lab.infra.chat_models import ChatMessage
from rsi_lab.infra.records import read_record, save_record
from rsi_lab.serialization import decode_json, digest, json_text
from rsi_lab.subjects.local import LocalSystemAdapter

SDK_VERSION = "rsi-method-sdk-v2"


@dataclass(frozen=True)
class PolicyObject:
    native_id: str | int
    source: str
    meta_source: str | None = None


@dataclass(frozen=True)
class StateView:
    objects: tuple[PolicyObject, ...]
    deployed_id: str | int | None


@dataclass(frozen=True)
class MethodPlugin:
    name: str
    system_id: str
    revision: str
    scope: str
    adapter: type
    initial_snapshot: Callable
    state_view: Callable
    capabilities: dict
    scripted_reply: Callable
    platforms: tuple[str, ...] = ("Darwin", "Linux")
    editor_response_format: str = "json_object"
    sdk_version: str = SDK_VERSION

    def state(self, snapshot):
        if snapshot.version.system_id != self.system_id or snapshot.version.upstream_revision != self.revision:
            raise IntegrityError("Plugin snapshot implementation mismatch")
        view = self.state_view(snapshot)
        if not isinstance(view, StateView) or not isinstance(view.objects, tuple):
            raise ValidationError("Plugin state_view must return a StateView with tuple objects")
        if view.deployed_id is not None and type(view.deployed_id) not in (str, int):
            raise ValidationError("Plugin deployed ID must be a string, integer or unknown")
        ids = []
        for obj in view.objects:
            if (not isinstance(obj, PolicyObject) or type(obj.native_id) not in (str, int)
                    or type(obj.source) is not str or not obj.source
                    or obj.meta_source is not None and type(obj.meta_source) is not str):
                raise ValidationError("Invalid plugin policy object")
            ids.append(obj.native_id)
        if len(ids) != len(set(ids)):
            raise IntegrityError("Plugin state contains duplicate native IDs")
        if view.deployed_id is not None:
            selected = next((o for o in view.objects if o.native_id == view.deployed_id), None)
            if selected is None or selected.source != snapshot.version.component("policy")["source"]:
                raise IntegrityError("Plugin deployment differs from its snapshot")
        return view


def candidate_projection(plugin, source, evidence, *, candidate, active, committed):
    """Check object membership against the plugin's declared state, never source equality."""
    native_id = evidence.get("child_id")
    if native_id is not None and type(native_id) not in (str, int):
        raise ValidationError("Plugin candidate ID must be a string, integer or unknown")
    meta = evidence.get("proposed_meta_source")

    def member(snapshot):
        if snapshot is None or native_id is None:
            return None
        obj = next((o for o in plugin.state(snapshot).objects if o.native_id == native_id), None)
        if obj is None:
            return False
        if obj.source != source or meta is not None and obj.meta_source != meta:
            raise IntegrityError("Plugin candidate ID refers to different content")
        return True

    retained = member(active)
    selected = plugin.state(active).deployed_id
    return {"native_id": native_id, "identity_kind": "plugin_object",
            "object_identity_coverage": "observed" if native_id is not None else "not_observed",
            "meta_source_sha256": digest(meta) if meta is not None else None,
            "native_child_admitted": evidence.get("native_admitted"),
            "object_in_candidate_snapshot": member(candidate),
            "policy_matches_deployment": source == active.version.component("policy")["source"],
            "object_retained_after": retained,
            "object_deployed_after": (False if retained is False else
                                      selected == native_id if retained and selected is not None else None)}
