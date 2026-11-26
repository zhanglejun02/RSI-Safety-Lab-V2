"""Native AgentDojo tasks with explicit, independent task and effect labels.

The selected attacker-goal predicate is also evaluated on clean episodes. This
is a declared derived metric, not AgentDojo's native null clean security label.
"""
from copy import deepcopy

from rsi_lab.benchmarks.agentdojo_suite import Catalog as NativeCatalog
from rsi_lab.errors import ValidationError
from rsi_lab.serialization import digest

VERSION = "agentdojo-effects-v1"


class Catalog:
    def __init__(self, settings):
        self.native = NativeCatalog(settings)
        self.catalog, self.routes = [], {}
        for source in self.native.catalog:
            case = {**deepcopy(source), "task_pack": VERSION, "family": source["suite"],
                    "pair_id": f"agentdojo:{source['suite']}:{source['task_id']}"}
            self.catalog.append(case)
            self.routes[digest(case)] = source

    def cases(self, partition):
        return deepcopy([c for c in self.catalog if c["partition"] == partition])

    def describe(self):
        return {**self.native.describe(), "version": VERSION,
                "labels": "native_task_utility_and_selected_harmful_effect;clean_effects_measured"}

    def _source(self, case):
        try:
            return deepcopy(self.routes[digest(case)])
        except KeyError as exc:
            raise ValidationError("Case differs from frozen AgentDojo effect catalog") from exc

    def new_episode(self, case):
        return EffectEpisode(self.native.new_episode(self._source(case)))

    def scripted_reply(self, case, history, instructions=""):
        return self.native.scripted_reply(self._source(case), history, instructions)


class EffectEpisode:
    def __init__(self, episode, *, projection=VERSION):
        self.episode, self.projection = episode, projection

    def __getattr__(self, name):
        return getattr(self.episode, name)

    def finish(self, final_text):
        episode = self.episode
        result = episode.finish(final_text)
        if result["security"] is None:
            bad = bool(episode._suite._check_task_result(
                episode._injection, [{"type": "text", "content": final_text}],
                episode._before, episode._world, episode._trace))
            result.update(security=not bad, attack_success=bad)
        result.update(complete=True, task_success=bool(result["utility"]),
                      effect_projection=self.projection,
                      safety_scope="selected_native_harmful_effect_on_clean_and_attacked_episodes")
        return result
