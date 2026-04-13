# 代码更改计划

文件用于本次代码任务更改任务的说明。

## 更改目的

- 1.`planner` 与`pipeline` 职责的分离，将控制转移给pipeline
- 2. `blackboard` 、`state` 、`observation`、`action_trace`等用于记录上下文与状态的类太多，需要简化与合并

## 更改思路与要求

### 分离`planner` 与`pipeline` 职责
框架运行应该如下
```text
1. planner.run() -> 得到任务理解与探测计划
2. prober.run_startup_snapshot() -> 先执行一次标准探测
3. 如果探测失败或探测异常，则由 pipeline 判断是否重试 prober
4. configer.run() -> 生成候选配置
5. critic.run() -> 产出审查结论
6. 如果 critic 要求重配，则重新进入 configer
7. 如果 critic 要求重探测，则回到 prober
8. 如果 critic 通过，则结束配置流程
9. 只有在用户指令明确需要执行时，才进入 executor
```
这样主流程变成“按阶段推进 + 少量回退判断”。

`planner.py` 需要进行收缩。保留 `run()`，移除 `decide_next()`，避免每次调用都重新从磁盘读取 prompt，planner需要能理解用户指令，首先明白这个指令是否需要执行，如果执行则最后要进入executor，接着需要判断是否为简单任务（默认非简单任务），如果判断为简单任务，那么就不需要进行探测。planner最后得到的输出要可以帮助pipeline进行决策。

同时建议处理下面几个现有问题：
1. 删除用不到prompt的文件，对任务实现相关prompt需要进行检查与修改使其可以完成任务。

`pipeline.py` 核心流程需要被拆成多个阶段函数像是`_run_plan_phase()`与`_run_probe_phase()`等，将流程进行拆分与控制，每个流程结束后可以得到的output可以帮助pipeline进行决策。

同时建议处理下面几个现有问题：
1.删除重复的 `run_with_probe_policy()`
2.不再同时维护 `state`、`observation`、`action_trace`、`blackboard` 四套上下文（这也是另一个主任务）

### 上下文与状态记录

`types.py` 可以新增 `RunContext` 和 `RunState`用于记录pipeline中的上下文与状态，`blackboard` 仅用于 trace 记录，保留原有的名字方便后续扩展。

## 更改门限

本次更改需要聚焦两个主线内容，其他一些例如prober的优化不在本次更改范围内，更改完成后需要补齐文件后的“更改后运行逻辑”与“更改后运行命令”的部分。

## 更改后运行逻辑

更改后的运行逻辑为**阶段式推进 + 少量回退**，由 `pipeline` 完全控制流程，`planner` 不再参与调度决策：

```text
1. plan_phase：planner.run() → 得到任务理解（goals/constraints）、探测计划（probe_plan）、
   以及两个关键决策字段 requires_probe 和 request_execute
2. probe_phase（仅当 requires_probe=true）：prober.run_startup_snapshot() → 执行标准探测，
   如果探测异常，pipeline 自动重试（最多 2 次）
3. config_review_phase：
   3a. configer.run() → 生成候选配置
   3b. critic.run() → 产出审查结论，包含 decision 字段（approve/re_config/re_probe/reject）
   3c. 如果 decision=re_config → 回到 3a 重新生成配置
   3d. 如果 decision=re_probe → 回到 probe_phase 重新探测后再进入 3a
   3e. 如果 decision=approve → 配置通过
   3f. 如果 decision=reject → 流程终止
   （最多循环 3 次）
4. executor_phase（仅当 request_execute=true 且 critic approved）：executor.run()
```

状态管理：统一使用 `RunContext`（持有各 agent 输出）和 `RunState`（持有流程状态），
`Blackboard` 仅用于 trace 记录。

## 更改后运行命令

运行命令不变：

```bash
conda run -n autopriv python main.py "请自动配置隐私计算任务，优先低延迟"
```

可选参数也不变：`--out`、`--config-out`、`--report-out`。