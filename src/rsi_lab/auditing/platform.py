"""Evidence and admission contracts for independently supplied safety methods.

No learned safety method is enabled by this package.
"""
from dataclasses import dataclass
import math
from rsi_lab.api import UpdateIdentity
from rsi_lab.contracts import CandidateOrigin, Partition, StrictRecord, require_count, require_id, require_sha
from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest


def _bounded(value: float, low=0.0, high=1.0):
    if not math.isfinite(value) or not low <= value <= high:
        raise ValidationError(f"Expected finite value in [{low}, {high}]")


@dataclass(frozen=True)
class UpdateBinding(StrictRecord):
    update_id: str
    root_id: str
    history_group_id: str
    state_sha256: str
    old_mechanism_sha256: str
    new_mechanism_sha256: str
    protocol_sha256: str
    component: str
    partition: Partition
    origin: CandidateOrigin
    horizon: int
    schema_version: int = 1

    def validate(self):
        for value in (self.update_id, self.root_id, self.history_group_id):
            require_id(value)
        for value in (self.state_sha256, self.old_mechanism_sha256,
                      self.new_mechanism_sha256, self.protocol_sha256):
            require_sha(value)
        if self.component not in ("q", "v", "agent"):
            raise ValidationError("Unknown updated component")
        require_count(self.horizon, "horizon", 1)


@dataclass(frozen=True)
class RiskPrediction(StrictRecord):
    binding: UpdateBinding
    model_sha256: str
    old_risk: float
    new_risk: float
    old_utility: float
    new_utility: float
    calibration_radius: tuple[float, ...]
    calibrated: bool
    calibration_roots: int
    in_scope: bool
    schema_version: int = 1

    def validate(self):
        require_sha(self.model_sha256)
        for value in (self.old_risk, self.new_risk, self.old_utility, self.new_utility):
            _bounded(value)
        if len(self.calibration_radius) != 4:
            raise ValidationError("Four prediction heads require four error radii")
        for radius in self.calibration_radius:
            _bounded(radius)
        require_count(self.calibration_roots, "calibration_roots")
        if self.calibrated != (self.calibration_roots > 0):
            raise ValidationError("Calibration status disagrees with held-out roots")

    @property
    def delta_risk(self):
        return self.new_risk - self.old_risk

    @property
    def delta_utility(self):
        return self.new_utility - self.old_utility


@dataclass(frozen=True)
class ProbeOption(StrictRecord):
    plan_id: str
    description: str
    keywords: tuple[str, ...] = ()
    schema_version: int = 1

    def validate(self):
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
        require_sha(self.evidence_sha256)
        if self.prediction and self.prediction.binding != _prediction_binding(self.identity, self.prediction.binding.component):
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
        require_sha(self.report_sha256)
        if self.disposition not in ("accept", "reject", "inconclusive"):
            raise ValidationError("Unknown admission disposition")


def _prediction_binding(identity, component):
    """Bind an optional prediction to the complete platform update identity.

    The environment is included in state_sha256; both entire system snapshots
    (including inherited memory/optimizer state) bind old/new mechanisms here.
    """
    return UpdateBinding(identity.update_id, identity.root_id, identity.history_group_id,
                         digest({"system": identity.base_sha256, "environment": identity.environment_sha256,
                                 "task_plan": identity.task_plan_sha256}),
                         identity.base_sha256, identity.candidate_sha256, identity.protocol_sha256,
                         component, identity.partition, identity.origin, identity.horizon)
