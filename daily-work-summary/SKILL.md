---
name: daily-work-summary
description: Use when the user asks for a Chinese daily work summary, work log, day-end review, objective workplace recap, diligent time note, or a summary based on daily Git commits and local Claude Code or Codex conversations. Supports extracting Git records with daily_git_commits.py, persisted Claude Code JSONL with daily_claude_conversations.py, local Codex JSONL with daily_codex_conversations.py, and appending diligent time with calculate_diligent_time.py while keeping strict objective Chinese prose. Defaults to plain-language Chinese for leaders or non-technical readers and about 350 Chinese characters unless the user requests another length.
---

# Daily Work Summary

## Core Principle

Write an objective Chinese daily work summary that records what was handled, how it was handled, what was difficult, and what can be followed up, without claiming value, benefit, impact, or quality improvement.

When requirements conflict, use the user's confirmed口径: write limited context only. Explain the work's background, process position, scope, and relationship to other work, but do not evaluate outcomes.

## Git Commit Source

For a normal daily summary, use the bundled Git extractor `scripts/daily_git_commits.py`, the local Claude conversation extractor `scripts/daily_claude_conversations.py`, and the local Codex conversation extractor `scripts/daily_codex_conversations.py` by default before writing the final summary. If the user explicitly requests Git or commit records only, use Git-only mode and skip both conversation extractors. If the user names only Claude Code or only Codex, run only the requested conversation source unless combined records are also requested.

Determine the project roots once per summary run. Pass the exact same `--roots` values to the Git, Claude Code, and Codex extractors; never infer or substitute a different directory for one source. When `--roots` is omitted, all three scripts read the shared `scripts/daily_source_scope.py` default. Transcript storage options such as Claude/Codex `--dir` only locate history files and do not change the project roots used to select records by `cwd`.

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

All extractors normalize Windows drive paths to forward slashes, so `--roots D:\CETWorkSpace` (with backslashes) and the default config both scan correctly under Git Bash. Backslashes lost at the shell layer before reaching the script (unquoted `D:\CETWorkSpace`) cannot be recovered, so quote such arguments or use forward slashes.

Treat the conversation output as raw facts, not as a ready-made summary. Apply these evidence rules:

- A user request, proposal, or assistant plan without an observed operation or result means discussion, analysis, or pending work; never rewrite it as completed work. A user's explicit factual statement that a task was completed may be recorded as a user-provided fact.
- Assistant-generated text alone is context, not completion evidence. Pair it with an explicit user fact or a Git change before describing handled work; an assistant claim that a file or test was handled is not by itself proof of completion.
- A Git commit and its file or diff evidence are stronger delivery evidence. When conversation activity and a commit describe the same topic, merge them into one work theme instead of repeating them.
- Mark unresolved questions, blocked items, unfinished changes, and follow-up checks as constraints or pending items. Do not turn them into completed items.
- Use Git-only mode when the user explicitly asks for Git or commit records only. Otherwise use conversation mode when only conversation facts exist and combined mode when Git and one or more conversation sources contain facts. If a local history directory is missing, unreadable, incompatible, or empty, continue with the other usable sources without treating the extractor failure as work.
- Do not expose transcript paths, complete tool output, system instructions, internal reasoning, passwords, tokens, private keys, authorization headers, or other sensitive data in the final summary.

## Codex Conversation Source

Run `scripts/daily_codex_conversations.py` as part of the default combined mode and whenever the user asks to include Codex chats, Codex tasks, or work discussed in this app. It reads local persisted JSONL only and never calls a remote OpenAI API.

Typical commands:

```bash
python ~/.codex/skills/daily-work-summary/scripts/daily_codex_conversations.py --date 2026-08-28 --json
python ~/.codex/skills/daily-work-summary/scripts/daily_codex_conversations.py --since 2026-08-01 --until 2026-08-28 --project my-skill --roots D:\WorkSpace --json
python ~/.codex/skills/daily-work-summary/scripts/daily_codex_conversations.py --dir ~/.codex --roots D:\WorkSpace --project-filter my-skill --only-user --date 2026-08-28 --json
```

