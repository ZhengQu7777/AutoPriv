# 代码更改计划

文件用于本次代码任务更改任务的说明。

## 更改目的

- 1. 使得`executor`可以通过流水线的结果，生成对应的运行文件。本次先跑通`mp-spdz`任务，这个任务会根据 `configer` 最后生成的报告与`prober`探测结果（也就是examples/agents中的文件），生成`.mpc`文件与运行脚本`.sh`

## 更改思路与要求

### `executor` 逻辑梳理
其逻辑应该如下
```text
1. 如果用户指令中有需要执行\需要生成运行文件等类似的指令，那么流水线最后会调用`executor`模块，否则直接结束。
2. `executor`模块执行首先要判断用户需要做什么具体的隐私计算任务？隐私计算任务有类似psi，pir等多种任务，用户一般会在用户指令中说明。因此用户指令也需要投喂给`executor`的模型。
3. `executor`模块接着需要读取对应的prompt文件，该文件应该包含对应任务的说明与要求。
4. 最后模块需要将结果输出到新目录output目录下
```

我们认为无论之前critic最后是否给出通过的评论，我们`executor`模块都将最后的`configer`的结果作为输入，也就是有兜底的考量。

`executor`的prompt也需要考量，`executor`需要一个prompt来告诉它是执行模块，它的目的与任务是什么。还需要根据调用不同（像是`mp-spdz`与`secretflow`两种任务），还需要额外的对应的prompt。

以上逻辑需要梳理，查看当前链路是否有未完成的地方。

### `mp-spdz`任务梳理

当前有`mp-spdz`与`secretflow`两种任务，我们这次只跑通`mp-spdz`任务。其任务逻辑需要注意的有：
1.`mp-spdz`任务应有对应的prompt，该prompt需要有mp-spdz的说明，以及最后结果的要求，你需要生成该prompt，mp-spdz的文档网站为：https://mp-spdz.readthedocs.io/en
2. `mp-spdz`任务最后应该生成`.mpc`文件与运行脚本`.sh`，其中.mpc文件是对应隐私计算任务的运行文件，.sh是用户运行的脚本，我们认为用户可以在对应安装好mp-spdz的服务器上，直接运行脚本就可以运行，并得到运行结果（性能指标）。

以上逻辑需要梳理，查看当前链路是否有未完成的地方。

## 更改门限

本次更改需要聚焦`executor`模块改造，更改完成后需要补齐文件后的“更改后运行逻辑”与“更改后运行命令”的部分。

## 更改后运行逻辑

executor 阶段逻辑：

```text
1. pipeline 在 config_review 阶段结束后检查 RunState.request_execute
   若为 True，则无论 critic_approved 与否都调用 executor（兜底）
2. executor 把 user_instruction + final_config + probe_summary 作为上下文
3. executor 根据 config.backend 查表 BACKEND_GUIDE_FILES 找到对应的 backend 专属 prompt
   当前只实现 mp-spdz → executor_mp_spdz.txt；其他 backend 返回 status=skipped
4. 拼接 system prompt (executor_system.txt) + user prompt (executor_user.txt
   注入 INSTRUCTION / CONFIG_JSON / PROBE_JSON / PROBE_SUMMARY_JSON / BACKEND_GUIDE)
   调用 LLM 生成 JSON {task_type, mpc_file:{name,content}, sh_file:{name,content}, notes}
5. executor 把 .mpc / .sh 落盘到 output/<timestamp>_<backend>_<task_type>/ 目录
   同时写入 manifest.json 记录 backend、task_type、instruction、config 与 notes
6. sh 文件被 chmod 755 后用户可直接在装有 MP-SPDZ 的机器上执行
```

pipeline 主流程变为：plan → probe（可选）→ config+critic 循环 → executor（当 request_execute=True，兜底调用）。

## 更改后运行命令

运行命令不变：

```bash
conda run -n autopriv python main.py "请自动配置隐私计算psi任务，优先低延迟"
```
