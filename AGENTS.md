## 项目介绍

本项目构建autopriv多智能体自动配置架构，用于实现利用多agent协作，通过规划-采集本地配置-融合结果-得到配置参数，来实现通过agent配置隐私计算相关参数的功能。

## 项目结构

- `README.md`：项目的简单入口说明，包含目标、架构、运行方式与环境变量。
- `LOG.md`：对话与改动归档日志，每次问答后都要补充总结。
- `main.py`：命令行入口，接收用户任务并启动主流程。
- `autopriv/`：框架核心代码。
- `autopriv/agents/`：多智能体实现。
- `autopriv/agents/planner.py`：理解任务、生成初始计划、决定下一步由哪个 agent 执行。
- `autopriv/agents/prober.py`：采集本地环境信息，输出探测结果与摘要。
- `autopriv/agents/configer.py`：融合任务目标、环境信息、专家规则和 LLM 结果，生成最终配置。
- `autopriv/agents/critic.py`：在执行前审查配置是否合理，输出风险与建议。
- `autopriv/agents/executor.py`：执行预留位，当前主要用于后续接入 SecretFlow 或 MP-SPDZ。
- `autopriv/orchestration/`：流程编排层。
- `autopriv/orchestration/pipeline.py`：主流程调度器，负责组织 planner、prober、configer、critic、executor。
- `autopriv/orchestration/blackboard.py`：消息黑板，记录 agent 间通信内容。
- `autopriv/tools/`：本地工具层。
- `autopriv/tools/network.py`：网络与机器资源探测工具。
- `autopriv/knowledge/`：轻量专家知识库与规则文件。
- `autopriv/knowledge/expert_rules.json`：专家规则定义。
- `autopriv/llm/`：大模型调用封装。
- `autopriv/prompting/` 与 `autopriv/prompts/`：提示词模板与加载逻辑。
- `autopriv/types.py`：项目通用数据结构定义。
- `autopriv/settings.py`：环境变量与运行配置加载。
- `autopriv/memory/`：历史记忆能力，当前属于扩展模块。
- `examples/`：样例输出、agent 输出示例和 PSI 演示脚本。
- `docs/`：项目框架文档，重点解释框架逻辑、模块逻辑和运行逻辑。

## 规定
### 用户对话规定

用户对话分为：1.复杂任务指令 2.简单任务指令 3.回复指令 不满足用户对话的命令无法通过本次任务门禁！
- 用户对话格式：复杂任务指令/简单任务指令/回复指令：“具体命令”
- 1.复杂任务指令。用户通过输入严谨的语句进行任务布置，用户的语句会依次包括任务上下文描述、任务目的、任务执行过程、任务修改范围、任务检查。
- 例子:
”复杂任务指令：这是一个简单的多智能体框架项目，利用agent协作来配置隐私计算相关的配置。（任务上下文）我想要理解这个项目，得到各个模块代码的说明，梳理框架逻辑。（任务目的）你需要先读取README文件，了解项目构成，接着去分模块读取框架的具体设计，接着梳理框架逻辑，然后总结各个模块的代码逻辑，最后细化AGENTS.md中的项目结构，并在/docs生成多个md文件来描述各个模块的代码逻辑、框架逻辑、运行逻辑等。(任务执行过程) 这次对话我们修改的范围仅限于/docs文件夹与AGENTS.md 与LOG.md。（任务修改范围）任务完成后需要进行检测1.修改是否在允许范围 2.总结是否清晰，是否陷入技术细节 3.总结是否简单易懂，让py基础薄弱的人也能理解 4.是否将本次对话进行总结归档到LOG中（任务检查）“
- 2.简单任务指令。一两句话描述的简单任务。
- 3.回复指令。简单回复上次任务中的智能体提出的问题。

### 归档规定

用户每次问答需要进行总结归档到 LOG.md 中，用户的提问与回答都需要各总结为一小段话。例子如下：

- （xx时间）
- 用户：xxxxx 
- 回答：xxx 
- 改动文件：xxx

### 模块md文件规定

每个代码模块目录下需要有一个对应的md文件用于描述该模块的功能与代码逻辑，该md文件在代码修改的同时需要同时更新。该md文件可以用于快速注入任务上下文。

- `autopriv/agents/` 对应 `autopriv/agents/agents.md`
- `autopriv/orchestration/` 对应 `autopriv/orchestration/orchestration.md`
- 依次类推


