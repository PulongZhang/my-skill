---
name: daily-work-summary
description: Use when the user asks for a Chinese daily work summary, work log, day-end review, objective workplace recap, or a summary generated from daily Git commits. Supports extracting Git commit records with the bundled daily_git_commits.py script, then rewriting them into strict Chinese prose with no evaluative claims and a required three-item opening.
---

# Daily Work Summary

## Core Principle

Write an objective Chinese daily work summary that records what was handled, how it was handled, what was difficult, and what can be followed up, without claiming value, benefit, impact, or quality improvement.

When requirements conflict, use the user's confirmed口径: write limited context only. Explain the work's background, process position, scope, and relationship to other work, but do not evaluate outcomes.

## Git Commit Source

When the user asks to generate a daily summary from Git commits, use the bundled script `scripts/daily_git_commits.py` as the source extractor before writing the final summary.

Typical commands:

```bash
python scripts/daily_git_commits.py
python scripts/daily_git_commits.py --date 2026-04-13
python scripts/daily_git_commits.py --since 2026-04-01 --until 2026-04-13
python scripts/daily_git_commits.py --author zhangpulong --roots D:\WorkSpace D:\CETWorkSpace
```

Use script output as raw work material only. Do not paste the generated Git report as the final answer. Convert commit subjects, commit bodies, changed files, repositories, and diff stats into the required objective Chinese daily summary.

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
1、事项一
2、事项二
3、事项三

正文段落……
```

Rules:

- Start with exactly three numbered lines: `1、`, `2、`, `3、`.
- Put each numbered item on its own line.
- Each item text must be under 10 Chinese characters, excluding the number and punctuation.
- The opening three lines are the only allowed list or分点.
- After the opening, write continuous paragraphs only.
- Default to at least 300 Chinese characters when the user requests a detailed summary or gives enough work content.
- Do not use personal pronouns such as“我”“我们”“本人”.
- Do not use order-linking words such as“首先”“其次”“然后”“最后”.
- Do not use metaphors, exaggeration, slogans, or English except necessary technical terms.
- Do not overemphasize implementation details; keep technical details only when needed to identify the work.

## Content Coverage

Cover these elements in prose:

- Work content: completed handling, review, modification, checking, communication, or testing.
- Work method: tools, documents, code review, comparison, debugging, testing, verification, or record checking.
- Difficulties: unclear fields, missing data, inconsistent returns, dependency issues, import errors, failing tests, ambiguous rules, or incomplete inputs.
- Resolution: concrete actions taken, such as locating paths, comparing data, adjusting mapping, replacing wording, running checks, or rechecking outputs.
- Reflection: describe observed challenges, constraints, remaining gaps, and follow-up items, not value or benefit.

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
确保、提高、改善、增强、促进、优化、帮助、便于、有利于、成功、有效、高效、便捷、可靠、稳定、优质、使得、实现了、达到了
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

- The three opening items are separate lines and each item is under 10 Chinese characters.
- No extra lists appear after the opening.
- No forbidden exact words appear.
- No hidden value claims appear.
- No personal pronouns appear.
- No“首先/其次/然后/最后”appear.
- Reflection describes facts, constraints, challenges, and follow-up work instead of benefits or impact.

If any check fails, revise before output.
