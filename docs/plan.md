# 代码更改计划

文件用于本次代码任务更改任务的说明。

## 更改目的

- 1. 修改相关的prompt使得框架针对`mp-spdz`生成的mpc文件能够正确在`mp-spdz`中运行。

## 更改思路与要求

### `mp-spdz` 结构

本地`mp-spdz`安装的地址为：/Users/dengruotao/Documents/mp-spdz-0.4.2
你可以查看它的结构与文件来协助本次任务的更改，我简单说下其中部分结构。其中 Player-Data 目录是输入文件，Scripts 目录下存放mp-spdz自带的脚本。

### mpc文件样例

项目 output 目录下psi_task.mpc 是一个可以运行的mpc文件。它是有框架生成并进行修改后才可以运行的，我保留了旧版为psi_task_old.mpc。

你需要看看两者不同，从而去修改对应的prompt使得mpc文件生成可以更加准确，注意这是一个psi任务的例子，不要使得prompt过于特化，使得后续其他不同任务生成受到影响。

### mpc运行指令例子

当前运行生成的sh文件无法直接运行，我经过下面这样的指令可以运行。
第一种运行方法：
先进入mp-spdz目录
./compile.py psi_task.mpc  // 先编译mpc文件
./semi2k-party.x 0 psi_task -pn 13263 -h localhost -N 2 -OF output //一个窗口作为第0方运行两方协议，制定好端口与输出文件
./semi2k-party.x 1 psi_task -pn 13263 -h localhost -N 2 -OF output //另一个窗口作为第1方运行两方协议，制定好端口与输出文件
第二种运行方法：
./compile.py psi_task.mpc  // 先编译mpc文件
./Scripts/semi2k.sh //采用sh运行

根据正确的运行方法，修改对应的prompt，使得sh文件生成更加正确。


## 更改门限

本次更改需要聚焦`executor`模块生成结果的改造与优化，更改完成后需要补齐文件后的“更改后大致变化”与“更改后运行命令”的部分。

## 更改后大致变化

本次只改 `autopriv/prompts/executor_mp_spdz.txt`，executor 代码与流水线逻辑保持不变。prompt 重写后 LLM 生成的 `.mpc` / `.sh` 更符合 MP-SPDZ 实际语法与运行约定：

- `.mpc` 改为平展脚本（不再包 `def main()` / `if __name__ == '__main__'`），所有逻辑写在模块顶层。
- 秘密值的累加器必须使用 `sint(0)`，防止 cint 误用导致秘密泄漏或类型错误。
- 约束了合法的导入方式与类型选择（sint/sfix/cint 语义）。
- 保留 configer → Scripts/<protocol>.sh 的映射，默认 semi2k。
- `.sh` 不再硬编码用户路径：通过 `MP_SPDZ_HOME` 环境变量定位安装目录，用 `$SCRIPT_DIR` 定位 `.mpc` 所在目录，拷贝到 `$MP_SPDZ_HOME/Programs/Source/`。
- `.sh` 默认不传 `-R` 参数，直接 `./compile.py <program>`；运行走 `./Scripts/<protocol>.sh <program>`（显式传程序名）。
- 提醒用户准备 `Player-Data/Input-P0-0`、`Input-P1-0` 输入文件。
- 去掉了不一定可用的 `/usr/bin/time -v`。

这些改动按任务普适规则组织（不是 PSI 专属），后续其他任务类型（PIR、比较、统计）也可复用同一套规则。

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
