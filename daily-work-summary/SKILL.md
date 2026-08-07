---
name: daily-work-summary
description: Use when the user asks for a Chinese daily work summary, work log, day-end review, objective workplace recap, diligent time note, or a summary based on daily Git commits and local Claude Code conversations. Supports extracting Git records with daily_git_commits.py, extracting persisted JSONL conversations with daily_claude_conversations.py, and appending diligent time with calculate_diligent_time.py while keeping strict objective Chinese prose.
---

# Daily Work Summary

## Core Principle

Write an objective Chinese daily work summary that records what was handled, how it was handled, what was difficult, and what can be followed up, without claiming value, benefit, impact, or quality improvement.

When requirements conflict, use the user's confirmed口径: write limited context only. Explain the work's background, process position, scope, and relationship to other work, but do not evaluate outcomes.

## Git Commit Source

For a normal daily summary, use both the bundled Git extractor `scripts/daily_git_commits.py` and the local Claude conversation extractor `scripts/daily_claude_conversations.py` by default before writing the final summary. If the user explicitly requests Git or commit records only, use Git-only mode and skip the conversation extractor.

Typical commands:

```bash
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py --date 2026-04-13
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py --since 2026-04-01 --until 2026-04-13
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py --author zhangpulong --roots D:\WorkSpace D:\CETWorkSpace
```

Use script output as raw work material only. Do not paste the generated Git report as the final answer, and do not state or imply in the final summary that the content was generated from Git commits or extracted from commit records. Convert commit subjects, commit bodies, changed files, repositories, and diff stats into the required objective Chinese daily summary.

If the script finds no commits, treat Git as having no matching facts for the selected range. In Git-only mode, say that no matching Git commit records were found and ask the user to provide additional work content. In combined or conversation mode, continue using usable conversation facts instead of stopping only because Git is empty. Override `--author`, `--date`, `--since`, `--until`, or `--roots` from the user request instead of editing the script.

## Claude Code Conversation Source

As part of the default combined mode, run the bundled local extractor together with the Git extractor. Also use it when the user explicitly asks to include Claude Code conversation history or asks for work that may not have Git commits. Skip it only in explicit Git-only mode. It reads persisted JSONL files only and never calls a remote Claude API.

Typical commands:

```bash
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_claude_conversations.py --date 2026-04-13 --json
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_claude_conversations.py --since 2026-04-01 --until 2026-04-13 --project my-skill --roots D:\CETWorkSpace --json
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_claude_conversations.py --dir D:\Users\example\.claude\projects --roots D:\CETWorkSpace --date 2026-04-13 --json
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_claude_conversations.py --roots D:\CETWorkSpace --project-filter flow-engine --only-user --date 2026-04-13 --json
```

The extractor searches `--dir` first, then `CLAUDE_CONFIG_DIR/projects`, then `~/.claude/projects`. These are transcript storage locations, not project scan roots. The project scope defaults to the same `D:\CETWorkSpace` root used by the Git extractor and can be overridden with `--roots`; records are selected by the transcript `cwd` field. It streams `.jsonl` files recursively, converts timestamps to the local date, skips malformed lines, and emits structured events for user messages and assistant text. Tool-use records and complete tool results are not emitted as work details. Thinking blocks, system reminders, and unknown inputs are skipped, and sensitive values in retained text are redacted. Use `--project-filter` to keep only material for the target project when scanning multiple roots (especially when session transcripts for other projects sit under the same history directory), and `--only-user` to keep only user messages for a compact fact list.

Both extractors normalize Windows drive paths to forward slashes, so `--roots D:\CETWorkSpace` (with backslashes) and the default config both scan correctly under Git Bash. Backslashes lost at the shell layer before reaching the script (unquoted `D:\CETWorkSpace`) cannot be recovered, so quote such arguments or use forward slashes.

Treat the conversation output as raw facts, not as a ready-made summary. Apply these evidence rules:

