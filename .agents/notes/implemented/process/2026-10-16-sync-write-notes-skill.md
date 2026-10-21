# Agent Note: 决策笔记 Skill 仅同步可安装内容

Status: implemented

## Problem

本仓库的 `write-notes-like-deepseek/` 是旧版整仓副本。来源仓库已在 `a571160` 合入可安装资源与维护资源分离的更新；继续复制仓库根目录会让安装结果携带维护脚本、配图和生成产物。

## Decision

将来源仓库 `skills/write-notes-like-deepseek/` 原样同步到本仓库顶层 `write-notes-like-deepseek/`，保持直接包含 `SKILL.md` 的多 Skill 发布布局。只保留 `SKILL.md`、`references/`、`templates/`、`scripts/` 和看板模板 `assets/agent-notes-board.html`；删除旧副本中不属于安装包的资源。校验器逐行识别历史豁免并跳过代码块的修复随来源版本保留。

后续同步仍从 `codex/local-divergences` 的合并结果取可安装目录。本轮接入主分支截至 `72573a5` 的简体中文与强制验证规则、看板修复、中文小节及链接校验兼容，不引入来源仓库维护用的语料导入器。

历史检索：现有三篇活跃笔记分别属于 Jev API、日报和 SSH 配置，与本次同步无关；没有需要更新或归档的同主题笔记。

## Alternatives considered

- 继续复制整个来源仓库：可以保留 README 展示和维护命令，但安装时仍混入与宿主无关的资源，与本次上游拆分目的冲突。
- 仅覆盖变更文件并保留旧附件：删除最少，但会留下失效的维护脚本和旧版 package.json，使用者仍难判断哪些命令适用于安装结果。

## Verification

本轮同步（2026-10-21）：来源为 `codex/local-divergences` 的合并提交 `2fda9f5`，包含主分支截至 `72573a5` 的更新。全部 21 个可安装文件与来源逐字节一致；从本仓库根目录执行下述三项校验，五篇活跃笔记与零条归档全部通过。来源仓库的导入、格式兼容及看板完整小节提取回归也通过。改动范围仅为七个 Skill 文件和本笔记。

- 首次拆分同步的来源为 `PulongZhang/write-notes-like-deepseek` 的 `codex/local-divergences` 分支、提交 `a571160`。当时目标安装目录的 21 个文件与来源文件集合一致，全部逐字节一致；旧版副本的 50 个文件事先核对与 `d78ffdf` 一致，没有额外定制。
- 从本仓库根目录执行 `npx tsx write-notes-like-deepseek/scripts/verify-agent-note-tree.ts`、`verify-agent-note-format.ts`、`verify-archived-agent-notes.ts`，四篇活跃笔记全部通过，归档零条。
- 临时安装测试以 `skills@1.7.1 add <本仓库> --skill write-notes-like-deepseek --agent codex claude-code` 选择本 Skill，覆盖默认链接与 `--copy` 两种方式；Codex / Claude 路径、安装目录边界、宿主校验、看板与归档均通过。测试沿用来源仓库的安装断言，Windows 下仅以 Node 直接启动 `npx-cli.js`。
- Git 差异检查通过，改动范围仅为目标 Skill 和本决策笔记。

## Consequences

- 收益：本仓库保持可直接发现的顶层 Skill 布局，安装目录与来源发布内容一致，并保留本地校验修复。
- 代价：README 配图、语料导入和配图导出命令留在来源仓库维护；安装目录不再提供旧 package.json 或预生成 board.html。宿主 npm scripts 与 CI 仍须使用者按实际安装路径配置。