The extractor searches `--dir` first, then `CODEX_HOME`, then `~/.codex`. When given a Codex configuration directory it scans both `sessions` and `archived_sessions`; `--dir` may also name one session directory or one JSONL file. These locations identify transcript storage only. Project scope is selected from the session metadata `cwd` field and must use the same roots chosen for Git and Claude Code. Use `--project-filter` only to narrow records within that shared scope.

It emits only user `input_text` and assistant `output_text`. It skips developer and system instructions, environment/plugin context, reasoning, tool calls, tool arguments, tool outputs, token events, and unknown records. Retained text uses the same sensitive-value redaction and per-message length limit as the Claude extractor.

Apply the same evidence rules used for Claude conversations. User requests and assistant prose are context rather than completion proof unless paired with explicit user facts, observed operation results, or Git evidence. Merge duplicate work themes across Git, Claude Code, and Codex sources.

## If Work Content Is Missing

If the user has not provided today's work content and has not requested a summary based on available daily records, output exactly this text and stop. A normal daily summary request uses the default combined Git, Claude Code, and Codex conversation sources:

```text
您好，作为您的工作总结撰写顾问，我会按照您的要求，为您撰写一份详细且客观的工作总结。请您先简单介绍一下今天的主要工作内容，我会从全局角度进行分析和总结，突出工作中的收获、挑战及改进空间。现在，请您开始讲述今天的工作情况吧。
```

Do not add the three-item opening to this initialization response.

## Default Reader

Assume the reader is a leader or a non-technical colleague. That reader may know general concepts such as interface, configuration, log, database, deployment, and service registration, but may not know specific component names, implementation details, or internal identifiers.

Write for that reader:

- Explain what problem was handled, which workflow or system it belongs to, what action was taken, and what remains open.
- Translate technical actions into plain workplace Chinese. A general concept can stay; a specific implementation detail needs a short explanation or should be omitted.
- Use English only for necessary proper nouns or identifiers with no natural Chinese name. Do not use English to make a sentence look precise.

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
- Default to about 350 Chinese characters when the user gives enough work content. Treat this as a target, not a hard limit; follow an explicit user request for a shorter or longer summary.
- Do not use personal pronouns such as“我”“我们”“本人”.
- Do not use the Chinese character “了”.
- Do not use order-linking words such as“首先”“其次”“然后”“最后”.
- Do not use metaphors, exaggeration, or slogans. Use English only for necessary proper nouns or identifiers with no natural Chinese name.
- Do not overemphasize implementation details. Avoid file paths, class/function/variable names, code snippets, stack traces, or log/SQL fragments in the body; mention a name only when it is the only way to identify which piece of work is meant.
- Do not open the body with a total summary of the day, such as“今天的工作围绕……展开”, and do not label paragraphs with“部署方面”“业务方面”“配置方面”这一类分点标题. Each paragraph should directly describe one concrete work theme.
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

Body paragraphs should read like plain Chinese workplace prose for a leader or colleague outside the technical front line. Each paragraph should directly describe one concrete work theme, not announce a topic before the detail. State the problem, the action, and where the work sits, so a reader who knows general technical concepts but not implementation details can follow the point. Prefer purpose and role over mechanism.

Good:

```text
服务从旧运行环境迁到新版后，原来的注册方式和网络访问方式不能直接复用。部署说明按注册中心、网络访问和数据库脚本三部分整理，保留仍然沿用的配置，列出需要新增或替换的项和脚本顺序。
```

Bad — starts with a total summary and labels each paragraph like a report section:

```text
今天的工作围绕部署、配置和数据库展开。部署方面，调整注册配置；业务方面，核对错误返回；数据库方面，检查脚本顺序。
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
- The body does not start with a total summary of the day and does not label paragraphs with“XX方面”section headings.
- Each body paragraph directly describes one concrete work theme; the reader can follow the problem, action, and position without knowing implementation details.
- English appears only for necessary proper nouns or identifiers; general technical concepts use common Chinese wording.
- Reflection describes facts, constraints, challenges, and follow-up work instead of benefits or impact.
- Conversation requests and plans are not written as completed work without operation or result evidence.
- Duplicate topics from conversation facts and Git facts are merged into one theme.
- The final text does not disclose transcript sources, system content, tool results, internal reasoning, paths, or sensitive values.
- Body paragraphs carry minimal code-level detail (no paths, names, snippets, traces) and stay readable for someone outside the technical front line.

If any check fails, revise before output.
