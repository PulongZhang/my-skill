# cc-switch 可识别的 Skill 仓库规范

## 结论

`cc-switch` 识别 Skill 仓库时，并不依赖仓库级别的 manifest 文件。它会下载指定 GitHub 仓库的 ZIP 包，然后从仓库根目录开始递归扫描，凡是直接包含 `SKILL.md` 的目录，都会被识别为一个 Skill。

因此，一个可被 `cc-switch` 识别的 Skill 仓库只需要满足：

1. 仓库可以通过 GitHub 的 `owner/repo` 和分支下载。
2. 仓库中至少有一个目录直接包含名为 `SKILL.md` 的文件。
3. `SKILL.md` 中建议使用 Claude Code Skill 标准 frontmatter，至少包含 `name` 和 `description`。

## 支持的仓库输入格式

在 `cc-switch` 中添加仓库时，支持以下格式：

```text
https://github.com/owner/repo
http://github.com/owner/repo
owner/repo
https://github.com/owner/repo.git
```

分支默认使用：

```text
main
```

如果下载失败，后端会尝试 `main` 或 `master` 分支。

## 单 Skill 仓库结构

如果一个仓库只包含一个 Skill，可以把 `SKILL.md` 放在仓库根目录：

```text
my-skill-repo/
└── SKILL.md
```

这种情况下，整个仓库会被识别为一个 Skill。

## 多 Skill 仓库结构

如果一个仓库包含多个 Skill，不要在仓库根目录放 `SKILL.md`，否则扫描会在根目录停止，子目录中的 Skill 不会被继续发现。

推荐结构：

```text
my-skills-repo/
├── java-i18n/
│   ├── SKILL.md
│   └── references/
│       └── message-codes.md
├── bpm-debugging/
│   ├── SKILL.md
│   └── scripts/
│       └── inspect-process.py
└── speckit-review/
    ├── SKILL.md
    └── references/
        └── workflow.md
```

也可以把所有 Skill 放到统一目录下：

```text
my-skills-repo/
└── skills/
    ├── java-i18n/
    │   └── SKILL.md
    ├── bpm-debugging/
    │   └── SKILL.md
    └── speckit-review/
        └── SKILL.md
```

## SKILL.md 推荐格式

```markdown
---
name: java-i18n
description: Use when working on Java i18n messages, exception messages, validation text, or localized API responses.
---

# Java i18n

Use this skill when modifying user-visible Java text, validation messages, exception messages, or API response messages.

## Workflow

1. Identify user-visible text.
2. Replace hardcoded text with controlled i18n keys.
3. Add or update message properties.
4. Verify the language header behavior.
```

`cc-switch` 只解析 frontmatter 中的：

```yaml
name:
description:
```

如果缺少 frontmatter，目录仍可能被识别为 Skill，但显示效果会变差：

- `name` 会回退为目录名。
- `description` 会为空。

## 识别规则

### 什么会被识别为 Skill

任何直接包含 `SKILL.md` 的目录都会被识别为 Skill：

```text
good-skill/
└── SKILL.md
```

### 什么不会被识别

文件名不匹配时不会被识别：

```text
bad-skill/
├── README.md
├── skill.md
└── Skill.md
```

`cc-switch` 查找的是严格命名的：

```text
SKILL.md
```

## 扫描停止规则

当某个目录包含 `SKILL.md` 时，`cc-switch` 会把该目录识别为一个 Skill，并停止继续扫描该目录的子目录。

例如：

```text
repo/
├── SKILL.md
└── nested-skill/
    └── SKILL.md
```

这里通常只会识别根目录这个 Skill，`nested-skill` 不会继续被发现。

因此，多 Skill 仓库应避免在根目录放 `SKILL.md`。

## 安装目录规则

对于 GitHub 仓库中的 Skill，发现时的目录可能是多级路径，例如：

```text
skills/java-i18n/SKILL.md
```

但安装时最终使用的是路径最后一段：

```text
java-i18n
```

因此同一个仓库中应避免出现最后一段目录名相同的 Skill：

```text
repo/
├── backend/foo/SKILL.md
└── frontend/foo/SKILL.md
```

这种结构容易造成安装目录冲突。

## 目录命名建议

推荐：

```text
java-i18n
bpm-debugging
speckit-review
frontend-design
```

避免：

```text
.skill-name
..
.
foo/bar 作为安装名
```

安装目录名需要是单个普通路径段，不能是隐藏目录，也不能是 `.` 或 `..`。

## ZIP 安装规则

`cc-switch` 从 ZIP 安装 Skill 时，也会递归扫描解压目录，寻找直接包含 `SKILL.md` 的目录。

ZIP 示例：

```text
skills.zip
└── skills/
    ├── java-i18n/
    │   └── SKILL.md
    └── bpm-debugging/
        └── SKILL.md
```

如果 ZIP 中没有任何 `SKILL.md`，则不会安装任何 Skill。

ZIP 扫描时会跳过隐藏目录。

## 推荐仓库模板

```text
claude-skills/
├── java-i18n/
│   ├── SKILL.md
│   └── references/
│       └── message-codes.md
├── bpm-debugging/
│   └── SKILL.md
└── speckit-review/
    ├── SKILL.md
    └── references/
        └── review-checklist.md
```

其中每个 `SKILL.md` 使用如下模板：

```markdown
---
name: bpm-debugging
description: Use when debugging BPM workflow issues, process instance state, task assignment, form submission, or workflow engine behavior.
---

# BPM Debugging

Use this workflow when investigating BPM runtime issues.

## Steps

1. Reproduce the issue.
2. Inspect process instance state.
3. Check task assignment and form submission records.
4. Verify engine-side logs and domain events.
5. Apply the smallest fix and rerun verification.
```

## 最小可用示例

一个最小可被识别的仓库可以只有：

```text
my-skill/
└── SKILL.md
```

`SKILL.md`：

```markdown
---
name: my-skill
description: Use when handling tasks related to my custom workflow.
---

# My Skill

Follow this workflow:

1. Understand the request.
2. Inspect the relevant files.
3. Make the smallest safe change.
4. Verify the result.
```

## 检查清单

发布前建议确认：

- [ ] 仓库可通过 `https://github.com/owner/repo` 访问。
- [ ] 分支名正确，通常为 `main`。
- [ ] 每个 Skill 目录直接包含 `SKILL.md`。
- [ ] 多 Skill 仓库根目录没有 `SKILL.md`。
- [ ] `SKILL.md` frontmatter 包含 `name` 和 `description`。
- [ ] Skill 目录名不是隐藏目录，不以 `.` 开头。
- [ ] 不存在多个 Skill 使用相同的最后一级目录名。
- [ ] ZIP 分发时，解压后仍能看到每个 Skill 的 `SKILL.md`。

## 简短结论

能被 `cc-switch` 识别的 Skill 仓库，本质上就是一个 GitHub 仓库或 ZIP 包，其中包含一个或多个直接带有 `SKILL.md` 的目录。`SKILL.md` 建议遵循 Claude Code Skill 格式，只写 `name` 和 `description` frontmatter，并把详细说明放在正文或 `references/` 中。
