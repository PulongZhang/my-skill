---
name: daily-work-summary
description: Use when the user asks for a Chinese daily work summary, work log, day-end review, objective workplace recap, diligent time note, or a summary generated from daily Git commits. Supports extracting Git commit records with daily_git_commits.py and appending diligent time from calculate_diligent_time.py while keeping strict objective Chinese prose.
---

# Daily Work Summary

## Core Principle

Write an objective Chinese daily work summary that records what was handled, how it was handled, what was difficult, and what can be followed up, without claiming value, benefit, impact, or quality improvement.

When requirements conflict, use the user's confirmed口径: write limited context only. Explain the work's background, process position, scope, and relationship to other work, but do not evaluate outcomes.

## Git Commit Source

When the user asks to generate a daily summary from Git commits, use the bundled script `scripts/daily_git_commits.py` as the source extractor before writing the final summary.

Typical commands:

```bash
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py --date 2026-04-13
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py --since 2026-04-01 --until 2026-04-13
uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/daily_git_commits.py --author zhangpulong --roots D:\WorkSpace D:\CETWorkSpace
```

Use script output as raw work material only. Do not paste the generated Git report as the final answer, and do not state or imply in the final summary that the content was generated from Git commits or extracted from commit records. Convert commit subjects, commit bodies, changed files, repositories, and diff stats into the required objective Chinese daily summary.

If the script finds no commits, say that no matching Git commit records were found for the selected date range, then ask the user to provide additional work content. Override `--author`, `--date`, `--since`, `--until`, or `--roots` from the user request instead of editing the script.

## If Work Content Is Missing

If the user has not provided today's work content and has not asked to generate from Git commits, output exactly this text and stop:

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

## Diligent Time

When the user asks to include diligent time, or when work content indicates overtime content should be recorded, run `uv run --project ~/.claude/skills/daily-work-summary python ~/.claude/skills/daily-work-summary/scripts/calculate_diligent_time.py` to get the end-time line.

Rules:

- Start time is always `17:45`.
- Use the script output line as the first diligent time line, for example `[勤奋时间][17:45][19:45]`.
- Add the second line as `勤奋工作内容: ...`, using a short objective description of the overtime work.
- If the script outputs no valid diligent time, omit both diligent time lines.
- Keep the same forbidden wording, no-personal-pronoun, and no-evaluation rules in `勤奋工作内容`.

## Content Coverage

Cover these elements in prose:

- Work content: completed handling, review, modification, checking, communication, or testing.
- Work method: tools, documents, code review, comparison, debugging, testing, verification, or record checking.
- Difficulties: unclear fields, missing data, inconsistent returns, dependency issues, import errors, failing tests, ambiguous rules, or incomplete inputs.
- Resolution: concrete actions taken, such as locating paths, comparing data, adjusting mapping, replacing wording, running checks, or rechecking outputs.
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
- Body paragraphs carry minimal code-level detail (no paths, names, snippets, traces) and minimal English, and stay readable for someone outside the codebase.

If any check fails, revise before output.
