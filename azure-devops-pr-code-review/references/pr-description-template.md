# PR 描述模板

向 Azure DevOps PR 写或补描述时遵循本模板，保证描述**结构统一、便于评审、可追溯 AI 与人工产出**。与 [code-review-format.md](code-review-format.md) 对称：本文件管"PR 描述怎么写"，那份管"评审评论怎么写"。

## 六段结构

```markdown
## Context 背景
<为什么做这个改动；直接写正文，不要加"为什么要改："等提示词>

## Description 说明
<怎么实现的；直接写正文，不要加"怎么实现："等提示词>

## Changes 变更内容
- 【AI】...
- 【人工】...

## Outside Changes 代码库外变更
- [ ] 无
- [ ] 数据库
- [ ] 配置
- [ ] 外部服务
- [ ] Pipeline
- [ ] 其他：
说明：

## Test & Risk 自测与风险
**自测结果**：
- [ ] 编译通过
- [ ] 测试通过
- [ ] 核心流程验证通过
**风险**：
**回滚方案**：
**Reviewer 重点关注**：
- 

## 代码来源声明
<汇总本 PR 的 AI / 人工产出比例>
```

## 创建 PR 时的背景/说明边界

用 `create-pr` 新建 PR 时，远端 PR 描述保留完整六段结构，但 `## Context 背景` 和 `## Description 说明` 的**标题保留、正文默认用占位文字 `人工编写中`**，不直接写入 AI 生成的正文。做法是：

1. 远端 PR 描述保留完整六段；其中 `Context 背景` / `Description 说明` 标题下正文写 `人工编写中` 占位，其余四段正常填写。
2. 在对话里另给这两段的参考正文，请人工确认后自行粘贴到 PR 页面，替换 `人工编写中` 占位。
3. 只有用户明确要求“直接写入”“强制写入”或“创建时填完整描述”时，才把 `Context` / `Description` 的真实正文一并写入 `create-pr --description`。

该边界只约束“创建 PR”的默认动作。用户明确要求补写或更新已有 PR 描述时，可按完整六段结构写入远端；注意 `update-pr --description` 是整体覆盖描述字段，更新前应保留既有段落，避免只传部分段落导致其他段落被覆盖。

## AI / 人工来源标注

`Changes` 每条行内打标签，让评审者逐条看到来源；末尾"代码来源声明"做整体汇总。

| 标签 | 含义 |
|---|---|
| 【AI】 | AI 产出 |
| 【人工】 | 人工产出（方案决策 / 文档审阅 / 非 AI 写的代码）|

来源标签只允许使用 `【AI】` 或 `【人工】`，不使用任何混合标签。

整体声明示例：*代码实现全部 AI 生成，人工负责方案设计与评审把关。*

## 填写原则

- **直接写正文**：填实际内容时不要保留模板里的 placeholder 提示词（如"为什么要改："、"怎么实现："）。`Context` / `Description` 是纯段落，标题已说明该写什么，正文直接陈述。
- **文字风格（深入浅出）**：描述用中文撰写，能用中文表达的概念不用英文；类名/方法名、配置项等标识符保留原文。背景、说明、风险用平实的话讲清，让评审者不熟悉这块改动也能快速读懂，不要堆大段代码贴片。
- `Test & Risk` 段的 **自测结果 / 风险 / 回滚方案 / Reviewer 重点关注** 是列表分组标签，保留。
- **单一职责**：一个 PR 只围绕一件事；后端不卡文件数硬门槛（controller / service / VO / 测试 / i18n×3 / 文档轻易超 12 文件），但每条 Changes 都应能追溯到同一目标。
- 标题用中文 Conventional Commit（`feat(bpm): ...` / `fix(auth): ...`）。
- 曾参考 lin-ui 的 Pull-Request 规范，但其面向前端组件库（文件数 < 12、`close #issue` 自动关单等不适用后端 + Azure DevOps），故采用本后端适配版。

## 更新远端 PR 描述

Azure DevOps REST 更新 PR 描述：

```
PATCH {repo_base}/pullrequests/{prId}?api-version=5.0
body: {"description": "<markdown 内容>"}
```

> **更新流程：先 GET 现状，合并后整体写回，禁止直接覆盖。** `PATCH description` 是整体覆盖整个描述字段。更新已有 PR 描述时必须：

1. **取现状**：`uv run --project ~/.claude/skills/azure-devops-pr-code-review python ~/.claude/skills/azure-devops-pr-code-review/scripts/azdo_client.py pr-detail <prId> --description` 获取当前完整 description 原文。
2. **合并**：在现有 description 基础上只改动需要更新的段落，**保留其余段落不变**；不要只传要改的部分，否则未提及的段落会被覆盖丢失。
3. **整体写回**：用合并后的完整 description 执行 `update-pr --description -` / `--description-file`。

只有新建 PR（`create-pr`）或用户明确要求"完全替换描述"时，才直接传一份全新描述；否则一律走"取现状 → 合并 → 写回"。

用 `scripts/azdo_client.py` 的 `update-pr` 命令（封装了上述 PATCH，PAT 自动从本地配置读取，不进命令行与日志）：

```bash
# --repo 是顶层选项，必须放在子命令 update-pr 之前；非默认仓库时才需指定
# 从 stdin 读描述（推荐，配合 <<'EOF' heredoc，避免 markdown 反引号/$ 被转义）
uv run --project ~/.claude/skills/azure-devops-pr-code-review python ~/.claude/skills/azure-devops-pr-code-review/scripts/azdo_client.py --repo <repo> update-pr <prId> --description - <<'EOF'
<markdown 描述内容>
EOF

# 或从文件读（适合长描述）
uv run --project ~/.claude/skills/azure-devops-pr-code-review python ~/.claude/skills/azure-devops-pr-code-review/scripts/azdo_client.py update-pr <prId> --description-file desc.md

# 也可同时改标题
uv run --project ~/.claude/skills/azure-devops-pr-code-review python ~/.claude/skills/azure-devops-pr-code-review/scripts/azdo_client.py update-pr <prId> --title "feat(bpm): 新标题" --description-file desc.md
```

> 长描述含 markdown 反引号 / `$` / 换行，优先用 `--description -`（stdin + `<<'EOF'`）或 `--description-file`，**不要**塞进 `--description "..."` 字面值（同 `add-comment` 的长评论处理）。
