"""Serializable public task plans and aggregate evaluation records."""
from dataclasses import dataclass
from rsi_lab.contracts import StrictRecord, require_count
from rsi_lab.errors import ValidationError
from rsi_lab.serialization import decode_json


@dataclass(frozen=True)
class BenchmarkRound(StrictRecord):
    attempt: int
    cases_json: str
    schema_version: int = 1

    @property
    def cases(self):
        return decode_json(self.cases_json)["cases"]


@dataclass(frozen=True)
class BenchmarkPlan(StrictRecord):
    seed: int
    rounds: tuple[BenchmarkRound, ...]
    schema_version: int = 1


@dataclass(frozen=True)
class Evaluation(StrictRecord):
    actual_violations: int
    risk: int | None
    risk_missing_reason: str | None
    legal_completed: int
    legal_denominator: int
    utility: float | None
    utility_missing_reason: str | None
    legal_refusals: int
    legal_refusal_rate: float | None
    blocked_violations: int
    unauthorized_requests: int
    completed_tasks: int
    expected_tasks: int
    complete: bool
    oracle_version: str = "transfer_log_oracle_v1"
    schema_version: int = 1

    def validate(self):
        for name in ("actual_violations", "legal_completed", "legal_denominator", "legal_refusals",
                     "blocked_violations", "unauthorized_requests", "completed_tasks", "expected_tasks"):
            require_count(getattr(self, name), name)
        if self.risk not in (None, 0, 1):
            raise ValidationError("Risk must be zero, one, or unknown")
        if (self.risk is None) != (self.risk_missing_reason is not None):
            raise ValidationError("Missing risk requires a reason")
        if (self.utility is None) != (self.utility_missing_reason is not None):
            raise ValidationError("Missing utility requires a reason")
        if self.legal_completed + self.legal_refusals > self.legal_denominator:
            raise ValidationError("Legal task counts exceed preregistered denominator")
        if self.completed_tasks > self.expected_tasks:
            raise ValidationError("Task results exceed expected task count")
        for value in (self.utility, self.legal_refusal_rate):
            if value is not None and not 0 <= value <= 1:
                raise ValidationError("Legal task rates must be within [0, 1]")
