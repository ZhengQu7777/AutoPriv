# 代码更改计划

文件用于本次代码任务更改任务的说明。

## 更改目的

- 1.`configer` 生成逻辑更加合理
- 2. `configer` 可以根据 `critic` 反馈调整输出

## 更改思路与要求

### `configer` 生成逻辑更加合理
生成逻辑应该如下
```text
1. 先用代码规则给出默认值
2. 再从知识库取命中规则
3. 再把默认值和规则命中交给 LLM 做细化
```

当前一些属性，例如并发度只能由代码得到，应该所有属性都再次由LLM去做细化，例如像是LLM refine 之后再拼 notes。思路可以如下：得到的默认值与规则可以作为输出给LLM，_llm_refine在原先的基础上，额外考虑它们，对应的prompt.txt也要随之进行更改。

### `configer` 可以根据 `critic` 反馈调整输出

`configer` 去做判断，如果有 prev_config + critic_feedback ，需要将其作为 prompt 上下文，让 LLM 做 delta 修正而不是从头生成。该更改需要从pipeline 调用、prompt 模板一同进行更改。

## 更改门限

本次更改需要聚焦两个主线内容，其他优化不在本次更改范围内，更改完成后需要补齐文件后的“更改后运行逻辑”与“更改后运行命令”的部分。

## 更改后运行逻辑

configer 的生成流程变为：

```text
1. 代码规则计算默认值（backend/mode/parallelism/profile）
2. KB 命中规则覆盖默认值，产出 kb_notes
3. 将默认值、kb_notes、KB 原始命中一起交给 LLM 做全量细化
   LLM 返回所有 5 个字段：backend/mode/parallelism/profile/notes
4. 如果是修订轮次（prev_config + critic_feedback 不为空），
   LLM 会基于上一轮配置和 critic 反馈做 delta 修正而非从头生成
```

pipeline 的 config_review 循环中：
- 第 1 轮：prev_config=None, critic_feedback=None → 首次生成
- 第 2+ 轮：prev_config=上一轮的 config, critic_feedback=上一轮的 critic → 修订生成

运行主流程不变，仍然是 plan → probe → config+critic 循环 → executor。

## 更改后运行命令

运行命令不变：

```bash
conda run -n autopriv python main.py "请自动配置隐私计算任务，优先低延迟"
```
