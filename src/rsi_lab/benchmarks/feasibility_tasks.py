"""Fixed feasibility composition; existing tasks, explicit effect-label projection.

This is not an official AgentDojo score. Its selected harmful-effect predicates
are evaluated on clean episodes too. Task success and oracle completion are
separate, as required by the effect-scored study and its public review protocol.
"""
from copy import deepcopy

from rsi_lab.benchmarks import agentdojo_suite, scheduling_tasks
from rsi_lab.benchmarks.agentdojo_effects import EffectEpisode
from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest

VERSION = "rsi-feasibility-v1"


class Catalog:
    def __init__(self, settings):
        if type(settings) is not dict or set(settings) != {"scheduling", "agentdojo"}:
            raise ValidationError("Feasibility pack requires explicit scheduling and AgentDojo allocations")
        self.backends = {"scheduling": scheduling_tasks.Catalog(settings["scheduling"]),
                         "agentdojo": agentdojo_suite.Catalog(settings["agentdojo"])}
        self.catalog, self.routes = [], {}
        for name, backend in self.backends.items():
            for source in backend.catalog:
                case = deepcopy(source)
                case.update(task_pack=VERSION, component=name)
                if name == "agentdojo":
                    case.update(family=source["suite"],
                                pair_id=f"agentdojo:{source['suite']}:{source['task_id']}")
                self.catalog.append(case)
                self.routes[digest(case)] = (backend, deepcopy(source))

    def cases(self, partition):
        return deepcopy([c for c in self.catalog if c["partition"] == partition])

    def describe(self):
        # No independent task allocation, goals, or attack contents in editor feedback.
        return {"name": VERSION, "version": VERSION,
                "components": {name: backend.describe() for name, backend in self.backends.items()},
                "labels": "environment_effects;task_success_separate_from_oracle_completion"}

    def _route(self, case):
        try:
            return self.routes[digest(case)]
        except KeyError as exc:
            raise ValidationError("Case differs from frozen feasibility catalog") from exc

    def new_episode(self, case):
        backend, source = self._route(case)
        episode = backend.new_episode(deepcopy(source))
        return NativeEffectEpisode(episode) if case["component"] == "agentdojo" else episode

    def scripted_reply(self, case, history, instructions=""):
        backend, source = self._route(case)
        return backend.scripted_reply(deepcopy(source), history, instructions)


class NativeEffectEpisode(EffectEpisode):
    """Project native state/trace predicates without altering native task execution."""
    def __init__(self, episode):
        super().__init__(episode, projection=VERSION)
