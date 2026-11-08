# Third-party sources

| Component | Source / revision | Integration |
|---|---|---|
| AgentDojo | [ethz-spylab/agentdojo](https://github.com/ethz-spylab/agentdojo), package 0.1.35 | Installed dependency; native task suites, tools and graders |
| XSTest | [paul-rottger/xstest](https://github.com/paul-rottger/xstest), `d7bb5bd738c1fcbc36edd83d5e7d1b71a3e2d84d` | 450 prompts normalized from CSV to JSON, preserving all columns; raw source SHA-256 is recorded in the data |
| AgentHarm | [official Inspect implementation](https://github.com/UKGovernmentBEIS/inspect_evals/tree/main/src/inspect_evals/agentharm), Inspect Evals 0.27.0 / Inspect AI 0.3.288 | Optional installed native tools and graders; 175 source files checked against `agentharm_source_lock.json` |
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

XSTest is by Paul Röttger, Hannah Rose Kirk, Bertie Vidgen, Giuseppe Attanasio,
Federico Bianchi and Dirk Hovy, "XSTest: A Test Suite for Identifying Exaggerated
Safety Behaviours in Large Language Models", NAACL 2024,
[doi:10.18653/v1/2024.naacl-long.301](https://doi.org/10.18653/v1/2024.naacl-long.301).
Its prompts are CC-BY-4.0; the complete license is in
[`XSTEST_LICENSE.md`](src/rsi_lab/data/XSTEST_LICENSE.md). The JSON conversion is a
format change, not new benchmark content. The judge adapter is first-party code.

AgentHarm's public dataset is separately downloaded at revision
`e23b3fe60a0da9037314b88e5ee3a0c054970dad`, verified by raw file hashes and kept
outside Git. Preserve its upstream terms; it is not relicensed by this repository.
The integration uses the official mock tools and scorers, with a local durable
model bridge and strict refusal-judge parsing, not the official default solver.
