# Agent Note: sshops config 规范格式由代码固化，收敛与门禁共用一份实现

Status: implemented

## Problem

`~/.ssh/config` 的格式规则此前只存在于文档与三个写路径的各自实现里：create/update 生成、迁移脚本追加、手工编辑，各写各的字段顺序与省略规则。结果是同一份 config 里出现三种块格式——空值元数据行（`# location:`）时有时无、`IdentityFile` 有的是 Windows 绝对路径有的写 `~/.ssh/`、块间空行时有时无（137 块内多一行空行、133 块前少一行分隔）。

同时发现仓库里两个"格式修复"脚本已经腐化：`fix_ssh_config.py` 依赖早已删除的 `~/.ssh/server_config` JSON 目录，其 `normalize_key_path()` 还停留在 `zhangyang` 用户名的注释上；`add_comments_to_config.py` 只会给缺注释的块补一份空模板，补出来的是空值字段行，正是漂移的来源之一。两者都没有被 SKILL.md 引用。

## Decision

格式的权威定义是 `scripts/lib/ssh_config_format.py` 一份代码，三处消费：

- `format_ssh_config.py` 是收敛入口与门禁：默认 dry-run 只打印 diff，`--write` 落盘，`--check` 供 CI / 提交前使用（不符合时退出码 1）。
- `ssh_config_manager_v3.py` 的 create/update/delete 在落盘后调用 `_normalize_file()`，把整份文件收敛回规范格式；create 的注释与指令渲染直接复用 lib 的渲染器，不再手拼字符串。
- `tests/test_ssh_config_format.py` 用 14 个用例锁定契约：幂等、字段重排、`Port 22` 省略、`IdentityFile` 归一、未识别指令与块内注释保留、`Host *` 与无元数据块原样不动、CRLF 保留、写入幂等。

规范格式（`ssh_config_format.py` 模块 docstring 同款）：

```text
# ===== <alias> =====
# description: ...   # environment: ...   # tags: a,b   # location: ...
# password: ...      # created_at: ...    # updated_at: ...
Host <alias>
    HostName ...   User ...   [Port <非22>]   [IdentityFile ~/.ssh/<密钥>]   [ProxyJump ...]
```

空值一律省略；块间恰好一个空行；行尾风格沿用文件原样（当前 config 为 CRLF）；未识别指令按原顺序、原拼写保留；不带元数据的块与 `Host *` 通配块整体不动。

同时删除两个腐化脚本（`fix_ssh_config.py`、`add_comments_to_config.py`），SKILL.md 的配置管理章节写入格式契约与三条命令，版本推进到 3.6.0。

## Alternatives considered

- **只写文档规则，不动代码**——文档无法约束三个写路径，漂移已经真实发生；被测代码是唯一能长期兑现的契约。
- **白名单式"只规范化脚本自己创建过的块"**——需要额外 bookkeeping 状态，且会放过手工编辑产生的漂移。
- **保留 `fix_ssh_config.py` 并修补 JSON 依赖**——该脚本同时依赖三套早已废弃的架构（JSON 配置目录、`server_config/*.json`、旧 tags 密码格式），修补等于重写；其唯一仍有价值的能力（路径归一）已被新模块的 `normalize_identity_path` 覆盖。
- **把 `Port 22` 显式写全（不做省略）**——更啰嗦但没有歧义；选择了与现有 5/7 台一致、且与 `ssh_config_manager_v3.py` 既有行为一致的省略写法，避免大范围改写既有块。

## Consequences

- **收益**：格式不再依赖人的记忆或文档；`--check` 可接入提交前门禁，漂移会在下一次写操作时被自动收敛。`fix_ssh_config.py` 的 JSON 依赖腐化不会再复现——新模块不读任何外部配置源。
- **代价与已知上限**：`--check` 是脚本级门禁而非 git hook，只有显式调用才生效；未识别指令的"按原拼写保留"意味着非标准指令（`ProxyCommand` 等）不会被纠正，只保证不丢。当出现跨平台行尾混用时（当前为纯 CRLF）需要重访 `detect_newline` 的"出现即按 CRLF 渲染"策略。
- **对既有行为的影响**：`Port 22` 行与空值元数据行会被删掉——对 config 语义无影响（22 是默认端口、空值字段本就无内容），但会让 `~/.ssh/config` 产生一次可见 diff。

## Verification

- `uv run --project sshops python -m unittest discover -s tests` — 29 用例全绿（含新增 14 例）。
- `uv run --project sshops python sshops/scripts/format_ssh_config.py --check` — 对现有 `~/.ssh/config` 退出码 0。
- 在真实 config 的临时副本上跑 `update` + `delete` 后执行 `--check`，仍为 0，证明管理命令落盘即规范。
