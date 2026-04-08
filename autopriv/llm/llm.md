# llm 模块说明

## 1. 模块定位

`autopriv/llm/` 负责封装项目里的大模型调用逻辑。

它的目标不是实现完整 SDK，而是提供一个足够简单、稳定的接口，让 `planner`、`configer` 和 `critic` 都能以相同方式向模型请求 JSON 结果。

## 2. 目录内容

- `client.py`
  大模型调用主实现。
- `__init__.py`
  导出 `LLMClient` 和 `LLMConfigError`。

## 3. `LLMClient` 的职责

`LLMClient` 主要做三件事：

- 校验模型配置是否齐全
- 调用兼容 OpenAI Chat Completions 的接口
- 把模型输出解析为 Python 字典

## 4. 配置校验 `ensure_ready()`

`ensure_ready()` 会检查 `AppSettings.model` 是否存在且已启用。

模型配置最少要求：

- `AUTOPRIV_LLM_API_KEY`
- `AUTOPRIV_LLM_BASE_URL`
- `AUTOPRIV_LLM_MODEL`

如果缺少任意一个，就会抛出 `LLMConfigError`。

这也是为什么 `AutoConfigPipeline` 在初始化时就会先做一次模型配置检查。

## 5. 请求发送 `chat_json()`

`chat_json(system_prompt, user_prompt, temperature=0.1)` 是整个模块最核心的方法。

### 5.1 它如何组织请求

它会构造一个 POST 请求，目标 URL 为：

`<base_url>/chat/completions`

请求体包含：

- `model`
- `temperature`
- `response_format: {"type": "json_object"}`
- `messages`

其中消息严格分成：

- `system`
- `user`

### 5.2 为什么强制 JSON

这个项目依赖结构化输出。如果模型返回自由文本，各 agent 很难稳定解析结果。

因此当前实现同时做了两层约束：

- 请求时声明 `response_format = json_object`
- 收到响应后再用 `_safe_json_load()` 做解析校验

## 6. 输出解析 `_safe_json_load()`

模型返回内容后，`_safe_json_load()` 会：

1. 去掉首尾空白
2. 如果内容被 ``` 包裹，尝试去掉代码块标记
3. 调用 `json.loads()`
4. 确认最终结果必须是字典

如果解析后不是 JSON 对象，会抛出 `LLMConfigError`。

## 7. 当前模块在项目中的使用方式

以下 agent 会直接创建并使用 `LLMClient`：

- `PlannerAgent`
- `ConfigerAgent`
- `CriticAgent`

它们的调用模式基本一致：

1. 从 `autopriv/prompts/` 读取 prompt 模板
2. 用 `render_prompt()` 注入变量
3. 调用 `chat_json()`
4. 对返回结果做本地解析和兜底

## 8. 当前优点

- 结构简单，阅读成本低
- 对上层 agent 提供统一接口
- 明确要求 JSON 输出，适合流程编排

## 9. 当前限制

- 只支持最基础的聊天完成接口
- 没有重试、退避、限流和错误分级
- 没有统一日志和请求追踪
- 对服务端返回格式的假设较强

因此它适合作为项目原型期的轻量封装，但距离生产级 LLM 客户端还有明显差距。
