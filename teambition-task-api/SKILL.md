---
name: teambition-task-api
description: Use when querying or modifying Teambition tasks, work-time records, taskflow statuses, project metadata, or when a logged-in browser session must be reused through chrome-devtools or an F12 console script.
---

# Teambition 任务 API

## 概览

在 Chrome DevTools 已连接且 Teambition 页面已登录时，优先直接执行同源请求；否则生成供用户手动运行的 F12 控制台脚本。

所有写操作必须遵循同一顺序：

**查询现状 → 明确计划 → 用户授权 → 写前校验 → 修改 → 独立验证**

查询可直接执行。创建任务、登记工时、删除记录和修改任务状态均属于外部写操作，必须先取得用户明确授权。

## 执行决策

1. 调用 `mcp__chrome-devtools__list_pages` 查找已打开的 Teambition 页面。
2. 找到后先用 `mcp__chrome-devtools__select_page` 选中该页面；没有 Teambition 页面时用 `mcp__chrome-devtools__new_page` 新开页面，避免覆盖无关标签页。
3. `mcp__chrome-devtools__navigate_page` 只用于已选中的 Teambition 页面或空白页，以打开或刷新目标 URL。
4. 选中目标页面后检查 URL。如果包含 `/login`，立即停止并要求用户完成登录；登录前不得请求业务接口。
5. 已登录时，使用 `mcp__chrome-devtools__evaluate_script` 在页面内执行同源 `fetch`：
   - 查询操作可直接执行；
   - 创建、登记工时、删除、修改状态前必须展示具体计划并取得明确授权；
   - 每次脚本应自包含配置、请求 helper、操作逻辑和返回结果，不依赖上次执行留下的全局变量。
6. Chrome DevTools 不可用，或用户要求手动运行时，生成完整、自包含的 F12 IIFE：`(async () => { ... })();`：
   - 只读请求的 IIFE 只包含查询、完整性检查和结果报告，不得包含任何写接口；
   - 写请求的 IIFE 必须执行“运行时查询 → 校验 → 预览 → `window.confirm`（明确允许取消）→ 写入 → 独立验证”，用户取消时不得产生写入。
7. 始终让浏览器复用同源登录态。不得读取、打印或手工拼接 `Cookie` / `Authorization`。

接口路径、请求字段和可复用函数见 [`references/api.md`](references/api.md)。

## 标准流程 A：查询全部未完成任务

1. GraphQL 使用以下 TQL，按执行者查询组织内未完成任务：

   ```text
   isArchived = false AND isDone = false AND executorId = "用户ID"
   ```

2. 遍历所有分页：读取 `pageInfo.hasNextPage` 和 `pageInfo.endCursor`，将上一页 `endCursor` 作为下一页游标，直到 `hasNextPage=false`。
3. 如果 `hasNextPage=true` 但 `endCursor` 为空，立即报错并说明结果不完整，不得把已取得页面当作全量结果。
4. `project` 不是合法 TQL 字段。必须先完成组织级全分页，再按 GraphQL 节点的 `node.project.id`（整理后的结果字段为 `project.id`）在本地过滤项目。
5. 返回前再次排除 `isDeleted=true`、`isArchived=true` 或 `isDone=true` 的任务。
6. 报告查询范围、执行者、分页是否完整、项目过滤条件和最终任务数量。

不要改用未经验证的项目查询参数代替组织级全分页。

## 标准流程 B：补录工时

补录工时必须严格分为两个阶段。只读阶段结束后必须等待用户确认，不能在同一轮自动进入写入。

### 阶段 1：只读分析与计划

1. 查询目标日期范围内该用户每天已有的工时和工时记录。日期聚合必须包含归档任务，`filter.task` 使用空对象 `{}`，不得使用 `isArchived=false`，否则可能漏算并重复补录。
2. 查询现有任务并识别可复用项：已有准确任务 ID 时必须用 `tasks/bulk` 精确校验；没有准确 ID 时必须复用流程 A 的组织级全分页，再按 `project.id` 本地过滤。分页不完整时停止，禁止建议或执行创建。
3. 按任务 ID、准确标题、项目、SFC / 任务类型和实际工作内容识别精准唯一匹配。同名但 SFC 不同或候选不唯一时停止消歧，不得静默创建；已有工时不得覆盖或重复登记。
4. 输出计划，逐项列出：
   - 复用哪个现有任务及其 ID；
   - 哪些工作没有可复用任务，建议新增什么任务及类型；
   - 每天已有时长、目标时长、缺口和拟登记内容；
   - 哪些匹配不唯一或信息不足，需用户决定。
5. 等待用户明确确认计划以及其中的创建任务、登记工时等写操作。

### 阶段 2：运行时重查与执行

1. 获得授权后重新查询日期聚合和候选任务，不能直接使用阶段 1 的旧结果写入。日期聚合仍使用 `filter.task: {}`；准确 ID 必须再次用 `tasks/bulk` 校验，标题候选仍复用流程 A 的组织级全分页并按 `project.id` 本地过滤，分页不完整禁止创建。
2. 对复用任务逐项校验 ID、标题、项目、SFC、执行者、删除/归档/完成状态；SFC 必须纳入授权方案，变化时停止。发工时前再对所有最终任务 ID 做一次 bulk 预检，异常项不得写入。
3. 仅在没有精准唯一匹配、不是重名歧义，且运行时仍有工时缺口时创建任务。创建前在循环外一次性查询并校验任务列表、阶段和 SFC 元数据；阶段接口不得用于猜工作流状态。当前仅验证了 S1867 需求 SFC 的起始态 `904`；其他 SFC 必须停止，直到用户提供并确认属于实际 SFC 工作流且 `kind: start` 的状态配置。
4. 发 batch 前再做一次靠近写入的全日期聚合重查：缺口增加时停止，减少时只补更小缺口，已满时跳过。batch 响应和写后聚合都必须按本次记录 ID、任务、日期、时长及记录数逐项核对；每日总量严格等于目标才成功，超过目标须报告超额/并发冲突。
5. 运行时重查只能自动减少或跳过已授权操作。若结果要求增加工时、增加日期、新建任务、改变任务 ID/标题/类型、改变目标状态或扩大任何写入范围，必须输出修订计划并重新取得明确授权。
6. 同一任务涉及多天时，按任务汇总为一个请求中的多条 `times`，同时保留逐日缺口边界。
7. 写入后重新调用日期聚合，按日期独立核对总工时、记录数和新增记录；不能只检查登记接口返回值。
8. 逐项报告已创建任务、已登记工时、跳过项、失败项和验证结果。

