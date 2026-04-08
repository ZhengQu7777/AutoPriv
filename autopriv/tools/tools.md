# tools 模块说明

## 1. 模块定位

`autopriv/tools/` 是本地工具层。它的职责不是做业务判断，而是提供可复用的“观测与执行能力”。

当前这一层主要服务 `ProberAgent`，用于收集机器和网络信号。

## 2. 目录内容

- `base.py`
  定义工具抽象和工具注册表。
- `network.py`
  定义网络与主机资源探测工具。
- `__init__.py`
  导出当前工具层公开接口。

## 3. `base.py`

### 3.1 `Tool`

`Tool` 是抽象基类，要求每个工具至少提供：

- `name`
- `run(**kwargs) -> dict[str, Any]`

这说明项目默认把工具视为“输入参数 -> 输出字典”的统一组件。

### 3.2 `ToolRegistry`

`ToolRegistry` 是工具管理器，主要能力有：

- `register(tool)`
  注册工具实例
- `get(name)`
  按名字获取工具
- `call(name, **kwargs)`
  直接运行工具
- `names()`
  返回当前已注册工具名

这让 agent 不需要自己保存各类工具对象，只要面向注册表操作即可。

## 4. `network.py`

### 4.1 `NetworkProbeTool`

`NetworkProbeTool` 是当前唯一的实际工具，实现名为 `network_probe`。

它负责采集：

- 网络 RTT
- 近似下载带宽
- CPU 核数
- 物理内存

### 4.2 RTT 探测怎么做

RTT 探测使用 `socket.create_connection()`，默认目标是：

- host: `8.8.8.8`
- port: `53`

它会尝试多次连接，记录每次耗时，最后取平均值作为 `rtt_ms`。

如果连接失败，则该次样本会被忽略；全部失败时 `rtt_ms` 为 `None`。

### 4.3 带宽探测怎么做

带宽探测通过 `urllib.request.urlopen()` 下载一个固定 URL 的部分内容，默认是：

- `https://speed.hetzner.de/1MB.bin`

读取完成后，按字节数和耗时粗略换算为 `bandwidth_mbps`。

这不是专业测速器，而是一个轻量、低成本的近似估计。

### 4.4 主机资源探测

- `os.cpu_count()`
  获取 CPU 核数
- `_memory_gb()`
  使用 `os.sysconf()` 读取总物理内存，并换算成 GB

如果内存读取失败，会返回 `None`。

## 5. 返回结果结构

`NetworkProbeTool.run()` 返回的字典字段包括：

- `rtt_ms`
- `bandwidth_mbps`
- `cpu_cores`
- `memory_gb`

这正好对应 `ProbeOutput` 中的核心字段，便于 prober 直接组装数据对象。

## 6. 当前设计优点

- 接口很统一，方便以后继续加新工具
- 当前实现足够轻量，便于快速启动
- 工具与 agent 解耦，后续替换实现成本较低

## 7. 当前限制

- `ProberAgent.run_once()` 当前没有把 `kwargs` 透传给 `network_probe`，因此 `probe_plan.tool_args` 实际上还没有真正生效
- RTT 和带宽探测都依赖外部网络，离线或受限环境下可能拿不到值
- 带宽结果只是一种粗略估计，不适合作为严谨性能基准

## 8. 扩展方向

后续可考虑在该目录新增更多工具，例如：

- 磁盘 IO 探测
- GPU 资源探测
- 容器配额探测
- 网络抖动分位数探测
- 实际后端预检查工具

新增工具时，最关键的是保持 `Tool` 的统一接口不变。
