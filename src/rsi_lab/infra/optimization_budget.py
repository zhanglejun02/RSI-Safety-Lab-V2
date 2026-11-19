"""Root-local search and review caps charged from existing provider journals.

There is no second reservation ledger: under a short root-local lock, admission
checks the live journals and the provider commits its own pending request. A
crash therefore leaves either no request or its original durable reservation.
Independent audit and final evaluation providers cannot attach to this budget.
"""
from contextlib import closing, contextmanager
import fcntl
from pathlib import Path
import sqlite3

from rsi_lab.errors import BudgetExceeded, ConflictError, ValidationError
from rsi_lab.infra.artifacts import _checked_path
from rsi_lab.infra.chat_models import DurableChatProvider
from rsi_lab.infra.records import save_record


PROTOCOL = "root-optimization-budget-v1"
JOURNALS = ("train.sqlite", "editor.sqlite", "train-judge/judge.sqlite",
            "review/actor.sqlite", "review/judge.sqlite")


def validate_optimization_spec(spec):
    if (type(spec) is not dict or set(spec) != {"max_calls", "max_total_tokens"}
            or any(type(value) is not int or value < 1 for value in spec.values())):
        raise ValidationError("Optimization budget requires positive max_calls and max_total_tokens")
    return dict(spec)


class OptimizationBudget:
    def __init__(self, directory, spec):
        self.root = _checked_path(Path(directory)).resolve()
        self.spec = validate_optimization_spec(spec)
        self.root.mkdir(parents=True, exist_ok=True)
        save_record(self.root / "optimization-budget.json",
                    {"protocol": PROTOCOL, "caps": self.spec, "journals": JOURNALS})

    def attach(self, provider):
        if not isinstance(provider, DurableChatProvider):
            raise ValidationError("Optimization budgets require a durable provider")
        path = _checked_path(provider.path).resolve()
        if path not in {self.root / name for name in JOURNALS}:
            raise ValidationError("Provider journal is outside the declared optimization phases")
        previous = getattr(provider, "optimization_budget", None)
        if previous is not None and (previous.root != self.root or previous.spec != self.spec):
            raise ConflictError("Provider already belongs to another optimization budget")
        provider.optimization_budget = self
        return provider

    @contextmanager
    def admission(self):
        """Serialize only the budget check and durable provider reservation."""
        with _checked_path(self.root / "optimization-budget.lock").open("ab") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)

    def _totals(self, *, current_path=None, current_stats=None):
        totals = {"dispatched_calls": 0, "actual_total_tokens": 0,
                  "reserved_tokens": 0, "budget_overrun": False}
        for name in JOURNALS:
            path = _checked_path(self.root / name)
            if current_path is not None and path == current_path:
                stats = current_stats
            elif path.exists():
                with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
                    db.row_factory = sqlite3.Row
                    stats = DurableChatProvider._budget_usage(db)
            else:
                continue
            for field in ("dispatched_calls", "actual_total_tokens", "reserved_tokens"):
                totals[field] += stats[field]
            totals["budget_overrun"] |= bool(stats["budget_overrun"])
        return totals

    def check(self, current_path, current_stats, reservation):
        """Called with admission lock held, before inserting a new pending call."""
        totals = self._totals(current_path=Path(current_path).resolve(), current_stats=current_stats)
        if totals["dispatched_calls"] >= self.spec["max_calls"]:
            raise BudgetExceeded("Combined optimization call limit reached before dispatch")
        charged = totals["actual_total_tokens"] + totals["reserved_tokens"]
        if totals["budget_overrun"] or charged + reservation > self.spec["max_total_tokens"]:
            raise BudgetExceeded("Combined optimization token budget cannot cover pre-dispatch reservation")

    def summary(self):
        with self.admission():
            totals = self._totals()
        return {"protocol": PROTOCOL, "caps": dict(self.spec), **totals,
                "charged_tokens": totals["actual_total_tokens"] + totals["reserved_tokens"],
                "scope": "search_and_review_excludes_independent_audit_and_final"}
