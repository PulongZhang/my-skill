# Agent Note: Jev API 参数 Skill 以原生 HTTP 契约为核心

Status: implemented

## Problem

用户要一个简洁的 Skill，说明怎样调用 Jev、请求需要哪些参数及各参数的作用。贴文包含模型原理、价格和 Agent 架构，但这些不是本次 Skill 的重点。仓库采用顶层目录分别发布 Skill。

## Decision

`jev-api/SKILL.md` 以 TypeSafe 官方 API 文档为准，说明端点、鉴权、三个顶层字段、三种问题类型及其 `instructions` 和 `criteria`，给出一个最小 cURL 请求及必要的返回字段解读。版本相关内容仅使用模型别名，并提示使用时核对官方文档。Skill 不添加 SDK 包装、脚本、依赖或原理教程。

## Alternatives considered

- **复制 TypeSafe 官方完整 Skill**：优势是厂商维护且内容全面；用户只要求调用参数，整套构建模式会淹没核心信息。
- **同时提供 Python 和 TypeScript SDK 教程**：优势是能直接套进常见项目；用户尚未指定语言，官方 SDK 细节也比原生 HTTP 契约更容易变化，因此本次只给通用 HTTP 调用。

## Consequences

- **收益**：Skill 可从请求字段直接找到参数作用和示例；不绑定具体编程语言。
- **代价**：使用 SDK 的开发者需要自行映射官方 SDK 方法；API 变化时仍需对照链接的活文档更新。
- **验证**：官方 API 文档与主要字段逐项核对；示例 JSON 能解析；skill-creator 的 `quick_validate.py` 通过。
