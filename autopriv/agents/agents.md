# agents 模块说明

## 1. 模块定位

`autopriv/agents/` 是项目中最接近“角色协作”的一层。这里定义了每个 agent 负责的事情，以及它们如何把输入转换成结构化输出。

当前目录包含 5 个核心 agent：

- `PlannerAgent`
- `ProberAgent`
- `ConfigerAgent`
- `CriticAgent`
- `ExecutorAgent`

另外还有一个共同基类 `Agent`。

## 2. 这个目录里的文件分别做什么

- `base.py`
  定义 agent 的公共抽象基类。
- `planner.py`
  理解任务，生成初始计划，并在流程运行中决定下一步动作。
- `prober.py`
  收集网络和主机资源信息，生成探测报告。
- `configer.py`
  把规划结果、探测结果、规则库和 LLM 判断融合成最终配置。
- `critic.py`
  对候选配置做静态检查和 LLM 风险审查。
- `executor.py`
  根据配置尝试执行目标后端，目前主要预留给 SecretFlow 和 MP-SPDZ。
- `__init__.py`
  统一导出各 agent 类。

## 3. 公共基类 `Agent`

`base.py` 中的 `Agent` 很轻，只做两件事：

- 给每个 agent 一个 `name`
- 给每个 agent 一个统一的 `run()` 抽象接口

它还内置了一个 `ToolRegistry`，方便 agent 注册和调用本地工具。

这意味着项目里的 agent 不是“完全自由的脚本”，而是被统一纳入同一种调用风格。

## 4. `PlannerAgent`

### 4.1 作用

`PlannerAgent` 是流程起点。它要先把用户任务翻译成机器可执行的计划，然后在运行过程中持续判断下一步该轮到谁。

### 4.2 关键方法

- `run(instruction, blackboard=None)`
  调用 `_run_llm()`，产出 `PlannerOutput`，并把探测计划写到黑板上。
- `decide_next(instruction, state, observation=None, blackboard=None)`
  根据当前状态、最近观察和通信轨迹，让 LLM 选择下一步 agent。
- `_run_llm(instruction)`
  读取 `planner_system.txt` 和 `planner_user.txt`，向模型请求结构化规划结果。

### 4.3 生成的核心信息

- `goals`
  任务目标列表。
- `constraints`
  约束条件，例如偏好的后端或任务优先级。
- `probe_plan`
  给 `ProberAgent` 的探测计划，包括采样次数、探测间隔、指标和提示文本。

### 4.4 容错逻辑

`planner.py` 做了两层兜底：

- `_parse_probe_plan()` 会修正无效的 `metrics`、`sample_count`、`interval_s` 和 `tool_args`
- `_parse_action()` 会限制下一步只能是 `prober`、`configer`、`critic`、`executor` 或 `stop`

这可以减少 LLM 输出不规范导致的流程失控。

## 5. `ProberAgent`

### 5.1 作用

`ProberAgent` 负责收集运行环境信号。当前主要关心网络和机器基础资源。

### 5.2 注册的工具

初始化时会注册 `NetworkProbeTool()`，所以它当前依赖的是 `network_probe` 工具。

### 5.3 关键方法

- `run()`
  默认等价于单次探测。
- `run_once()`
  采集一次网络和机器资源，生成 `ProbeOutput`。
- `run_periodic(sample_count, interval_s)`
  按给定次数和间隔连续采样，生成 `ProbeReport`。
- `run_startup_snapshot(planner, periodic_interval_s, blackboard=None)`
  启动阶段常用入口。会根据 planner 的计划选择单次探测还是少量多次探测。

### 5.4 启动阶段的保护策略

即使 planner 生成了激进参数，`run_startup_snapshot()` 也会主动收缩：

- `sample_count` 最多 3 次
- `interval_s` 最多 2 秒

这样做的目的不是“完全听从 planner”，而是保证启动阶段足够快，不被长探测拖住。

### 5.5 汇总逻辑

`_build_summary()` 会从多次样本里提取：

- `avg_rtt_ms`
- `avg_bandwidth_mbps`
- `max_rtt_ms`
- `min_bandwidth_mbps`
- `cpu_cores`
- `memory_gb`

这些字段后续会被 `configer` 和 `critic` 使用。

## 6. `ConfigerAgent`

### 6.1 作用

`ConfigerAgent` 是项目里最核心的“融合器”。它不只是简单拼接输入，而是分层决定配置。

### 6.2 输入来源

- `PlannerOutput`
- `ProbeOutput`
- 专家规则命中结果
- LLM 二次细化结果
- 黑板中的通信轨迹

### 6.3 生成配置的顺序

它的逻辑是分层推进的：

