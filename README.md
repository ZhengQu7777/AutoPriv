# AutoPriv Multi-Agent Auto-Config

一个简洁、可扩展的多智能体自动配置架构。

## 技术选型结论

- 现阶段优先：自定义轻量架构（当前实现）。
- 可选折中：按需引入 LangGraph 的局部能力（例如状态持久化、可视化 DAG）。
- 暂不建议：一开始就把核心流程全面迁移到 LangGraph。

## 为什么此阶段不强依赖 LangGraph

- 当前流程是稳定的线性链路：planner -> prober -> configer，手写编排更轻、更易控。
- 你后续会持续扩展工具和策略，先用清晰接口把边界定好，迁移到图编排成本低。
- 现阶段核心风险在策略与资源测量，而不是复杂状态图；先把策略做实更划算。
- 你后续 executor 可能在 MP-SPDZ/隐语间切换，真正需要的是“后端适配层”，不是图引擎本身。
- LangGraph 的优势在复杂工作流治理（循环、并发、恢复、人工介入）；目前这些需求还未成为主矛盾。

建议：先保持当前轻量架构；当出现分支回路、并行子任务、人工中断恢复等需求时，再引入 LangGraph 最合适。

## 架构

- `PlannerAgent`：解析用户指令，产出 goals 与 constraints。
- `ProberAgent`：周期探测本地资源（RTT、带宽、CPU、内存），并生成探测报告。
- `ConfigerAgent`：融合 planner/prober 结果，并结合 RAG 专家知识，输出最终配置。
- `AutoConfigPipeline`：默认顺序编排，后续可插入 executor。

## 目录

- `autopriv/agents/`：各 agent 实现
- `autopriv/tools/`：工具抽象与具体探测工具
- `autopriv/knowledge/`：专家规则知识库（RAG）
- `autopriv/orchestration/pipeline.py`：主流程编排
- `main.py`：CLI 入口

## Prober 指标与报告

默认探测指标：

- `rtt_ms`：网络往返时延
- `bandwidth_mbps`：下行带宽近似值
- `cpu_cores`：CPU 核数
- `memory_gb`：物理内存

`ProberAgent` 支持周期采样，配置项：

- 默认策略：启动时采样一次（不需要传次数）
- 周期复测间隔：默认 300 秒（5 分钟），给长任务 executor 使用

输出报告：

- `samples`：每次采样的原始结果和时间戳
- `summary`：平均 RTT、平均带宽、最大 RTT、最小带宽等聚合指标

## Conda 环境

```bash
cd AutoPriv
conda env create -f environment.yml
conda activate autopriv
```

如果环境已存在：

```bash
cd AutoPriv
conda env update -n autopriv -f environment.yml --prune
```

## 运行

```bash
cd AutoPriv
conda run -n autopriv python main.py "请自动配置隐私计算任务，优先低延迟"
```

默认输出路径（不传也会生成）：

- `examples/generated_result.json`
- `examples/probe_report.json`
- `examples/generated_config.json`

如需自定义输出路径，可显式传参：

```bash
conda run -n autopriv python main.py "请自动配置隐私计算任务，优先低延迟" \
	--out examples/generated_result.json \
	--report-out examples/probe_report.json \
	--config-out examples/generated_config.json
```

会生成三份文件：

- 全量结果：`generated_result.json`
- 探测报告：`probe_report.json`
- 配置文件：`generated_config.json`

## Configer 的 RAG 知识库

- 知识库文件：`autopriv/knowledge/expert_rules.json`
- 规则检索器：`autopriv/knowledge/expert_kb.py`
- 当前实现是轻量规则检索（可替换为向量检索+LLM 解释）

你可以把专家知识写成规则：

- 触发条件（例如 RTT 高、带宽低、偏好后端）
- 推荐配置（backend/mode/profile）
- 解释 note（会写入配置 notes）

## API Key 在哪里配置

当前是纯 `LLM Agent` 架构，`PlannerAgent` 和 `ConfigerAgent` 都会调用大模型。
不配置 key/url/model 会在启动阶段直接报错并退出。

请配置环境变量：

- `AUTOPRIV_LLM_API_KEY`
- `AUTOPRIV_LLM_BASE_URL`
- `AUTOPRIV_LLM_MODEL`
- `AUTOPRIV_LLM_TIMEOUT_S`（可选，默认 30）

可参考模板文件 `.env.example`。

另外，prober 的默认周期策略可通过环境变量调整：

- `AUTOPRIV_PROBE_INTERVAL_S`（默认 300 秒）

Executor 的 SecretFlow 执行参数：

- `AUTOPRIV_SECRETFLOW_ENV`（默认 `sf`）
- `AUTOPRIV_SECRETFLOW_PSI_SCRIPT`（默认 `examples/psi/secretflow_psi_demo.py`）

可直接运行 PSI demo：

```bash
cd AutoPriv
conda run -n sf python examples/psi/secretflow_psi_demo.py
```

## 扩展建议

- 增加 `ExecutorAgent`：读取 `config` 后分发到具体平台执行器。
- 给 `ConfigerAgent` 注入模型分析工具：例如代价预测器、通信轮次估计器。
- 增加更多 `Tool`：GPU 探测、磁盘 IO、容器资源上限、网络抖动分位数等。

建议的 executor 设计：

- 保留一个统一 `ExecutorAgent` 做路由和生命周期管理。
- 为每个平台实现一个 adapter（如 `MPSPDZExecutor`、`SecretFlowExecutor`）。
- 不建议一开始做两个完全独立 executor 主流程，否则策略与日志会重复。
