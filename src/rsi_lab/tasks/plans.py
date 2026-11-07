"""Serializable opaque public task rounds shared by benchmark environments."""
from dataclasses import dataclass
from rsi_lab.contracts import StrictRecord
from rsi_lab.serialization import decode_json

@dataclass(frozen=True)
class BenchmarkRound(StrictRecord):
    attempt: int
    cases_json: str
    schema_version: int = 1

    @property
    def cases(self):
        from rsi_lab.serialization import decode_json
        return decode_json(self.cases_json)["cases"]



@dataclass(frozen=True)
class BenchmarkPlan(StrictRecord):
    seed: int
    rounds: tuple[BenchmarkRound, ...]
    schema_version: int = 1

