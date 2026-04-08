# memory 模块说明

## 1. 模块定位

`autopriv/memory/` 是项目里的历史记忆扩展层。

它的目标是把一次运行中的关键结果保存下来，方便后续回看、分析或做长期经验积累。

不过从当前代码看，这个模块还没有深度接入主流程，属于“已预留、未充分使用”的状态。

## 2. 目录内容

- `episode_memory.py`
  会话记忆的核心实现。
- `__init__.py`
  导出 `EpisodeMemory`。

## 3. `EpisodeMemory` 做什么

`EpisodeMemory` 是一个非常轻量的 JSONL 存储器。

它有两个核心成员：

- `self.path`
  默认保存路径是 `examples/memory/episodes.jsonl`
- `self.working`
  当前会话暂存区，是一个普通字典

## 4. 关键方法

### 4.1 `put(key, value)`

把一项数据放进当前暂存区。

它不会立即写盘，只是先累计在 `working` 中。

### 4.2 `save_episode()`

把当前暂存区转成可 JSON 序列化的结构，并以一行 JSON 的形式追加写入文件。

写入前会先确保目录存在。

## 5. `_as_jsonable()` 的作用

由于有些对象可能是 dataclass，不能直接写入 JSON，所以 `_as_jsonable()` 会递归转换：

- dataclass -> `asdict(...)`
- dict -> 递归转换 value
- list / tuple -> 递归转换元素
- 其他类型 -> 原样返回

这个函数保证记忆模块对项目里的数据对象有基本兼容能力。

## 6. 当前在项目中的实际地位

从目前代码来看，`AutoConfigPipeline` 并没有直接调用 `EpisodeMemory`。

这意味着：

- 记忆能力已经有了基础实现
- 但运行结果还没有自动沉淀到这个模块
- 目前更多是为后续扩展预留接口

## 7. 适合保存什么

如果后续接入主流程，这个模块很适合保存：

- 用户任务
- planner 输出
- 探测报告
- 最终配置
- critic 结论
- 执行结果

这样可以逐渐形成“历史案例库”。

## 8. 当前优点与限制

优点：

- 实现极简，容易接入
- JSONL 适合逐条追加
- 对 dataclass 有基本兼容

限制：

- 没有查询接口
- 没有分 session 管理
- 没有去重和清理机制
- 没有自动接入 pipeline

因此它目前更像“轻量持久化工具”，还不是完整记忆系统。
