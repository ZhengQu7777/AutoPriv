# 代码更改计划

文件用于本次代码任务更改任务的说明。

## 更改目的

- 1. 继续修改相关的prompt使得框架针对`mp-spdz`生成的mpc文件能够正确在`mp-spdz`中运行。

## 更改思路与要求

### `mp-spdz` 结构

本地`mp-spdz`安装的地址为：/Users/dengruotao/Documents/mp-spdz-0.4.2
你可以查看它的结构与文件来协助本次任务的更改，我简单说下其中部分结构。其中 Player-Data 目录是输入文件，Scripts 目录下存放mp-spdz自带的脚本。

### mpc文件样例

项目 output 目录下psi_task.mpc 是一个可以运行的mpc文件。它是有框架生成并进行修改后才可以运行的，我保留了旧版为psi_task_old.mpc。

你需要看看两者不同，从而去修改对应的prompt使得mpc文件生成可以更加准确，注意这是一个psi任务的例子，不要使得prompt过于特化，使得后续其他不同任务生成受到影响。

其重点在于：1.不应该去认为是动态输入，MP-SPDZ 编译阶段需要知道数组多大 2.sint.get_input_from是正确的而size0.read_from(0)会报错：AttributeError: 'cint' object has no attribute 'read_from'
另外任务编写应该根据所得的本地设备的配置，尽量有些优化的写法。（比起不知道配置的情况）

### mpc运行指令例子

当前运行生成的sh文件无法直接运行，我经过下面这样的改动可以运行：
报错：
Program was compiled for a prime field, not a ring modulo a power of two. Use './compile.py -R <size>'.
我将
./compile.py "$PROGRAM"  改为 ./compile.py -R 64 "$PROGRAM" 可以运行
另外默认协议应该是更简单的`semi2k`

根据正确的运行方法，修改对应的prompt，使得sh文件生成更加正确。


## 更改门限

本次更改需要聚焦`executor`模块生成结果的改造与优化，更改完成后需要补齐文件后的“更改后大致变化”与“更改后运行命令”的部分。

## 更改后大致变化

本次只改 `autopriv/prompts/executor_mp_spdz.txt`，executor 代码与流水线逻辑保持不变。本次在上一轮基础上继续修正 LLM 生成工件的正确性，重点是编译期形状、输入接口、默认协议与编译参数的匹配：

新增/修正的普适规则（任务无关）：

- A4「编译期尺寸」：数组维度与循环上界必须是 Python int 或模块级常量；禁止用运行时 sint/cint 值作为维度或上界（`sint.Array(size0)`、`@for_range(size0)` 都是错的）。
- A5「输入接口」：唯一合法的读入方式是 `sint.get_input_from(party)` / `sfix.get_input_from(party)`；**不存在** `cint.read_from`（会直接抛 `AttributeError: 'cint' object has no attribute 'read_from'`），需要公开 size 的话用 `sint.get_input_from(p).reveal()` 得到 cint。
- A7「MAX_SIZE padding 范式」：对"实际长度未知"的输入，选一个编译期 MAX_SIZE、始终读 MAX_SIZE 个元素、运行时用 `i < size` 做 mask。这是 MPC 程序的通用模式，不止 PSI 适用。
- A10「基于 probe/configer 做合理优化」：MAX_SIZE、`@for_range_opt` 的使用、是否上大并行度，应参考 `probe.cpu_cores` / `config.parallelism` / `probe.memory_gb` / `probe.rtt_ms` / `probe.bandwidth_mbps`；这些 hint 对所有任务类型都适用。
- B 段默认协议：明确以 `semi2k` 为默认（2PC 半诚实，环上，最轻），`offline_precompute` 不再等同于 mascot（安全模型与离线预计算是正交的）。
- C 段编译参数：默认 `./compile.py -R 64 "$PROGRAM"`，对应 ring-based 的 semi2k；field-based 协议（mascot / mal-shamir）才省去 `-R`。并在注释里直接给出 MP-SPDZ 的错误文案 "Program was compiled for a prime field, not a ring modulo a power of two." 让 LLM 理解为什么要带这个参数。

上一轮已有的规则保留：

- `.mpc` 平展脚本，无 `def main()` / `if __name__ == '__main__'`。
- 秘密累加器用 `sint(0)`。
- `.sh` 用 `MP_SPDZ_HOME` + `$SCRIPT_DIR` 定位，无硬编码绝对路径。
- `./Scripts/<protocol>.sh "$PROGRAM"` 带显式程序名参数。
- 不使用 `/usr/bin/time -v`。

整体按任务无关规则组织，PIR、比较、统计、ML 推理等其他任务类型可直接复用。

## 更改后运行命令

运行命令不变：

```bash
conda run -n autopriv python main.py "请自动配置mp-spdz的隐私计算psi任务，优先低延迟，需要运行"
```

生成工件后，用户可在本地有 MP-SPDZ 安装的机器上直接执行：

```bash
export MP_SPDZ_HOME=/path/to/mp-spdz-0.4.2
bash output/<timestamp>_mp-spdz_<task>/run_<task>.sh
```
