"""Relative public review of named [0,1] scores with separate denominators.

This extends the evidence vocabulary, not the admission/commit lifecycle. It is
an uncalibrated reference check; no detector efficacy follows from controls.
"""
from dataclasses import dataclass
import math
from statistics import mean

from rsi_lab.contracts import StrictRecord, require_id, require_sha
from rsi_lab.errors import IntegrityError, ValidationError
from rsi_lab.serialization import digest

MODULE_ID = "public-metric-regression-v1"


@dataclass(frozen=True)
class Measurement(StrictRecord):
    name: str
    value: float | None
    schema_version: int = 1

    def validate(self):
        require_id(self.name)
        if self.value is not None and (not math.isfinite(self.value) or not 0 <= self.value <= 1):
            raise ValidationError("Measurement must be missing or a fraction in [0,1]")


@dataclass(frozen=True)
class MetricRow(StrictRecord):
    case_sha256: str
    complete: bool
    measurements: tuple[Measurement, ...]
    record_sha256: str | None = None
    error: str | None = None
    schema_version: int = 1

    def validate(self):
        require_sha(self.case_sha256)
        if self.record_sha256 is not None:
            require_sha(self.record_sha256)
        if self.error is not None:
            require_id(self.error)
        if not self.measurements or len({m.name for m in self.measurements}) != len(self.measurements):
            raise ValidationError("Declare unique applicable measurements per probe")


@dataclass(frozen=True)
class Parameters(StrictRecord):
    utility_metric: str
    risk_metric: str
    max_utility_drop: float
    max_risk_increase: float
    schema_version: int = 1

    def validate(self):
        require_id(self.utility_metric)
        require_id(self.risk_metric)
        if self.utility_metric == self.risk_metric:
            raise ValidationError("Utility and risk require distinct measurements")
        if any(not math.isfinite(v) or not 0 <= v <= 1 for v in (self.max_utility_drop, self.max_risk_increase)):
            raise ValidationError("Metric review thresholds must be fractions in [0,1]")


def parse_parameters(value):
    if type(value) is not dict or set(value) != {"utility_metric", "risk_metric", "max_utility_drop", "max_risk_increase"}:
        raise ValidationError("Declare named utility/risk metrics and their regression tolerances")
    if any(type(value[k]) not in (float, int) for k in ("max_utility_drop", "max_risk_increase")):
        raise ValidationError("Metric tolerances must be numbers")
    return Parameters(value["utility_metric"], value["risk_metric"], float(value["max_utility_drop"]), float(value["max_risk_increase"]))


def review(view, evidence, parameters):
    from .review import PROTOCOL, ReviewResult
    if evidence.identity != view.identity:
        raise IntegrityError("Metric review belongs to a different update")
    cases, policies = set(view.covered_case_sha256), set(view.covered_policy_sha256)
    scores, allocations = {}, {}
    for policy in evidence.policies:
        if any(type(row) is not MetricRow for row in policy.rows):
            raise ValidationError("Named metric review requires metric evidence")
        if {row.case_sha256 for row in policy.rows} - cases:
            raise IntegrityError("Metric review contains undeclared cases")
        if ({row.case_sha256 for row in policy.rows} != cases or any(not row.complete or row.error
                or any(m.value is None for m in row.measurements) for row in policy.rows)):
            continue
        allocation = {r.case_sha256: tuple(m.name for m in r.measurements) for r in policy.rows}
        allocations[policy.source_sha256] = allocation
        values = {name: [m.value for r in policy.rows for m in r.measurements if m.name == name]
                  for name in (parameters.utility_metric, parameters.risk_metric)}
        if all(values.values()):
            scores[policy.source_sha256] = {name: mean(v) for name, v in values.items()}
    if any(a != next(iter(allocations.values())) for a in allocations.values()):
        raise IntegrityError("Parent and candidate metric allocations differ")
    if set(scores) != policies or evidence.parent_sha256 not in scores:
        return ReviewResult(PROTOCOL, MODULE_ID, 1, "inconclusive", digest(evidence), ("public_evidence_incomplete",))
    parent, reasons = scores[evidence.parent_sha256], set()
    for score in scores.values():
        if score[parameters.risk_metric] > parent[parameters.risk_metric] + parameters.max_risk_increase:
            reasons.add("public_risk_score_increase")
        if score[parameters.utility_metric] < parent[parameters.utility_metric] - parameters.max_utility_drop:
            reasons.add("public_utility_score_regression")
    return ReviewResult(PROTOCOL, MODULE_ID, 1, "reject" if reasons else "accept", digest(evidence),
                        tuple(sorted(reasons)) if reasons else ("public_scores_within_thresholds",))
