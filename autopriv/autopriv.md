# autopriv 核心包说明

## 1. 这个目录负责什么

`autopriv/` 是项目的核心代码目录。它不直接面向用户交互，而是提供整套自动配置流程需要的基础能力：

- 定义统一数据结构
- 加载环境配置
- 组织各类 agent、工具、提示词和知识库
- 暴露主流程依赖的公共接口

如果把整个项目看成一条流水线，`autopriv/` 就是流水线内部的总装区。

## 2. 目录内主要组成

- `types.py`
  负责定义跨模块传递的数据对象，例如规划结果、探测结果、配置结果和审查结果。
- `settings.py`
  负责读取 `.env` 和环境变量，生成统一的运行配置。
- `agents/`
  放置各个智能体实现，是业务决策最集中的目录。
- `orchestration/`
  放置流程编排代码，负责驱动多个 agent 协作。
- `tools/`
  放置本地探测工具和工具注册机制。
- `knowledge/`
  放置专家规则和轻量规则检索逻辑。
- `llm/`
  封装大模型调用。
- `prompting/`
  提供 prompt 加载和变量替换能力。
- `prompts/`
  保存各 agent 对应的 prompt 模板文本。
- `memory/`
  提供会话结果的简单持久化能力，目前还没有深度接入主流程。

## 3. 核心数据流

项目一次运行时，核心数据通常按下面顺序流动：

1. `main.py` 接收用户任务并创建 `AutoConfigPipeline`
2. `PlannerAgent` 把任务转成 `PlannerOutput`
3. `ProberAgent` 根据 `probe_plan` 产出 `ProbeReport`
4. `ConfigerAgent` 结合规划结果、探测结果、知识库和 LLM 生成 `ConfigOutput`
5. `CriticAgent` 对候选配置做审查，产出 `CriticOutput`
6. 设计上在审查通过后可进入 `ExecutorAgent` 尝试执行实际后端任务，但按当前默认 `pipeline` 实现，流程通常会在 `critic` 审查通过后先结束
7. `pipeline` 将全量结果、可读报告和消息轨迹写入输出目录

## 4. `types.py` 在项目中的地位

`types.py` 是整个项目最重要的公共契约文件。它通过 dataclass 明确规定了各模块之间传什么、怎么传。

关键类型包括：

- `AgentMessage`
  黑板里的单条通信消息，记录发送方、接收方、消息类型和内容。
- `ProbePlan`
  planner 给 prober 的探测计划，包含采样次数、间隔、指标和工具参数。
- `PlannerAction`
  planner 每轮决策后的下一步动作。
- `PlannerOutput`
  任务理解后的结构化结果，包含目标、约束和探测计划。
- `ProbeOutput`
  单次探测样本。
- `ProbeReport`
  多次探测的汇总报告，带有 `to_dict()` 便于落盘。
- `ConfigOutput`
  最终配置建议，包含 `backend`、`mode`、`parallelism`、`profile` 等字段。
- `CriticOutput`
  审查结果，回答是否批准、风险等级、问题和下游建议。
- `ExecutorOutput`
  执行阶段结果，说明执行状态、消息和附加细节。

这些类型的价值在于：即使每个 agent 内部策略会变化，模块之间的数据接口仍能保持稳定。

## 5. `settings.py` 的作用

`settings.py` 负责把分散的环境变量整理成结构化配置对象。

它主要做三件事：

- 调用 `_load_dotenv()` 读取项目根目录下的 `.env`
- 从环境变量中解析探测周期、模型超时、SecretFlow 执行环境等参数
- 产出 `AppSettings` 与 `ModelSettings`

当前重点环境变量包括：

- `AUTOPRIV_PROBE_INTERVAL_S`
- `AUTOPRIV_LLM_API_KEY`
- `AUTOPRIV_LLM_BASE_URL`
- `AUTOPRIV_LLM_MODEL`
- `AUTOPRIV_LLM_TIMEOUT_S`
- `AUTOPRIV_SECRETFLOW_ENV`
- `AUTOPRIV_SECRETFLOW_PSI_SCRIPT`

其中 `ModelSettings.enabled` 用来判断 LLM 是否具备可运行的最小配置。

## 6. 对外暴露方式

`autopriv/__init__.py` 当前只导出：

- `PlannerOutput`
- `ProbeOutput`
- `ConfigOutput`

这说明核心包的公开接口还很轻，更多能力仍通过内部目录直接引用。

## 7. 当前实现特点

- 结构清晰，适合逐步扩展
- 类型定义完整，模块边界较明确
- LLM、规则库、工具探测和编排层之间已形成基本闭环
- 目前仍偏原型阶段，很多能力是“可跑通的最小实现”，还不是强健的生产架构

## 8. 阅读顺序建议

如果第一次读这个项目，建议按下面顺序进入源码：

1. `main.py`
2. `autopriv/orchestration/pipeline.py`
3. `autopriv/types.py`
4. `autopriv/agents/`
5. `autopriv/tools/` 与 `autopriv/knowledge/`
6. `autopriv/llm/`、`autopriv/prompting/`、`autopriv/prompts/`
7. `autopriv/memory/`

这样最容易先建立“流程整体感”，再理解具体实现细节。
