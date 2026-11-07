"""Evidence and admission contracts for independently supplied safety methods.

No learned safety method is enabled by this package.
"""
from dataclasses import dataclass
from typing import Protocol
from rsi_lab.api import UpdateIdentity
from rsi_lab.contracts import StrictRecord
from rsi_lab.errors import ValidationError
from rsi_lab.learning.contracts import RoundOutcome, RiskPrediction, UpdateBinding
from rsi_lab.serialization import digest

@dataclass(frozen=True)
class ProbeOption(StrictRecord):
    plan_id: str
    description: str
    keywords: tuple[str, ...] = ()
    schema_version: int = 1

    def validate(self):
        from rsi_lab.contracts import require_id
        require_id(self.plan_id)



@dataclass(frozen=True)
class AuditView(StrictRecord):
    identity: UpdateIdentity
    diff_text: str
    state_summary: str
    native_valid: bool
    semantic_component: str | None
    no_op: bool
    probe_options: tuple[ProbeOption, ...] = ()
    schema_version: int = 1

    def validate(self):
        if len(self.diff_text.encode()) > 65536 or len(self.state_summary.encode()) > 32768:
            raise ValidationError("Audit text projection exceeds limits")
        if self.semantic_component not in (None, "q", "v", "agent"):
            raise ValidationError("Unsupported semantic role")



@dataclass(frozen=True)
class ProbeRequest(StrictRecord):
    plan_id: str
    horizon: int
    schema_version: int = 1

    def validate(self):
        from rsi_lab.contracts import require_id
        require_id(self.plan_id)
        if not 1 <= self.horizon <= 2:
            raise ValidationError("Probe outside registered short-horizon allowance")



@dataclass(frozen=True)
class ProbeEvidence(StrictRecord):
    identity: UpdateIdentity
    request: ProbeRequest
    outcomes: tuple[RoundOutcome, ...]
    synthetic_units: float
    stream_id: str
    schema_version: int = 1

    def validate(self):
        from rsi_lab.learning.contracts import validate_grid
        validate_grid(self.outcomes, 1, self.request.horizon)
        if self.synthetic_units < 0:
            raise ValidationError("Invalid probe cost")



@dataclass(frozen=True)
class DetectionReport(StrictRecord):
    identity: UpdateIdentity
    detector_id: str
    evidence_sha256: str
    observed_harm: bool
    complete: bool
    coverage_supported: bool
    findings: tuple[str, ...]
    prediction: RiskPrediction | None = None
    schema_version: int = 1

    def validate(self):
        from rsi_lab.learning.contracts import require_sha
        require_sha(self.evidence_sha256)
        if self.prediction and self.prediction.binding != learning_binding(self.identity, self.prediction.binding.component):
            raise ValidationError("Prediction belongs to another update")



@dataclass(frozen=True)
class AdmissionDecision(StrictRecord):
    identity: UpdateIdentity
    report_sha256: str
    policy_id: str
    disposition: str
    reason: str
    schema_version: int = 1

    def validate(self):
        from rsi_lab.learning.contracts import require_sha
        require_sha(self.report_sha256)
        if self.disposition not in ("accept", "reject", "inconclusive"):
            raise ValidationError("Unknown admission disposition")



class ProbeAccess(Protocol):
    def run(self, request: ProbeRequest) -> ProbeEvidence: ...



def learning_binding(identity, component):
    """Explicit platform-v1 projection, never equivalent to frozen P0 bindings.

    The environment is included in state_sha256; both entire system snapshots
    (including inherited memory/optimizer state) bind old/new mechanisms here.
    """
    return UpdateBinding(identity.update_id, identity.root_id, identity.history_group_id,
                         digest({"system": identity.base_sha256, "environment": identity.environment_sha256,
                                 "task_plan": identity.task_plan_sha256}),
                         identity.base_sha256, identity.candidate_sha256, identity.protocol_sha256,
                         component, identity.partition, identity.origin, identity.horizon)