复用任务或新建任务都不得默认标记完成。任务名和工时描述必须反映实际工作；方案、Demo、评审不得误写成正式开发。

F12 工时模板见 [`work-time-fill-template.js`](work-time-fill-template.js)。执行前替换并核验配置；模板内容必须符合主流程，不得绕过授权和校验。

## 标准流程 C：批量完成任务

1. 用户必须明确指定要完成的任务，优先使用任务 ID；仅给出模糊标题时先查询并消歧，不能直接写入。
2. 生成计划前按首次出现顺序稳定去重任务 ID；调用 bulk 前和发出 PUT 前都只使用该去重结果。重复输入只执行一次，并在报告中列明已合并的重复 ID。
3. 写前调用 `POST /work-time-server/api/tasks/bulk`，逐项核对：
   - 请求 ID 与返回任务 ID；
   - 名称与用户指定目标；
   - 项目；
   - SFC / `_scenariofieldconfigId`；
   - `isDeleted`、`isArchived`；
   - 当前 `isDone` 和 `_taskflowstatusId`。
4. 逐项确认目标状态 ID 属于任务实际 SFC 对应的工作流且 `kind: end`。当前仅验证了 S1867 需求 SFC 的终态 `907`；其他 SFC 必须停止，直到用户提供并确认属于实际 SFC 工作流且 `kind: end` 的状态配置，不得自动猜测，也不得复用需求终态。
5. 数量不符、ID 缺失、重名、项目不符、类型不符、已删除或已归档时停止对应项，并向用户报告。根据当前状态继续判断：
   - `isDone=true` 且状态正是目标终态：跳过并报告；
   - `isDone=true` 但处于其他终态：停止，请用户决定；
   - `isDone=false` 但状态 ID 已是目标终态：视为数据异常并停止。
6. 工作流项目只使用 `PUT /api/tasks/{id}/taskflowstatus` 修改状态。
7. 默认启用必填校验。只有用户明确授权跳过目标状态必填字段时，才可使用 `sfcRequiredValidateEnable: false`。
8. 发出 PUT 前再次稳定去重任务 ID；写后调用 `tasks/bulk`，逐项要求：
   - 返回了目标任务；
   - `isDone=true`；
   - `_taskflowstatusId` 等于目标终态 ID。
9. 不得使用 `PUT /api/tasks/{id}` 携带状态字段，也不得使用 `PUT /api/tasks/{id}/isDone` 完成工作流任务。

更新接口返回 HTTP 200/204 只说明请求被接收，不代表业务状态已经正确变更。

## 标准流程 D：检查工时涉及任务的状态

1. 查询目标日期范围的工时聚合。为避免漏报归档任务，`filter.task` 必须使用空对象 `{}`，不得使用 `isArchived=false`。
2. 仅从 `payload[].objects` 中提取 `objectType=task` 的 `_objectId`。
3. 对任务 ID 去重后，直接调用 `POST /work-time-server/api/tasks/bulk` 查询详情并按请求 ID 对账。
4. 不得与“当前未完成任务”集合取交集；有工时的任务可能已经完成、归档或删除。
5. 按以下互斥顺序分类，命中前一类后不得进入后续类别：
   1. 未知/缺失（bulk 未返回对应 ID）；
   2. 已删除；
   3. 已归档；
   4. 已完成；
   5. 未完成。

未知/缺失不能推断为未完成、删除或处理成功。

## 安全约束与失败处理

- 查询可直接执行；所有外部写操作必须获得用户明确授权。
- 不按模糊标题直接写入。标题重名、任务数量不符、项目或任务类型不一致时停止并请求消歧。
- 不把参与者登记工时等同于任务执行者，不代替他人完成任务。
- 不默认完成复用任务或新建任务；登记工时与完成任务是两个独立授权动作。
- 写接口 HTTP 200/204 不等于业务验证完成；必须通过独立查询检查最终状态。
- 批量操作部分失败后，逐项报告成功、失败和未知结果，并重新查询现状；只重试明确失败且仍需处理的项，不盲目整体重跑。
- 创建任务和登记工时接口没有幂等键。运行时查询、准确任务 ID 和每日缺口计算只能降低重复风险，不能承诺并发下绝对唯一。
- 删除不可恢复。删除任务或工时前，再次向用户展示并确认具体任务 ID 或工时记录 ID。
- 不因脚本曾执行失败就假设没有产生写入；重试前先重新查询。
- 认证失效、响应结构不符、分页不完整或 bulk 对账缺失时停止，不带着不确定状态继续写入。

## 快速参考

- API 细节：[`references/api.md`](references/api.md)
- S1867 速查：[`references/s1867.md`](references/s1867.md)
- F12 工时模板：[`work-time-fill-template.js`](work-time-fill-template.js)

主文件只规定执行顺序、授权边界和验证标准。具体请求体、接口返回字段及 S1867 固定 ID 从上述参考文件按需读取，不在此重复维护。
