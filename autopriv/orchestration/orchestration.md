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

`Blackboard` 是一个很轻量的消息记录器。

### 2.1 它提供的能力

- `publish(sender, receiver, kind, content)`
  追加一条消息。
- `list_messages()`
  返回消息对象列表。
- `to_dict()`
  把消息转成适合 JSON 落盘的字典列表。

### 2.2 它的作用

这个类不负责调度，也不负责判断谁先执行。它只负责留下“通信痕迹”。

这些消息会被多个地方使用：

- planner 决定下一步时，会参考历史通信轨迹
- configer 和 critic 调用 LLM 时，也会把通信轨迹送进 prompt
- pipeline 最终会把全部消息写进输出结果

因此黑板的价值是“保留上下文”，而不是“驱动流程”。

## 3. `pipeline.py` 做什么

`AutoConfigPipeline` 是项目里最关键的总调度器。

它负责：

- 初始化所有 agent
- 检查 LLM 配置是否可用
- 维护全流程状态
- 驱动 planner 决定下一步
- 调用对应 agent
- 处理兜底逻辑
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

这意味着当前项目是“启动即要求 LLM 可用”的设计，而不是只有部分 agent 需要时再延迟检查。

## 5. 主流程 `_run_core()`

`run()` 和 `run_with_probe_policy()` 最终都进入 `_run_core()`。这里是整套协作链路的真实入口。

### 5.1 初始动作

一开始会先创建：

- `Blackboard`
- `planner_out`
- 若干结果变量，如 `probe_report`、`config_out`、`critic_out`
- `observation`
- `action_trace`
- `state`

`state` 里目前记录的是一些布尔标志和计数器，例如：

- 是否已有探测结果
- 是否已有配置
- critic 是否批准
- 是否已经执行过 executor
- 重规划次数

### 5.2 循环调度

主循环最多执行 8 轮。

每轮都会：

1. 调用 `planner.decide_next(...)`
2. 把动作加入 `action_trace`
3. 若有 `updates`，则调用 `_apply_planner_updates()` 修改 `probe_plan`
4. 根据 `action.agent` 分派到具体 agent

### 5.3 每类动作的处理方式

当 planner 选中不同 agent 时，pipeline 会做不同处理：

- `prober`
  执行启动探测，更新 `probe_report`、`probe_out`、`state["has_probe"]` 和 `observation`
- `configer`
  要求必须已有探测结果，否则记录错误观察
- `critic`
  要求必须已有配置和探测报告，否则记录错误观察
- `executor`
  要求必须已有配置且 critic 已批准，否则记录错误观察
- `stop`
  直接结束循环

这里有一个当前实现上的关键细节：`critic` 一旦返回 `approved=True`，pipeline 会立刻 `break`，因此默认主链路通常不会继续走到 `executor` 分支。

### 5.4 观察值 `observation`

`observation` 是 planner 下一轮决策的重要输入。它不是完整状态快照，而是“最近一次执行反馈”。

例如：

- prober 完成后会记录异常与探测汇总
- configer 完成后会记录 backend、mode、profile
- critic 完成后会记录是否批准、风险和下一建议
- executor 完成后会记录执行状态和消息

## 6. 异常与兜底逻辑

### 6.1 探测异常判定

`_probe_anomaly(report)` 的规则比较简单：

- `max_rtt_ms > 350`
- `min_bandwidth_mbps` 为空
- `min_bandwidth_mbps < 5`

满足任一条件就判定有异常。

如果异常出现，pipeline 会把 `replan_count` 加 1，让 planner 在下一轮知道环境不稳定。

### 6.2 安全兜底

即使主循环因为 planner 决策不完整提前结束，pipeline 也会在最后补齐关键结果：

- 没有 `probe_report` 时，强制再跑一次 prober
- 没有 `config_out` 时，强制再跑一次 configer
- 没有 `critic_out` 时，强制再跑一次 critic

这让主流程更稳，不会因为某一轮决策异常直接返回残缺结果。

## 7. planner 对探测计划的动态更新

`_apply_planner_updates()` 支持 planner 在运行中调整：

- `sample_count`
- `interval_s`
- `prober_prompt`

它会优先读取 `updates["probe_plan"]`，如果没有则直接把 `updates` 当成探测计划字段。

这说明当前架构已经预留了“运行中重配探测策略”的入口。

## 8. 输出保存 `run_and_save()`

`run_and_save()` 在得到全量结果后，会完成三类落盘：

### 8.1 全量结果

把完整字典写到 `out_path`。

### 8.2 可选独立文件

- `report_path`
  单独保存 `probe_report`
- `config_path`
  单独保存 `config`

### 8.3 可读报告

调用 `_write_readable_reports()`，在目标目录下生成：

- `agents/planner/planner_output.json` 和 `.txt`
- `agents/prober/prober_output.json` 和 `.txt`
- `agents/configer/configer_output.json` 和 `.txt`
- `agents/critic/critic_output.json` 和 `.txt`
- `agents/executor/executor_output.json` 和 `.txt`
- `overall/overall_report.json` 和 `.txt`

其中 `.txt` 是面向人阅读的简化版摘要，`.json` 更适合程序处理。

## 9. 当前流程特征

这个编排层的特点可以概括为：

- 外表是多 agent 协作
- 内核仍是单线程顺序调度
- planner 拥有动态决定下一步的权力
- pipeline 保留了足够强的兜底，避免流程返回空结果
- executor 已经接入，但默认收尾点实际上更接近 `critic`

## 10. 当前限制

- 没有并发执行
- 没有任务恢复机制
- 没有超细粒度的错误分类
- `state` 仍然比较粗，主要记录布尔状态
- 默认在 `critic` 通过后直接结束，导致 executor 通常不会自动执行
- `executor` 的结果不会在未通过 critic 时自然进入链路

因此它更适合作为清晰、易扩展的原型编排器，而不是复杂工作流引擎。
