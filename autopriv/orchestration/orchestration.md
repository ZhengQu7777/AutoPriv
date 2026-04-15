# orchestration 模块说明

## 1. 模块定位

`autopriv/orchestration/` 负责把多个 agent 真正组织成一条可运行的流程。

这个目录回答的是两个问题：

- 流程怎样一步一步往前走
- agent 之间的通信怎样记录

当前目录主要有两个文件：

- `pipeline.py`
- `blackboard.py`

## 2. `blackboard.py` 做什么

`Blackboard` 是一个轻量的消息记录器，当前定位为 **trace 记录**。

### 2.1 它提供的能力

- `publish(sender, receiver, kind, content)`
  追加一条消息。
- `list_messages()`
  返回消息对象列表。
- `to_dict()`
  把消息转成适合 JSON 落盘的字典列表。

### 2.2 它的作用

这个类不负责调度，也不负责判断谁先执行。它只负责留下"通信痕迹"。

这些消息会被多个地方使用：

- configer 和 critic 调用 LLM 时，会把通信轨迹送进 prompt
- pipeline 最终会把全部消息写进输出结果

因此黑板的价值是"保留上下文"，而不是"驱动流程"。流程控制和状态维护由 `RunContext` + `RunState` 承担。

## 3. `pipeline.py` 做什么

`AutoConfigPipeline` 是项目里最关键的总调度器，也是流程控制权的唯一持有者。

它负责：

- 初始化所有 agent
- 检查 LLM 配置是否可用
- 维护统一上下文 `RunContext` 和流程状态 `RunState`
- 按固定阶段顺序调用各 agent
- 根据 critic 审查结果决定回退分支
- 保存结构化结果和文本报告

## 4. 初始化过程

`AutoConfigPipeline.__init__()` 会先做两件事：

1. 读取 `AppSettings`
2. 通过 `LLMClient(self.settings).ensure_ready()` 检查模型配置

检查通过后，才会创建：

- `PlannerAgent`
- `ProberAgent`
- `ConfigerAgent`
- `CriticAgent`
- `ExecutorAgent`

这意味着当前项目是"启动即要求 LLM 可用"的设计，而不是只有部分 agent 需要时再延迟检查。

## 5. 主流程 `_run_core()`

`run()` 进入 `_run_core()`。这里是整套协作链路的真实入口。

### 5.1 初始动作

一开始会创建：

- `Blackboard`：用于记录 trace
- `RunContext`：统一上下文，收拢所有 agent 的输出
- `RunState`：流程状态（作为 `RunContext.state`），记录阶段、计数器和布尔标志

不再维护独立的 `observation`、`action_trace` 或 `state` 字典。

### 5.2 阶段式编排

主流程被拆分为多个阶段函数，按顺序推进：

```text
1. _run_plan_phase()           -> planner 理解任务，写入 RunContext
2. _run_probe_phase()          -> prober 采集环境（仅当 requires_probe=True）
3. _run_config_review_phase()  -> configer + critic 主循环（含回退）
4. _run_executor_phase()       -> 仅在 critic 通过且 request_execute=True 时执行
5. _build_result()             -> 汇总所有结果
```

### 5.3 `_run_plan_phase()`

调用 `planner.run()` 产出 `PlannerOutput`，并把关键布尔标志（`requires_probe`、`request_execute`）写入 `RunState`。

### 5.4 `_run_probe_phase()`

调用 `prober.run_startup_snapshot()` 产出 `ProbeReport`。如果探测异常（RTT 过高或带宽缺失/极低），会重试最多 `MAX_PROBE_RETRIES`（2）次。

### 5.5 `_run_config_review_phase()`

这是最核心的循环，最多执行 `MAX_CONFIG_REVIEW_CYCLES`（3）轮：

1. 每轮调用 `configer.run()` 产出 `ConfigOutput`
   - 第 1 轮：`prev_config=None, critic_feedback=None`，首次生成
   - 第 2+ 轮：`prev_config=上一轮 config, critic_feedback=上一轮 critic`，让 LLM 做 delta 修正
2. 再调用 `critic.run()` 产出 `CriticOutput`
3. 如果 `critic.decision="approve"`，结束循环
4. 如果 `critic.decision="re_config"`，回到步骤 1 进行修订
5. 如果 `critic.decision="re_probe"`，先重新探测再回到步骤 1
6. 如果 `critic.decision="reject"` 或超过最大循环次数，使用最后一次结果

### 5.6 `_run_executor_phase()`

只在两个条件同时满足时进入：

- `context.state.critic_approved = True`
- `context.state.request_execute = True`

调用 `executor.run()` 产出 `ExecutorOutput`。

## 6. 异常与兜底逻辑

### 6.1 探测异常判定

`_probe_anomaly(report)` 的规则：

- `max_rtt_ms > 350`
- `min_bandwidth_mbps` 为空
- `min_bandwidth_mbps < 5`

满足任一条件就判定有异常，pipeline 会尝试重试探测。

### 6.2 状态兜底

每个阶段函数在执行前都会用 `assert` 检查前置条件（例如 planner 输出是否存在）。对于 probe 可能缺失的场景（`requires_probe=False`），会自动填充默认空值 `ProbeOutput()` / `ProbeReport()` 而不是报错。

## 7. 输出保存 `run_and_save()`

`run_and_save()` 在得到全量结果后，会完成三类落盘：

### 7.1 全量结果

把完整字典写到 `out_path`。

### 7.2 可选独立文件

- `report_path`
  单独保存 `probe_report`
- `config_path`
  单独保存 `config`

### 7.3 可读报告

调用 `_write_readable_reports()`，在目标目录下生成：

- `agents/planner/planner_output.json` 和 `.txt`
- `agents/prober/prober_output.json` 和 `.txt`
- `agents/configer/configer_output.json` 和 `.txt`
- `agents/critic/critic_output.json` 和 `.txt`
- `agents/executor/executor_output.json` 和 `.txt`
- `overall/overall_report.json` 和 `.txt`

其中 `.txt` 是面向人阅读的简化版摘要，`.json` 更适合程序处理。

## 8. 当前流程特征

这个编排层的特点可以概括为：

- 主流程由代码固定阶段驱动，不依赖 LLM 做调度决策
- 回退分支有限且由代码逻辑控制（critic 可指示回退到 configer 或 prober）
- 统一上下文 `RunContext` + `RunState` 贯穿全流程，不再维护多套状态
- `Blackboard` 仅用于 trace 记录，不参与流程控制
- executor 仅在用户明确要求执行且 critic 通过时才进入

## 9. 当前限制

- 没有并发执行
- 没有任务恢复机制
- 没有超细粒度的错误分类
- prober 内部的探测参数透传和采样策略细分属于后续任务