1. 先用代码规则给出默认值
2. 再从知识库取命中规则
3. 再把默认值和规则命中交给 LLM 做细化
4. 最后拼出 `ConfigOutput`

### 6.4 代码内置的默认规则

- `_choose_backend()`
  优先尊重 `preferred_backend`；否则根据 RTT 和带宽做基础选择。
- `_choose_mode()`
  RTT 很高时转向 `offline_precompute`，否则默认 `online_balanced`。
- `_choose_parallelism()`
  根据 CPU 核数在 1、2、4 间选择。
- `_choose_profile()`
  根据带宽或时延确定 `low_bandwidth`、`high_latency` 或 `balanced`。

### 6.5 知识库与 LLM 的配合

`_apply_kb_hints()` 会先把规则库命中的推荐值覆盖到默认方案上，并把规则说明写进 `notes`。

随后 `_llm_refine()` 再把 planner、probe、默认值、规则命中和通信轨迹一起送给模型，让模型做最后修正。

不过它对模型结果仍然保留限制：

- `backend` 只能是 `mp-spdz` 或 `secretflow`
- `mode` 和 `profile` 为空时会回退默认值

### 6.6 附加信息 `extra`

`ConfigOutput.extra` 里保留了大量上下文，便于落盘和调试：

- 原始目标和约束
- 原始探测结果
- 探测计划
- 命中的规则
- 当前 LLM 配置
- 通信轨迹

这部分不是最终给执行器的最小配置，而是“解释这份配置从哪里来”的上下文。

## 7. `CriticAgent`

### 7.1 作用

`CriticAgent` 是执行前的审查员。它要回答的不是“如何生成配置”，而是“这个配置现在能不能放行”。

### 7.2 两类检查

它会做两层检查：

- `_static_checks()`
  纯代码规则检查，不依赖 LLM。
- `LLMClient.chat_json(...)`
  让模型根据规划、探测报告、配置和通信轨迹补充风险判断。

### 7.3 当前静态规则

目前写死了两个关键判断：

- 如果 `max_rtt_ms > 300` 且模式仍是 `online_balanced`，说明高时延下方案不合理
- 如果 `min_bandwidth_mbps < 5` 但 profile 不是 `low_bandwidth`，说明低带宽场景没有被正确处理

### 7.4 决策输出

`CriticOutput` 会包含：

- `approved`
- `risk_level`
- `issues`
- `recommendations`
- `next_agent`

如果静态检查发现问题，它会强制把 `approved` 改成 `False`，并在原本要进入 `executor` 时改派到 `configer` 或 `prober`。

## 8. `ExecutorAgent`

### 8.1 作用

`ExecutorAgent` 是执行预留层。当前实现还不算完整后端适配器，但已经具备最小分发能力。

### 8.2 当前支持情况

- `secretflow`
  会尝试执行 `AUTOPRIV_SECRETFLOW_PSI_SCRIPT` 指定的脚本。
- `mp-spdz`
  当前只返回 `todo`，说明适配器尚未完成。

### 8.3 SecretFlow 执行逻辑

`_run_secretflow()` 会：

1. 定位项目根目录
2. 拼接 SecretFlow 脚本路径
3. 用 `conda run -n <env> python <script>` 执行
4. 根据返回码生成 `ExecutorOutput`

为避免输出过大，它只保留 stdout/stderr 的末尾几行，通过 `_tail()` 截断。

### 8.4 当前边界

这个 agent 目前更像“执行接口占位符”，还不是成熟的多后端执行框架。

另外要注意一件事：从当前 `pipeline.py` 的默认逻辑看，流程通常会在 `critic` 审查通过后直接结束，因此 `executor` 虽然已经实现并接入了分发接口，但默认主链路里通常不会自动走到这里。

## 9. 各 agent 的协作关系

设计上的理想顺序是：

1. `planner` 产出规划
2. `prober` 收集环境
3. `configer` 生成配置
4. `critic` 审查方案
5. `executor` 在通过时执行

但实际流程不完全写死，因为 `planner.decide_next()` 会根据状态和观察动态选下一步。

同时，按当前 `pipeline` 实现，若 `critic` 已批准，主循环会提前结束，所以“设计顺序”与“默认实际执行顺序”并不完全相同。

## 10. 当前实现的优点与限制

优点：

- 每个 agent 的职责划分相对清楚
- 有统一输入输出结构，便于接线
- 已具备“规则 + LLM + 编排”三者结合的雏形

限制：

- planner 对流程走向有较大影响，LLM 输出质量会直接影响链路稳定性
- configer 和 critic 都依赖 LLM，可解释性和稳定性仍需加强
- executor 仍然偏轻量，尚未真正实现多后端抽象
- 默认 pipeline 在 `critic` 通过后就收尾，导致 executor 更像预留能力而非稳定进入的常规步骤
