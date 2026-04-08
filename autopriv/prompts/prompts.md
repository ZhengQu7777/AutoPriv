# prompts 模块说明

## 1. 模块定位

`autopriv/prompts/` 存放项目使用的 prompt 模板文本。

这些文件本身不包含 Python 逻辑，但它们会直接影响 `planner`、`configer`、`critic` 的输出格式和行为，因此也是项目的重要“配置代码”。

## 2. 当前有哪些 prompt

- `planner_system.txt`
- `planner_user.txt`
- `planner_decide_system.txt`
- `planner_decide_user.txt`
- `configer_system.txt`
- `configer_user.txt`
- `critic_system.txt`
- `critic_user.txt`
- `prober_default.txt`

## 3. `planner_system.txt`

作用：

- 告诉模型它是隐私计算自动配置系统中的 planner
- 强制返回 JSON
- 规定输出必须包含 `goals`、`constraints`、`probe_plan`
- 给出 `probe_plan` 的字段结构

它决定的是“planner 第一次出计划时的基本格式”。

## 4. `planner_user.txt`

作用：

- 注入用户任务 `[[TASK]]`
- 告诉模型约束里可包含哪些字段
- 强调要生成实际可用的 `probe_plan`
- 当任务是长任务时，要把探测间隔设成几分钟级别

它更偏向具体任务指令。

## 5. `planner_decide_system.txt`

作用：

- 告诉模型它现在是在做流程调度，而不是做初始规划
- 强制只能选一个下一步动作
- 限定合法 agent 集合
- 给出几条调度规则

其中最关键的规则包括：

- 没有探测结果时优先 prober
- 有异常时优先重新探测或调整
- 有配置但还没验证时，优先 critic
- critic 拒绝后不能直接进 executor

这份 prompt 是动态调度的核心约束。

## 6. `planner_decide_user.txt`

作用：

- 注入任务文本
- 注入当前状态 JSON
- 注入最近观察 JSON
- 注入黑板通信轨迹 JSON

它给 planner 提供的是“当前局势”。

## 7. `configer_system.txt`

作用：

- 告诉模型它是多智能体系统中的 configer
- 明确只能返回 `backend`、`mode`、`profile`
- 限制 `backend` 候选为 `mp-spdz` 或 `secretflow`

它的重点是让模型做“精修”，而不是无限扩展字段。

## 8. `configer_user.txt`

作用：

- 注入 planner 结果
- 注入 probe 结果
- 注入默认配置
- 注入知识库命中
- 注入通信轨迹

也就是说，configer 用到的 prompt 上下文相对完整。

## 9. `critic_system.txt`

作用：

- 告诉模型它是执行前审查员
- 规定输出字段必须包含：
  - `approved`
  - `risk_level`
  - `issues`
  - `recommendations`
  - `next_agent`

它是审查输出结构的格式约束。

## 10. `critic_user.txt`

作用：

- 注入 planner、probe_report、config 和通信轨迹
- 要求模型给出以风险为中心的审查结论

这使得 critic 能综合任务目标、环境信息和候选配置做判断。

## 11. `prober_default.txt`

作用：

- 给探测任务一个默认说明文本
- 强调优先采集 RTT、带宽、CPU 和内存
- 强调低开销和确定性输出

这个 prompt 当前不会直接驱动本地工具执行逻辑，但会被保存到规划与报告中，用于解释“本次探测原本想做什么”。

## 12. 当前设计特点

- prompt 拆分清晰，按 agent 职责分开
- 初始规划和动态调度使用不同 prompt，职责边界明确
- prompt 本身比较短，便于快速迭代

## 13. 当前限制

- prompt 仍较简化，对边界情况约束不算强
- 没有版本号或评测机制
- 没有针对不同模型的适配层

后续如果模型输出稳定性不足，优先应该从这个目录强化格式约束和规则说明。
