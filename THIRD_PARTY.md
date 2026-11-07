# Third-party sources

| Component | Source / revision | Integration |
|---|---|---|
| AgentDojo | [ethz-spylab/agentdojo](https://github.com/ethz-spylab/agentdojo), package 0.1.35 | Installed dependency; native task suites, tools and graders |
| GEPA | [gepa-ai/gepa](https://github.com/gepa-ai/gepa), `8b0ce6cd99a234f6b74daf37558a2ac0ce18f975` / 0.1.4 | Installed dependency; reviewed source lock in `src/rsi_lab/data` |
| OpenEvolve | [algorithmicsuperintelligence/openevolve](https://github.com/algorithmicsuperintelligence/openevolve), `73448d715968b3578d8458b16295e827edd2b6bf` | Installed dependency at the exact commit; reviewed source lock |
| HyperAgents | [facebookresearch/HyperAgents](https://github.com/facebookresearch/HyperAgents), `59a68f672dfb92c74aeb7e61535d776fb36e172d` | Five vendored upstream files, byte-verified before execution |

HyperAgents' upstream files retain **CC BY-NC-SA 4.0** and their attribution in
[`LICENSE.md`](src/rsi_lab/subjects/hyperagents_vendor/LICENSE.md) and
[`NOTICE.md`](src/rsi_lab/subjects/hyperagents_vendor/NOTICE.md). They are included
in the wheel. They must not be presented as MIT/Apache-licensed lab code.

The adapters, worker transport, budget accounting and benchmark glue are separate
integration code. The HyperAgents profile does not reproduce the upstream Docker
runner, full ensemble or multi-domain harness. No upstream endorsement is implied.

A project-wide first-party license has not been selected. This repository does not
grant a blanket open-source license over all contents; preserve each component's
notices when distributing source or wheels. No PyPI publication is configured.