- A user request, proposal, or assistant plan without an observed operation or result means discussion, analysis, or pending work; never rewrite it as completed work. A user's explicit factual statement that a task was completed may be recorded as a user-provided fact.
- Assistant-generated text alone is context, not completion evidence. Pair it with an explicit user fact or a Git change before describing handled work; an assistant claim that a file or test was handled is not by itself proof of completion.
- A Git commit and its file or diff evidence are stronger delivery evidence. When conversation activity and a commit describe the same topic, merge them into one work theme instead of repeating them.
- Mark unresolved questions, blocked items, unfinished changes, and follow-up checks as constraints or pending items. Do not turn them into completed items.
- Use Git-only mode when the user explicitly asks for Git or commit records only. Otherwise use conversation mode when only conversation facts exist and combined mode when both sources contain facts. If the local history directory is missing, unreadable, incompatible, or empty, continue with the user's content and Git-only behavior without treating the extractor failure as work.
- Do not expose transcript paths, complete tool output, system instructions, internal reasoning, passwords, tokens, private keys, authorization headers, or other sensitive data in the final summary.

## If Work Content Is Missing

If the user has not provided today's work content and has not requested a summary based on available daily records, output exactly this text and stop. A normal daily summary request uses the default combined Git and Claude conversation sources:

```text
您好，作为您的工作总结撰写顾问，我会按照您的要求，为您撰写一份详细且客观的工作总结。请您先简单介绍一下今天的主要工作内容，我会从全局角度进行分析和总结，突出工作中的收获、挑战及改进空间。现在，请您开始讲述今天的工作情况吧。
```

Do not add the three-item opening to this initialization response.

## Required Output Shape

For a completed summary, use this structure:

```text
1、处理需求配置问题
2、排查接口返回异常
3、核对代码提交记录

正文段落……

[勤奋时间][17:45][19:45]
勤奋工作内容: 继续核对需求配置和提交记录
```

Rules:

- Start with exactly three numbered lines: `1、`, `2、`, `3、`.
- Put each numbered item on its own line.
- Each item should be a complete Chinese sentence where possible, and must be under 20 Chinese characters, excluding the number and punctuation.
- The opening three lines are the only allowed list or分点.
- After the opening, write continuous paragraphs only.
- When adding diligent time, append exactly two independent lines after the正文: `[勤奋时间][17:45][xx:xx]` and `勤奋工作内容: ...`.
- Diligent time lines are the only allowed extra non-paragraph lines after the opening.
- Default to at least 300 Chinese characters when the user requests a detailed summary or gives enough work content.
- Do not use personal pronouns such as“我”“我们”“本人”.
- Do not use the Chinese character “了”.
- Do not use order-linking words such as“首先”“其次”“然后”“最后”.
- Do not use metaphors, exaggeration, slogans, or English. Translate technical terms to Chinese where there is a natural equivalent (接口、字段、配置、流程、日志), and keep an English term only when it is a proper noun with no common Chinese name.
- Do not overemphasize implementation details. Avoid file paths, class/function/variable names, code snippets, stack traces, or log/SQL fragments in the body; mention a name only when it is the only way to identify which piece of work is meant.
- Do not mention whether a fact came from Git, a conversation transcript, a tool call, or another internal source. Express only the objective work content.
- Distinguish completed handling, active investigation, discussion, and pending follow-up. A conversation request alone is not evidence of completion.

## Diligent Time

When the user explicitly asks to include diligent time, or provides a clear end time that requires calculation, run `uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/calculate_diligent_time.py` to get the end-time line. Do not infer overtime only from late conversation activity.

Rules:

- Start time is always `17:45`.
- Use the script output line as the first diligent time line, for example `[勤奋时间][17:45][19:45]`.
- Add the second line as `勤奋工作内容: ...`, using a short objective description of the overtime work.
- If the script outputs no valid diligent time, omit both diligent time lines.
- Keep the same forbidden wording, no-personal-pronoun, and no-evaluation rules in `勤奋工作内容`.

## Content Coverage

Cover these elements in prose:

