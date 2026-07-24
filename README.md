# my-skill

一个可由 `cc-switch` 发现并安装的多 Skill 仓库。每个顶层 Skill 目录独立维护其说明、脚本和依赖，避免不同 Skill 的 Python 依赖相互污染。

## 仓库结构

```text
my-skill/
├── <skill-name>/
│   ├── SKILL.md
│   ├── pyproject.toml  # 仅 Python Skill
│   ├── uv.lock         # 仅 Python Skill
│   ├── scripts/        # 可选
│   ├── references/     # 可选
│   └── assets/         # 可选
└── README.md
```

当前仓库是**多 Skill 仓库**：根目录不能放置 `SKILL.md`。每个待发布的 Skill 必须在自身目录中直接包含严格命名为 `SKILL.md` 的文件。

## cc-switch 识别规则

`cc-switch` 下载 GitHub 仓库或 ZIP 后，会从根目录递归扫描。任何**直接包含** `SKILL.md` 的目录都会被识别为一个 Skill；一旦识别到该目录，扫描不会继续进入其子目录。

因此：

- 仓库地址可使用 `https://github.com/owner/repo`、`http://github.com/owner/repo`、`owner/repo` 或 `https://github.com/owner/repo.git`。
- 默认分支是 `main`；下载失败时可能回退尝试 `master`。
- 多 Skill 仓库的根目录不要放 `SKILL.md`，否则子 Skill 不会继续被发现。
- `SKILL.md` 文件名区分大小写；`skill.md`、`Skill.md` 或仅有 `README.md` 都不会被识别。
- 安装目录使用 Skill 路径的最后一段，因此不能有两个 Skill 使用相同的最后一级目录名。
- 隐藏目录不会参与 ZIP 安装扫描；目录名也不能是 `.`、`..` 或隐藏目录名。

推荐的 `SKILL.md` frontmatter：

```markdown
---
name: example-skill
description: Use when handling the example workflow.
---
```

`name` 和 `description` 是 cc-switch 用于展示的关键元数据。缺失时目录仍可能被发现，但会退化为目录名和空描述。

## Python 与 uv 规范

所有包含可执行 Python 脚本的 Skill 都必须将运行依赖声明在自身的 `pyproject.toml`，并提交由 `uv lock` 生成的 `uv.lock`。禁止依赖系统 Python、Anaconda 环境或未记录的全局 `pip install`。

当前使用 Python 脚本的 Skill：

- `azure-devops-pr-code-review`
- `daily-work-summary`
- `gif-generator`
- `meeting-minutes-docx`
- `ssh`

### 日常命令

以 `<skill-dir>` 代替某个 Skill 目录：

```bash
# 根据锁文件创建或更新隔离环境；CI 中必须使用 --locked
uv sync --locked --project <skill-dir>

# 从任意工作目录执行脚本。--project 不会改变当前工作目录，
# 因此脚本路径也必须是完整的 Skill 路径。
uv run --project <skill-dir> python <skill-dir>/scripts/example.py --help
```

安装到 Claude Code 后，可将 `<skill-dir>` 写为 `~/.claude/skills/<skill-name>`；在本仓库开发时使用对应的仓库目录。

要求：

- 文档、脚本帮助文本和自动化命令使用 `uv run` 或 `uv sync`，不使用裸 `python` 或 `pip install`。
- 新增直接导入的第三方库时，先更新该 Skill 的 `pyproject.toml`，再执行 `uv lock --project <skill-dir>` 并提交新的 `uv.lock`。
- 只声明直接依赖；传递依赖交给锁文件解析，避免手工维护不一致的版本树。
- 不将 `.venv`、uv 缓存或系统解释器路径提交到仓库。

## 弃用警告零容忍

弃用警告代表未来的运行时兼容性风险。所有 Python Skill 的验证必须将**任何** Python 警告视为错误，不能因为当前命令仍可执行而忽略警告。

```bash
# 在 uv 锁定的环境中，导入即验证；任意警告都会使命令失败。
uv run --project <skill-dir> python -W error -c "import <top-level-module>"

# 运行单元测试时同样升级全部警告为错误。
uv run --project <skill-dir> python -W error -m unittest discover -s <skill-dir>/tests -v
```

例如，SSH Skill 必须使用 `uv.lock` 中受控的 Paramiko 版本，避免旧版 Paramiko 在导入时触发：

```text
cryptography.hazmat.decrepit.ciphers.algorithms.TripleDES ... will be removed
```

发现此类警告时，先升级或替换直接依赖并重新锁定，再运行带 `-W error` 的导入和测试验证；不要在代码中全局屏蔽警告。

## 发布前检查

- [ ] 分支为预期发布分支（通常为 `main`）。
- [ ] 每个 Skill 目录直接包含 `SKILL.md`，根目录没有 `SKILL.md`。
- [ ] 每个 `SKILL.md` 含有 `name` 和 `description` frontmatter。
- [ ] 各 Skill 的最后一级目录名唯一，且不是隐藏目录。
- [ ] Python Skill 的 `pyproject.toml` 与 `uv.lock` 已一并更新。
- [ ] 所有 Python 验证通过 `uv sync --locked` 与 `uv run` 执行。
- [ ] Python 导入和测试在 `python -W error` 下无警告。
- [ ] ZIP 分发时，解压后仍能直接看到各 Skill 的 `SKILL.md`。
