# prompting 模块说明

## 1. 模块定位

`autopriv/prompting/` 负责 prompt 的读取与变量替换。

这层的作用很单一，但很重要：它把“prompt 内容”与“业务代码”分离开，避免 agent 代码里塞满长文本。

## 2. 目录内容

- `prompt_store.py`
  prompt 加载与渲染逻辑。
- `__init__.py`
  导出 `load_prompt` 与 `render_prompt`。

## 3. `PROMPT_DIR`

`prompt_store.py` 中定义了：

`PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"`

这表示所有 prompt 文本默认都从 `autopriv/prompts/` 目录读取。

## 4. 两个核心函数

### 4.1 `load_prompt(name)`

负责按文件名读取 prompt 文本。

例如传入 `planner_system.txt`，它就会读取 `autopriv/prompts/planner_system.txt`。

### 4.2 `render_prompt(name, variables=None)`

先加载 prompt，再对其中的占位符做简单字符串替换。

占位符格式是：

`[[变量名]]`

例如：

- `[[TASK]]`
- `[[STATE_JSON]]`
- `[[PLANNER_JSON]]`

## 5. 当前替换机制的特点

它使用的是最简单的逐个 `str.replace()`，因此有这些特点：

- 简单直接
- 不依赖模板引擎
- 容易阅读和调试

但也意味着：

- 不支持条件分支
- 不支持循环
- 不支持复杂转义

所以它适合当前这种“小型、固定结构 prompt 模板”的项目阶段。

## 6. 模块在主流程中的位置

以下 agent 会直接使用 `render_prompt()`：

- `PlannerAgent`
- `ConfigerAgent`
- `CriticAgent`

其中 `PlannerAgent` 还会在没有 probe prompt 时，用它去渲染 `prober_default.txt`。

## 7. 当前优点与限制

优点：

- prompt 与代码分离，便于单独维护
- 替换逻辑非常轻，几乎没有学习成本

限制：

- 变量缺失时不会报警，可能直接留下未替换文本
- 没有模板校验
- 没有 prompt 版本管理

如果后续 prompt 复杂度提升，这一层可能需要升级为更完整的模板系统。
