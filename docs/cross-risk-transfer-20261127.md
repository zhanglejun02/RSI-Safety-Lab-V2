# 冻结自然更新的跨风险评测：运行前分配

本次不重新搜索或修改更新。将已完成 AgentDojo 确认批次中的全部冻结版本，
交给 AgentHarm 精选原生任务测试；保留阴性、反向、缺失和不确定结果。
它是描述性迁移试跑，不授予 L1/L2/L3，也不沿用二元违规阈值。

## 来源与固定版本

来源：`runs/current/agentdojo-confirm-20261126-v1/run`。准备阶段验证完成库存、
源码归属和执行器文件哈希，把七个版本标签、真实父子关系、原 AgentDojo
新任务汇总及其来源哈希一起冻结。六份不同源码加一个同源码独立执行控制：

| 版本 | 源码哈希前缀 | 实际父代 |
|---|---|---|
| Founder | `edc5c06cd3e4` | — |
| GEPA 07 第 1 轮 | `84c269fc2d2f` | Founder |
| GEPA 07 第 2 轮 | `b3bee63b0582` | GEPA 07 第 1 轮 |
| GEPA 08 第 1 轮 | `eda7b1ec314e` | Founder |
| OpenEvolve 07 第 1 轮 | `bafa5c27c945` | Founder |
| OpenEvolve 08 第 1 轮 | `5a8085a862d2` | Founder |
| sham-Founder | 与 Founder 相同 | Founder，独立执行对照 |

OpenEvolve 08 是保留但未部署的候选；它不是原轨迹的最终部署。五份不同更新
来自四个搜索根，本轮没有新搜索根，也没有 HyperAgents 自然版本。
版本全部纳入，不依据本轮危害分选版。启动后不再读取原批次来替换源码。

## 任务、模型与执行

使用 [AgentHarm v1 锁定适配](agentharm-adaptation.md) 的全部三个已接通家族，
每个家族一个固定 ID，分别测试原生 benign/harmful 两个请求：

- 会议安排：`9-1`；金融操作：`28-1`；数据库访问：`50-1`。
- 七个版本标签 × 三个家族 × 两类请求 × 五个测量块 = **210 次执行**。
- dev/probe 留空；没有编辑器、搜索、公开审查或模型评分器。保留父子配对，
  按任务和块轮转版本执行顺序。sham 不复用 Founder 答案或执行记录。
- actor 沿用原实验 DeepSeek `deepseek-flash`、temperature 0、thinking disabled、
  2,048 输出 tokens、120 秒超时、24 步。请求设置和执行器与来源锁核对。
- 每块 42 episodes / 1,008 actor-call 上限；五块最多 5,040 调用，实际费用
  和 tokens 按账本报告。每块 tokens 上限 8M；最多两个在途请求。
- 不因结果接近零、方向相反或区间较宽而追加候选、任务、块或补充未知请求。
  网络未知保留预留并暂停；明确恢复只继续未尝试分配。

这是公开数据中的新跨风险分配，不是官方 AgentHarm 成绩或秘密留出集。
三个家族及其参考行为已用于零 API 适配验收，尚未用这些自然版本筛选结果。
所有工具为原生模拟；候选代码仍在既有沙箱中实际执行。

## 预定报告

分别报告良性任务原生完成分 ↑、有害任务原生完成分 ↓，保留各自分母、缺失、
原生子项及调用成本。有害完成分不是二元违规率；它可能包含准备操作分。
不计算一个跨 benchmark 总安全分，不将原生分数临时二值化。

每份更新报告相对**实际父代**的配对分数差，同时展示与 Founder 的版本表。
按家族与测量块给出方向，并做移除一个家族后的敏感性检查。95% 近似区间
同时重采样家族和块，条件于这些固定版本；三家族、五块很少，区间只作描述，
不提供多重检验下的通过／失败判断。恒定差值不生成零宽确定性区间。
缺失用 [0,1] 分数范围给出最不利逻辑界，不能把它称为置信区间。

同源码 sham 用来检查当前执行波动，不用于挑选有利的噪声扣除量。评分使用
已锁定的确定性原生 rubric，没有 LLM judge；得分可复算仍不等于 rubric
覆盖了所有现实危害。完成后核对保存轨迹的分数与来源，再验证只读恢复。

交叉表并列展示原 AgentDojo **新任务确认端点**的任务完成率／ASR，以及
本次 AgentHarm 两类原生分数。它们不是同时执行，模型服务的后台版本也未被
固定；不合并分母，不把两轴相关性当作因果关系或方法总体规律。
旧审查结论仅适用于当时的 AgentDojo probe；本次不新增审查效力主张。

## 复用

所有新运行参数位于 `scripts/run_frozen_risk_suite.sh` 顶部；来源版本全集由
已完成批次导入。Bash 共用现有 campaign 冻结／恢复实现，Python 共用
`update-confirmation` 生命周期，只增加命名分数和不请求审查的测量配置。

```bash
bash scripts/run_frozen_risk_suite.sh control runs/current/MY-CROSS-RISK-CONTROL
bash scripts/run_frozen_risk_suite.sh prepare runs/current/MY-CROSS-RISK
bash scripts/run_in_tmux.sh MY-CROSS-RISK -- \
  bash scripts/run_frozen_risk_suite.sh run runs/current/MY-CROSS-RISK
bash scripts/run_frozen_risk_suite.sh status runs/current/MY-CROSS-RISK
bash scripts/run_frozen_risk_suite.sh resume runs/current/MY-CROSS-RISK
```

`prepare` 与 `control` 零付费；`run` 是显式真实调用。恢复读取保存的源码、
配置和脚本，不使用后来修改的顶部参数。tmux 不提供离线 API 或合盖执行保证。
结果保存为 `run/report.md`、`run/metrics.csv`、`run/cross-risk.csv` 和
`run/summary.json`，全部留在被 Git 忽略的运行目录。
