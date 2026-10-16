# Agent Note: 官方 DWS multi Skills 适配顶层发布布局

Status: implemented

## Problem

用户发现 DingTalk Workspace CLI 已提供完整的 Agent Skills，要求把这些 Skills 修改为符合当前代码仓库的格式。本仓库要求每个 Skill 位于顶层独立目录，Python 工具独立声明并锁定依赖；上游 `skills/multi/` 是嵌套发布布局。

## Decision

将官方提交 `92cb3f513c457b9a3578b72ed870632e891dded3` 的 `skills/multi/dingtalk-*/` 导入仓库顶层，保留 16 个 Skill 的原名称、业务规则、参考文件和 54 个 Python 文件。保留上游每个文件，并为独立分发的目录保留 Apache LICENSE、NOTICE 及本地适配说明；不创建额外通用指南或引入 legacy mono。

七个含 Python 脚本的 Skill 增加独立 `pyproject.toml` 和 `uv.lock`，将文档、脚本帮助及缺依赖提示改为 uv 命令，使用脚本所属 Skill 的绝对目录解析环境与脚本路径。脚本业务逻辑保持上游实现。`dingtalk-misc` 声明 `openpyxl`、`pillow` 和 `requests`；听记时间转换和日志摘要使用 IANA 时区数据，因此 `dingtalk-minutes` 与 `dingtalk-misc` 声明 `tzdata`，覆盖 Windows 无系统时区数据库的环境。入口补充 Windows `PYTHONUTF8=1` 约定，使 Python 子进程与调用方编码一致。

修正 `dingtalk-shared/references/recipes/conventions.md` 两处指向不存在的仓库根 `SKILL.md` 的链接，改为指向本 Skill 的入口。README 记录来源提交、功能分工、成套安装建议及 CLI 登录前提。

历史检索：检索 `.agents/notes/` 的 `dingtalk`、`DWS`、`钉钉` 和 `skill`；现有四篇活跃笔记涉及 Jev、日报、SSH 与笔记 Skill 同步，与本主题无关，无需合并或归档。

## Alternatives considered

- 直接引入上游 `skills/multi/` 嵌套目录：上游路径原样保留，后续同步简单，但不符合本仓库顶层独立 Skill 的现有布局。
- 引入单一 mono Skill：一次安装即可覆盖全部功能，但这是上游 legacy 方案，不能保留按产品渐进加载的默认组织方式。
- 另写通用功能指南：内容更短、更适合入门，但需要重复维护产品规则；用户明确选择适配官方既有 Skills，因此采用官方 multi 内容。

## Verification

- 16 个入口通过 skill-creator 的 `quick_validate.py`；逐项核对上游全部 390 个文件均保留，本地文档和脚本引用可解析，JSON 文件可解析，54 个 Python 文件在 warnings-as-errors 下编译通过。
- 七个 Python 环境均通过 `uv sync --locked`；从其他工作目录使用完整路径启动七类代表性脚本的 `--help`，全部返回成功。考勤相关直接依赖导入及日志摘要时区初始化通过。
- 听记模块上游 13 项离线测试在 `PYTHONUTF8=1`、`PYTHONWARNINGS=error` 的环境中全部通过。首次只对父解释器启用 `-X utf8` 时，子进程仍输出 Windows 本地编码，四项测试读取中文 JSON 失败；环境变量让父子进程使用相同编码，无需修改测试或业务逻辑。
- 仓库笔记通过目录、格式及归档三项校验；Git 差异检查通过。未执行真实钉钉业务读取或写入，在线权限与业务结果不属于本次离线验证范围。

## Consequences

- 收益：cc-switch 可以逐个发现官方产品 Skill，功能规则随参考文件一起分发；Python 脚本依赖可复现，并能从任意工作目录启动。
- 代价：后续同步需保留 uv 命令和依赖适配；各产品 Skills 有跨目录依赖，建议成套安装，在线命令仍取决于实际 DWS 版本与组织权限。
