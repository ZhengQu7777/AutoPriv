# prompts 模块说明

## 1. 模块定位

`autopriv/prompts/` 存放项目使用的 prompt 模板文本。

这些文件本身不包含 Python 逻辑，但它们会直接影响 `planner`、`configer`、`critic` 的输出格式和行为，因此也是项目的重要"配置代码"。

## 2. 当前有哪些 prompt

- `planner_system.txt`
- `planner_user.txt`
- `configer_system.txt`
- `configer_user.txt`
- `critic_system.txt`
- `critic_user.txt`
- `prober_default.txt`

## 3. `planner_system.txt`

作用：

- 告诉模型它是隐私计算自动配置系统中的 planner
- 强制返回 JSON
- 规定输出必须包含 `goals`、`constraints`、`requires_probe`、`request_execute`、`planning_notes`、`probe_plan`
- 给出 `probe_plan` 的字段结构
- 说明 `requires_probe` 和 `request_execute` 的判断规则

它决定的是"planner 理解任务时的输出格式"。

## 4. `planner_user.txt`

作用：

- 注入用户任务 `[[TASK]]`
- 告诉模型约束里可包含哪些字段
- 强调要生成实际可用的 `probe_plan`
- 当任务是长任务时，要把探测间隔设成几分钟级别
- 说明何时设置 `request_execute=true` 和 `requires_probe=false`

它更偏向具体任务指令。

## 5. `configer_system.txt`

作用：

- 告诉模型它是多智能体系统中的 configer
- 要求返回所有 5 个字段：`backend`、`mode`、`parallelism`、`profile`、`notes`
- 限制 `backend` 候选为 `mp-spdz` 或 `secretflow`
- 说明 notes 必须与最终配置一致，不能出现矛盾
- 说明修订轮次的行为：当 prev_config 和 critic_feedback 存在时，做 delta 修正而非从头生成

## 6. `configer_user.txt`

作用：

- 注入 planner 结果
- 注入 probe 结果
- 注入代码默认值（`DEFAULTS_JSON`）和 KB notes（`KB_NOTES_JSON`）
- 注入知识库命中
- 注入通信轨迹
- 注入上一轮配置（`PREV_CONFIG_JSON`）和 critic 反馈（`CRITIC_FEEDBACK_JSON`）
- 指导 LLM 在修订轮次时基于 critic 反馈做针对性修正

configer 用到的 prompt 上下文是所有 agent 中最完整的。

## 7. `critic_system.txt`

作用：

- 告诉模型它是执行前审查员
- 规定输出字段必须包含：
  - `approved`
  - `decision`（approve / re_probe / re_config / reject）
  - `risk_level`
  - `issues`
  - `recommendations`
  - `next_agent`
- 说明了 `decision` 各取值的含义和对应的 `next_agent` 设置规则

它是审查输出结构的格式约束。

## 8. `critic_user.txt`

作用：

- 注入 planner、probe_report、config 和通信轨迹
- 要求模型给出以风险为中心的审查结论
- 明确要求设置结构化的 `decision` 字段

这使得 critic 能综合任务目标、环境信息和候选配置做判断。

## 9. `prober_default.txt`

作用：

- 给探测任务一个默认说明文本
- 强调优先采集 RTT、带宽、CPU 和内存
- 强调低开销和确定性输出

这个 prompt 当前不会直接驱动本地工具执行逻辑，但会被保存到规划与报告中，用于解释"本次探测原本想做什么"。

## 10. 当前设计特点

- prompt 拆分清晰，按 agent 职责分开
- planner 只做任务理解，不再有调度类 prompt
- prompt 本身比较短，便于快速迭代

## 11. 当前限制

- prompt 仍较简化，对边界情况约束不算强
- 没有版本号或评测机制
- 没有针对不同模型的适配层

后续如果模型输出稳定性不足，优先应该从这个目录强化格式约束和规则说明。
