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
- 【AI·人工修订】...

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

## AI / 人工来源标注

`Changes` 每条行内打标签，让评审者逐条看到来源；末尾"代码来源声明"做整体汇总。

| 标签 | 含义 |
|---|---|
| 【AI】 | AI 直接产出 |
| 【人工】 | 人工直接产出（方案决策 / 文档审阅 / 非 AI 直接写的代码）|
| 【AI·人工修订】 | AI 初稿 + 人工修改 |

整体声明示例：*代码实现全部 AI 生成，人工负责方案设计与评审把关。*

## 填写原则

- **直接写正文**：填实际内容时不要保留模板里的 placeholder 提示词（如"为什么要改："、"怎么实现："）。`Context` / `Description` 是纯段落，标题已说明该写什么，正文直接陈述。
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

用 `scripts/azdo_client.py` 的 `update-pr` 命令（封装了上述 PATCH，PAT 自动从本地配置读取，不进命令行与日志）：

```bash
# --repo 是顶层选项，必须放在子命令 update-pr 之前；非默认仓库时才需指定
# 从 stdin 读描述（推荐，配合 <<'EOF' heredoc，避免 markdown 反引号/$ 被转义）
python scripts/azdo_client.py --repo <repo> update-pr <prId> --description - <<'EOF'
<markdown 描述内容>
EOF

# 或从文件读（适合长描述）
python scripts/azdo_client.py update-pr <prId> --description-file desc.md

# 也可同时改标题
python scripts/azdo_client.py update-pr <prId> --title "feat(bpm): 新标题" --description-file desc.md
```

> 长描述含 markdown 反引号 / `$` / 换行，优先用 `--description -`（stdin + `<<'EOF'`）或 `--description-file`，**不要**塞进 `--description "..."` 字面值（同 `add-comment` 的长评论处理）。
