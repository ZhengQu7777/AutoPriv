# knowledge 模块说明

## 1. 模块定位

`autopriv/knowledge/` 是项目的轻量专家知识层。

它的职责不是做复杂检索，而是把“领域经验”整理成规则，供 `ConfigerAgent` 在生成配置时参考。

当前这个目录更接近“规则库”，而不是向量数据库或完整 RAG 系统。

## 2. 目录内容

- `expert_rules.json`
  保存专家规则。
- `expert_kb.py`
  负责读取规则并执行匹配。
- `__init__.py`
  导出 `ExpertKnowledgeBase`。

## 3. `expert_rules.json` 的结构

当前规则文件采用统一结构：

```json
{
  "rules": [
    {
      "id": "rule_id",
      "when": {},
      "recommendation": {},
      "note": "说明文字"
    }
  ]
}
```

每条规则由三部分组成：

- `when`
  触发条件
- `recommendation`
  命中后建议覆盖的配置
- `note`
  人类可读解释，会被写入配置说明

## 4. 当前已有规则

### 4.1 `high_rtt_pref_offline`

当：

- `min_rtt_ms >= 120`
- `priority == "latency"`

则建议：

- `mode = offline_precompute`
- `profile = high_latency`

说明高时延场景应减少在线轮次。

### 4.2 `low_bandwidth_compress`

当：

- `max_bandwidth_mbps <= 15`

则建议：

- `profile = low_bandwidth`

说明低带宽场景要尽量压缩传输量。

### 4.3 `prefer_secretflow`

当：

- `preferred_backend == "secretflow"`

则建议：

- `backend = secretflow`

这条规则体现的是“显式偏好优先”。

## 5. `ExpertKnowledgeBase` 如何工作

`expert_kb.py` 中的 `ExpertKnowledgeBase` 在初始化时会：

1. 确定规则文件路径
2. 调用 `_load_rules()` 读取 JSON
3. 把合法规则保存到 `self.rules`

默认规则文件就是当前目录下的 `expert_rules.json`。

## 6. 检索过程 `retrieve()`

`retrieve(planner, probe, top_k=3)` 会顺序扫描规则：

1. 逐条读取规则里的 `when`
2. 调用 `_matches()` 判断是否命中
3. 命中后加入结果列表
4. 达到 `top_k` 后停止

注意：它不是打分排序，也不是相似度检索，而是“按文件顺序顺次匹配，最多取前几个命中项”。

## 7. `_matches()` 的判断维度

当前支持的条件字段包括：

- `preferred_backend`
- `priority`
- `min_rtt_ms`
- `max_rtt_ms`
- `min_bandwidth_mbps`
- `max_bandwidth_mbps`

这些条件会分别与：

- `planner.constraints`
- `probe.rtt_ms`
- `probe.bandwidth_mbps`

进行对照。

只要有一个条件不满足，就判定该规则不命中。

## 8. 这个模块在主流程里的位置

主流程中，只有 `ConfigerAgent` 直接使用该模块：

1. 先生成默认配置
2. 再调用 `kb.retrieve(...)`
3. 用命中的 `recommendation` 覆盖默认配置
4. 把 `note` 写入配置说明
5. 再交给 LLM 做最后细化

所以知识库的定位是“中间修正层”，不是唯一决策源。

## 9. 当前优点

- 规则简单直观，易于维护
- 不依赖额外数据库或索引
- 能快速把业务经验落进系统

## 10. 当前限制

- 没有规则优先级体系，命中顺序受文件顺序影响
- 没有冲突解决机制，后命中规则可能覆盖前命中规则
- 条件表达能力较弱，暂时不支持复杂逻辑组合
- 还不是严格意义上的 RAG，更像规则增强

## 11. 扩展建议

后续如果规则变多，可考虑逐步升级为：

- 增加优先级字段
- 增加冲突处理策略
- 增加更丰富的条件表达
- 引入向量检索或模型解释层

但在当前项目阶段，现有轻量规则库已经足够支撑基础配置推荐。