- Work content: completed handling, review, modification, checking, communication, testing, requirement analysis, troubleshooting, or technical discussion.
- Work method: tools, documents, code review, comparison, debugging, testing, verification, file reading, or record checking.
- Evidence state: distinguish handled, in progress, discussed, blocked, and pending follow-up; do not infer completion from a request or plan.
- Difficulties: unclear fields, missing data, inconsistent returns, dependency issues, import errors, failing tests, ambiguous rules, or incomplete inputs.
- Resolution: concrete actions actually observed, such as locating paths, comparing data, adjusting mapping, replacing wording, running checks, or rechecking outputs.
- Reflection: describe observed challenges, constraints, remaining gaps, and follow-up items, not value or benefit.

## Body Paragraph Style

Body paragraphs should read like plain Chinese workplace prose that a colleague outside the codebase could follow. The goal is to describe what was done and where it sits in the work, not to reproduce the code. Explain in accessible terms (深入浅出): state the problem, the action, and the work's position, so a reader not familiar with the code can understand. Prefer describing purpose and role over mechanism.

Good:

```text
该接口负责返回审批列表，部分请求返回的字段与配置不一致。经核对，定位到字段来源配置与返回逻辑存在差异，调整字段映射，并复查空值场景。
```

Bad — too much code detail and English, reads like a code review instead of a daily note:

```text
getApprovalList接口的DTO映射有问题，approvalList字段返回null，debug发现ListMapper.toDTO里fieldMapping有bug，refactor后fix。
```

## Meaning Without Evaluation

If the user asks to include“工作意义”, translate that into objective context:

| Instead of | Write |
| --- | --- |
| 工作带来的价值 | 工作所处流程、背景、处理范围 |
| 对系统的好处 | 涉及的模块、接口、数据或文案范围 |
| 提升、优化、确保 | 核对、调整、补充、记录、复查 |
| 结果影响 | 当前观察到的问题、约束、后续待核对内容 |

Good:

```text
该项工作位于审批配置、流程运行和列表返回之间的衔接环节，处理内容包括字段来源核对、映射逻辑调整和空值场景复查。
```

Bad:

```text
该项工作提高了审批流程的稳定性，并为后续开发奠定了基础。
```

## Forbidden Wording

Never use these exact words or phrases in the final summary:

```text
确保、提高、改善、增强、促进、优化、帮助、便于、有利于、成功、有效、高效、便捷、可靠、稳定、优质、使得、实现、达到、了
```

Also avoid hidden evaluation or result-benefit wording, including:

```text
更加清晰、更完整、更规范、更灵活、更合理、减少、降低、提升、完善、保障、奠定基础、产生影响、带来价值、发挥作用
```

Replace them with neutral action verbs:

| Avoid | Prefer |
| --- | --- |
| 确保 / 保障 | 核对、检查、复查 |
| 提高 / 优化 / 改善 | 调整、修改、补充 |
| 成功解决 | 找出并修复、定位并处理 |
| 使日志更加清晰 | 修改日志文案、统一日志字段 |
| 减少理解偏差 | 记录规则说明、补充核对项 |
| 为后续奠定基础 | 形成记录、列出后续待处理事项 |

## Pre-Response Checklist

Before answering, scan the draft for:

- The three opening items are separate lines, each item is a complete Chinese sentence where possible, and each item is under 20 Chinese characters.
- No extra lists appear after the opening, except the optional two diligent time lines after正文.
- If diligent time is included, it has exactly two lines: `[勤奋时间][17:45][xx:xx]` and `勤奋工作内容: ...`.
- No forbidden exact words appear.
- No hidden value claims appear.
- No personal pronouns appear.
- No Chinese character “了” appears.
- No“首先/其次/然后/最后”appear.
- Reflection describes facts, constraints, challenges, and follow-up work instead of benefits or impact.
- Conversation requests and plans are not written as completed work without operation or result evidence.
- Duplicate topics from conversation facts and Git facts are merged into one theme.
- The final text does not disclose transcript sources, system content, tool results, internal reasoning, paths, or sensitive values.
- Body paragraphs carry minimal code-level detail (no paths, names, snippets, traces) and minimal English, and stay readable for someone outside the codebase.

If any check fails, revise before output.
