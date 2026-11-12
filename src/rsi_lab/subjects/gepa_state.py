"""JSON-bound GEPA checkpoints; native code owns the pool and search decisions."""
from collections import Counter
from copy import deepcopy
import random

from rsi_lab.agents.program import validate_program
from rsi_lab.errors import IntegrityError
from rsi_lab.serialization import digest, primitive


class Cases:
    def __init__(self, ids):
        self.ids = list(ids)

    def all_ids(self):
        return self.ids

    def fetch(self, ids):
        if set(ids) - set(self.ids):
            raise IntegrityError("GEPA requested a case outside its public catalog")
        return list(ids)

    def __len__(self):
        return len(self.ids)


def _tuples(value):
    return tuple(_tuples(v) for v in value) if isinstance(value, list) else value


def restore(value):
    from gepa.core.state import GEPAState
    state = GEPAState.__new__(GEPAState)
    state.__dict__.update(deepcopy(value))
    if state.frontier_type != "instance" or state.evaluation_cache is not None or state.best_outputs_valset is not None:
        raise IntegrityError("Unsupported GEPA checkpoint configuration")
    for field in ("program_at_pareto_front_valset", "program_at_pareto_front_objectives"):
        setattr(state, field, {k: set(v) for k, v in getattr(state, field).items()})
    if not state.is_consistent():
        raise IntegrityError("Inconsistent GEPA checkpoint")
    for candidate in state.program_candidates:
        if set(candidate) != {"policy"}:
            raise IntegrityError("GEPA retained undeclared components")
        validate_program(candidate["policy"])
    return state


class Search:
    def __init__(self, saved, plan, ids, seed):
        from gepa.strategies.batch_sampler import EpochShuffledBatchSampler
        from gepa.strategies.candidate_selector import ParetoCandidateSelector
        self.plan = digest(plan)
        self.data = Cases(ids)
        self.rng = random.Random(seed)
        self.sampler = EpochShuffledBatchSampler(min(3, len(ids)), self.rng)
        self.selector = ParetoCandidateSelector(self.rng)
        self.state = None
        self.parent = None
        self.proposed = None
        if saved:
            if saved["plan_sha256"] != self.plan:
                raise IntegrityError("GEPA pool belongs to a different public suite")
            self.state = restore(saved["native"])
            if any(set(scores) != set(ids) for scores in self.state.prog_candidate_val_subscores):
                raise IntegrityError("GEPA checkpoint lost per-case scores")
            self.rng.setstate(_tuples(saved["rng"]))
            self.sampler.__dict__.update(deepcopy(saved["sampler"]))
            self.sampler.id_freqs = Counter(self.sampler.id_freqs)

    def prepare(self, directory):
        if self.state is not None:
            # The native loader only reads a checkpoint freshly constructed from
            # validated JSON in a private temp directory, never a supplied pickle.
            self.state.save(str(directory))

    def on_candidate_selected(self, event):
        self.parent = {"index": event["candidate_idx"], "source": event["candidate"]["policy"]}

    def on_proposal_end(self, event):
        self.proposed = event["new_instructions"]["policy"]

    def on_optimization_end(self, event):
        self.state = event["final_state"]

    def export(self):
        native = {k: v for k, v in self.state.__dict__.items() if k != "_budget_hooks"}
        for field in ("program_at_pareto_front_valset", "program_at_pareto_front_objectives"):
            native[field] = {k: sorted(v) for k, v in native[field].items()}
        sampler = {k: dict(v) if isinstance(v, Counter) else v
                   for k, v in self.sampler.__dict__.items() if k != "rng"}
        return primitive({"plan_sha256": self.plan, "native": native,
                          "sampler": sampler, "rng": self.rng.getstate()})
