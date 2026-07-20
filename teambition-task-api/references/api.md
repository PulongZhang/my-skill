# Teambition API 参考

本页只记录接口契约和可复用代码。执行顺序、授权边界和 F12 兜底流程见主 [`SKILL.md`](../SKILL.md)。项目固定 ID 见 [`s1867.md`](s1867.md)。

## 快速索引

| 操作 | 接口 | 关键要求 |
|---|---|---|
| 全量查询任务 | `POST /api/v2/graphql` | 遍历 `hasNextPage` / `endCursor`；项目在本地过滤 |
| 按日期聚合工时 | `POST /work-time-server/api/work-time/aggregation/dates` | 需要工时服务头 |
| 批量查任务 | `POST /work-time-server/api/tasks/bulk` | 需要工时服务头；按请求 ID 对账 |
| 批量登记工时 | `POST /work-time-server/api/work-time/batch?...` | `time` 单位为毫秒 |
| 删除工时记录 | `DELETE /work-time-server/api/work-time/{recordId}` | 不可恢复，必须明确授权 |
| 创建任务 | `POST /api/tasks` | 工作流状态必须是起始态 |
| 更新工作流状态 | `PUT /api/tasks/{id}/taskflowstatus` | 唯一允许的工作流状态更新接口 |
| 删除任务 | `DELETE /api/tasks/{id}` | 不可恢复，必须明确授权 |

## 同源请求与 Chrome DevTools

在已登录的 Teambition 页面执行相对路径 `fetch`，让浏览器复用同源登录态。不得读取、打印或手工拼接 `Cookie` / `Authorization`。`/work-time-server/` 下的接口还必须带 `x-organization-id` 和 `x-user-id`。

Chrome DevTools 登录门禁：

1. 用 `mcp__chrome-devtools__list_pages` 找到受控页面；必要时用 `mcp__chrome-devtools__navigate_page` 打开 Teambition 同源地址。
2. 若页面仍在 `/login`，停止，等待用户完成登录，不尝试提取认证信息。
3. 登录后，把完整函数声明传给 `mcp__chrome-devtools__evaluate_script`。每次调用都自包含配置和 helper，不依赖前一次调用留下的全局变量。

`evaluate_script` 使用 `async () => { ... }` 函数声明；F12 Console 则使用完整 IIFE：`(async () => { ... })();`。两者都必须把配置、请求封装、查询和返回值放在同一次执行中。

## GraphQL：全量查询执行者的未完成任务

`project` 不是合法 TQL 字段。必须先完成组织级全分页，再按 `node.project.id` 本地过滤；最终还要排除删除、归档和完成任务。以下函数可直接传给 `mcp__chrome-devtools__evaluate_script`，返回值仅包含可 JSON 序列化数据：

```javascript
async () => {
  const organizationId = "组织ID";
  const userId = "执行者用户ID";
  const currentUserId = "当前登录用户ID";
  const projectId = "目标项目ID"; // 设为 "" 时不过滤项目

  async function api(path, { method = "GET", body, expectArrayPayload = false, allowEmptySuccess = false } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const isWorkTimeService = path.startsWith("/work-time-server/");
    if (isWorkTimeService) {
      headers["x-organization-id"] = organizationId;
      headers["x-user-id"] = currentUserId;
    }

    const response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${method} ${path} -> HTTP ${response.status}`);
    }

    if (!text) {
      if (allowEmptySuccess) return null;
      throw new Error(`${method} ${path} 成功响应为空`);
    }
    let data;
    try { data = JSON.parse(text); } catch {
      throw new Error(`${method} ${path} 返回非 JSON 内容，可能发生认证重定向`);
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new Error(`${method} ${path} 返回结构异常`);
    }
    if (isWorkTimeService) {
      if (data.ok !== true) throw new Error(`${method} ${path} 返回 ok !== true`);
      if (expectArrayPayload && !Array.isArray(data.payload)) {
        throw new Error(`${method} ${path} 返回的 payload 不是数组`);
      }
    }
    return data;
  }

  const query = `
    query TasksByOrg($organizationId: ID!, $tql: String, $after: String) {
      organization(organizationId: $organizationId) {
        tasks(first: 40, tql: $tql, after: $after) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            content
            isDeleted
            isArchived
            isDone
            project { id name }
            executorUser { userId name }
            projectSfc { icon originalId }
            tasklistId
            stageId
            sfcId
            startDate
            dueDate
          }
        }
      }
    }
  `;
  const tql = `isArchived = false AND isDone = false AND executorId = "${userId}"`;
  const nodes = [];
  const seenCursors = new Set();
  const seenTaskIds = new Set();
  let after = null;
  let hasNextPage = true;

  while (hasNextPage) {
    const result = await api("/api/v2/graphql", {
      method: "POST",
      body: { query, variables: { organizationId, tql, after } },
    });
    if (result.errors != null) {
      if (!Array.isArray(result.errors) || result.errors.length > 0) {
        throw new Error(`GraphQL 查询失败: ${JSON.stringify(result.errors)}`);
      }
    }

    const page = result.data?.organization?.tasks;
    if (!page || typeof page !== "object" || Array.isArray(page)) {
      throw new Error("GraphQL 返回缺少合法 organization.tasks");
    }
    if (!Array.isArray(page.nodes)) throw new Error("organization.tasks.nodes 不是数组");
    if (!page.pageInfo || typeof page.pageInfo !== "object" || Array.isArray(page.pageInfo)) {
      throw new Error("organization.tasks.pageInfo 不是对象");
    }
    for (const node of page.nodes) {
      if (!node || typeof node !== "object" || Array.isArray(node) || typeof node.id !== "string" || !node.id) {
        throw new Error("GraphQL 返回畸形任务节点");
      }
      if (seenTaskIds.has(node.id)) throw new Error(`GraphQL 跨页重复任务 ID ${node.id}`);
      seenTaskIds.add(node.id);
      nodes.push(node);
    }

    const { hasNextPage: nextPage, endCursor } = page.pageInfo;
    if (typeof nextPage !== "boolean") throw new Error("pageInfo.hasNextPage 缺失或不是 boolean");
    if (endCursor != null && typeof endCursor !== "string") throw new Error("pageInfo.endCursor 类型异常");
    hasNextPage = nextPage;
    if (hasNextPage) {
      if (!endCursor) throw new Error("hasNextPage=true 但 endCursor 为空，查询结果不完整");
      if (endCursor === after || seenCursors.has(endCursor)) throw new Error("GraphQL 游标重复或无进展");
      seenCursors.add(endCursor);
    }
    after = endCursor ?? null;
  }

  for (const node of nodes) {
    for (const field of ["isDeleted", "isArchived", "isDone"]) {
      if (typeof node?.[field] !== "boolean") {
        throw new Error(`任务 ${node?.id ?? "<unknown>"} 的 ${field} 缺失或不是 boolean`);
      }
    }
  }

  return nodes
    .filter(node =>
      (!projectId || node.project?.id === projectId) &&
      node.isDeleted === false && node.isArchived === false && node.isDone === false
    )
    .map(node => ({
      id: node.id,
      content: node.content,
      project: node.project ?? null,
      executorUser: node.executorUser ?? null,
      projectSfc: node.projectSfc ?? null,
      tasklistId: node.tasklistId ?? null,
      stageId: node.stageId ?? null,
      sfcId: node.sfcId ?? null,
      startDate: node.startDate ?? null,
      dueDate: node.dueDate ?? null,
      isDeleted: node.isDeleted,
      isArchived: node.isArchived,
      isDone: node.isDone,
    }));
}
```

## 工时接口

### 请求契约

| 操作 | 请求 | 关键返回字段与判定 |
|---|---|---|
| 日期聚合 | `POST /work-time-server/api/work-time/aggregation/dates`；body 见下例 | `ok`、`payload[].date`、`workTime`、`count`、`objects[]`；对象含 `_id`、`objectType`、`_objectId`、`workTime` |
| 批量任务详情 | `POST /work-time-server/api/tasks/bulk`；body：`{"taskIds":["任务ID"]}` | 实际任务数组位于 `payload[]`；每项至少读取 `_id`、`content`、`_projectId`、`_scenariofieldconfigId`、`isDeleted`、`isArchived`、`isDone`、`_taskflowstatusId`；必须与请求 ID 对账 |
| 批量登记 | `POST /work-time-server/api/work-time/batch?from=task&taskId={任务ID}&_userId={用户ID}`；body 见下例 | `payload[]` 数量必须等于 `times`；逐条核对唯一非空 `_id`、`objectType=task`、`_objectId`、`date`、`workTime`，保存记录 ID；写后用日期聚合按记录核对 |
| 删除工时 | `DELETE /work-time-server/api/work-time/{recordId}` | 要求 `ok=true` 且 `payload.isDeleted=true`；不可恢复 |

以上接口都需要工时服务头。工时服务响应必须是对象、`ok === true`，需要列表的接口还必须有数组型 `payload`；认证重定向返回 HTML、`ok:false` 或结构异常时必须抛错，不得按空结果继续。通用 `api` helper 的 `allowEmptySuccess` 默认必须为 `false`；只有已知允许 204/空成功响应的调用者才能显式设为 `true`，并且仍须执行独立查询验证。`tasks/bulk` 的实际响应契约为 `{ ok, payload: Task[] }`，任务数组位于 `payload[]`。返回后必须按请求 ID 对账：响应中缺失的 ID 状态是“未知”，不能按未完成、已删除或已成功处理推断。

可复制的对账 helper：

```javascript
function reconcileBulkTasks(requestedIds, response) {
  function requireTeambitionId(value, label) {
    if (typeof value !== "string" || value !== value.trim() || !/^[a-f0-9]{24}$/i.test(value)) {
      throw new Error(`${label} 必须是无首尾空白的 24 位十六进制 ID`);
    }
    return value;
  }
  if (!response || typeof response !== "object" || Array.isArray(response)) {
    throw new Error("tasks/bulk 响应必须是对象");
  }
  if (response.ok !== true || !Array.isArray(response.payload)) {
    throw new Error("tasks/bulk 响应必须满足 ok === true 且 payload 为数组");
  }

  const uniqueRequestedIds = [...new Set(requestedIds)];
  uniqueRequestedIds.forEach((id, index) => requireTeambitionId(id, `requestedIds[${index}]`));
  const requestedSet = new Set(uniqueRequestedIds);
  const byId = new Map();
  response.payload.forEach((task, index) => {
    if (!task || typeof task !== "object" || Array.isArray(task)) {
      throw new Error(`tasks/bulk payload[${index}] 不是对象`);
    }
    requireTeambitionId(task._id, `tasks/bulk payload[${index}]._id`);
    if (!requestedSet.has(task._id)) throw new Error(`tasks/bulk 返回未请求 ID ${task._id}`);
    if (byId.has(task._id)) throw new Error(`tasks/bulk 重复返回 ID ${task._id}`);
    for (const field of ["_projectId", "_scenariofieldconfigId", "_taskflowstatusId"]) {
      requireTeambitionId(task[field], `任务 ${task._id}.${field}`);
    }
    for (const field of ["isDeleted", "isArchived", "isDone"]) {
      if (typeof task[field] !== "boolean") {
        throw new Error(`任务 ${task._id} 的 ${field} 缺失或不是 boolean`);
      }
    }
    byId.set(task._id, task);
  });

  return uniqueRequestedIds.map(requestedId => {
    const task = byId.get(requestedId);
    return {
      requestedId,
      found: task !== undefined,
      content: task?.content ?? null,
      projectId: task?._projectId ?? null,
      scenariofieldconfigId: task?._scenariofieldconfigId ?? null,
      isDeleted: task?.isDeleted ?? null,
      isArchived: task?.isArchived ?? null,
      isDone: task?.isDone ?? null,
      taskflowstatusId: task?._taskflowstatusId ?? null,
    };
  });
}
```

`requestedIds` 会按首次出现顺序稳定去重。缺失 ID 仍会得到一条 `found: false` 的结果，其余字段为 `null`；不得从其他集合补猜状态，也不得用 `!value` 把缺失布尔字段归为未完成。

每日总工时与工时涉及任务状态查询都必须包含归档任务，因此通用日期聚合使用 `"task": {}`。只有用户明确要求排除归档任务时，才添加归档过滤。聚合响应必须严格校验：每个日期行具有经真实日历回验的 ISO 日期、非负安全整数 `workTime` / `count`、数组型 `objects`，且日期不得重复、`count === objects.length`、object 的 `workTime` 合计严格等于日期 `workTime`；每个 object 必须有无首尾空白的 24 位十六进制 `_id`、非空 `objectType` 和非负安全整数 `workTime`，task 类型还必须有同格式 `_objectId`。畸形行不得静默跳过。

日期聚合请求：

```json
{
  "startDate": "2026-07-01",
  "endDate": "2026-07-05",
  "userIds": ["用户ID"],
  "filter": {
    "project": {},
    "task": {},
    "customfield": {}
  }
}
```

登记工时请求；`time` 单位为毫秒，可在一次请求的 `times` 中按日期提交多条。成功响应的 `payload[]` 必须与 `times` 一一对应，并包含可核验的 `_id`、`objectType`、`_objectId`、`date`、`workTime`；字段缺失、记录数不符或记录 ID 重复时视为失败/未知。写后日期聚合必须按这些记录 ID 核对任务、日期和时长，同时核对 `count` 与新增记录数。每日总量只有严格等于目标值才成功，超过目标值必须报告超额或并发冲突：

```json
{
  "_userId": "用户ID",
  "_objectId": "任务ID",
  "objectType": "task",
  "tagIds": [],
  "times": [
    { "date": "2026-07-01", "time": 3600000, "description": "实际工作说明" }
  ]
}
```

### 查询工时涉及任务的状态

只从日期聚合 `payload[].objects` 中提取 `objectType=task` 的 `_objectId`，去重后直接调用 `tasks/bulk`。不要与“当前未完成任务”集合取交集，因为工时涉及的任务可能已经完成。

以下函数可独立传给 `mcp__chrome-devtools__evaluate_script`；F12 Console 使用时仅把整个函数外包为完整 IIFE：`(async () => { ... })();`。

```javascript
async () => {
  const organizationId = "组织ID";
  const currentUserId = "当前登录用户ID";
  const workTimeUserId = "工时所属用户ID";
  const startDate = "2026-07-01";
  const endDate = "2026-07-05";

  async function api(path, { method = "GET", body, expectArrayPayload = false, allowEmptySuccess = false } = {}) {
    const headers = {};
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const isWorkTimeService = path.startsWith("/work-time-server/");
    if (isWorkTimeService) {
      headers["x-organization-id"] = organizationId;
      headers["x-user-id"] = currentUserId;
    }
    const response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: "same-origin",
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(`${method} ${path} -> HTTP ${response.status}`);
    }

    if (!text) {
      if (allowEmptySuccess) return null;
      throw new Error(`${method} ${path} 成功响应为空`);
    }
    let data;
    try { data = JSON.parse(text); } catch {
      throw new Error(`${method} ${path} 返回非 JSON 内容，可能发生认证重定向`);
    }
    if (!data || typeof data !== "object" || Array.isArray(data)) {
      throw new Error(`${method} ${path} 返回结构异常`);
    }
    if (isWorkTimeService) {
      if (data.ok !== true) throw new Error(`${method} ${path} 返回 ok !== true`);
      if (expectArrayPayload && !Array.isArray(data.payload)) {
        throw new Error(`${method} ${path} 返回的 payload 不是数组`);
      }
    }
    return data;
  }

  function requireTeambitionId(value, label) {
    if (typeof value !== "string" || value !== value.trim() || !/^[a-f0-9]{24}$/i.test(value)) {
      throw new Error(`${label} 必须是无首尾空白的 24 位十六进制 ID`);
    }
    return value;
  }

  function normalizeApiDate(value, label) {
    if (typeof value !== "string") throw new Error(`${label} 不是字符串`);
    const match = value.match(/^(\d{4}-\d{2}-\d{2})(?:T00:00:00(?:\.000)?Z)?$/);
    if (!match) throw new Error(`${label} 不是 YYYY-MM-DD 或 UTC 零点时间戳`);
    const date = match[1];
    const parsed = new Date(`${date}T00:00:00.000Z`);
    if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) {
      throw new Error(`${label} 不是有效日期`);
    }
    return date;
  }

  function reconcileBulkTasks(requestedIds, response) {
    if (!response || typeof response !== "object" || Array.isArray(response)) {
      throw new Error("tasks/bulk 响应必须是对象");
    }
    if (response.ok !== true || !Array.isArray(response.payload)) {
      throw new Error("tasks/bulk 响应必须满足 ok === true 且 payload 为数组");
    }
    const uniqueRequestedIds = [...new Set(requestedIds)];
    uniqueRequestedIds.forEach((id, index) => requireTeambitionId(id, `requestedIds[${index}]`));
    const requestedSet = new Set(uniqueRequestedIds);
    const byId = new Map();
    response.payload.forEach((task, index) => {
      if (!task || typeof task !== "object" || Array.isArray(task)) {
        throw new Error(`tasks/bulk payload[${index}] 不是对象`);
      }
      requireTeambitionId(task._id, `tasks/bulk payload[${index}]._id`);
      if (!requestedSet.has(task._id)) throw new Error(`tasks/bulk 返回未请求 ID ${task._id}`);
      if (byId.has(task._id)) throw new Error(`tasks/bulk 重复返回 ID ${task._id}`);
      for (const field of ["_projectId", "_scenariofieldconfigId", "_taskflowstatusId"]) {
        requireTeambitionId(task[field], `任务 ${task._id}.${field}`);
      }
      for (const field of ["isDeleted", "isArchived", "isDone"]) {
        if (typeof task[field] !== "boolean") {
          throw new Error(`任务 ${task._id} 的 ${field} 缺失或不是 boolean`);
        }
      }
      byId.set(task._id, task);
    });
    return uniqueRequestedIds.map(requestedId => {
      const task = byId.get(requestedId);
      return {
        requestedId,
        found: task !== undefined,
        content: task?.content ?? null,
        projectId: task?._projectId ?? null,
        scenariofieldconfigId: task?._scenariofieldconfigId ?? null,
        isDeleted: task?.isDeleted ?? null,
        isArchived: task?.isArchived ?? null,
        isDone: task?.isDone ?? null,
        taskflowstatusId: task?._taskflowstatusId ?? null,
      };
    });
  }

  const aggregation = await api("/work-time-server/api/work-time/aggregation/dates", {
    method: "POST",
    expectArrayPayload: true,
    body: {
      startDate,
      endDate,
      userIds: [workTimeUserId],
      filter: { project: {}, task: {}, customfield: {} },
    },
  });
  const seenDates = new Set();
  const seenRecordIds = new Set();
  const normalizedDays = [];
  for (const [index, day] of aggregation.payload.entries()) {
    if (!day || typeof day !== "object" || Array.isArray(day)) throw new Error(`日期聚合 payload[${index}] 不是对象`);
    const date = normalizeApiDate(day.date, `日期聚合 payload[${index}].date`);
    if (seenDates.has(date)) throw new Error(`日期聚合日期重复 ${date}`);
    seenDates.add(date);
    for (const field of ["workTime", "count"]) {
      if (!Number.isSafeInteger(day[field]) || day[field] < 0) throw new Error(`${date}.${field} 非法`);
    }
    if (!Array.isArray(day.objects)) throw new Error(`${date}.objects 不是数组`);
    if (day.count !== day.objects.length) throw new Error(`${date}.count 与 objects 数量不符`);
    let objectWorkTime = 0;
    for (const [objectIndex, item] of day.objects.entries()) {
      if (!item || typeof item !== "object" || Array.isArray(item)) throw new Error(`${date}.objects[${objectIndex}] 不是对象`);
      requireTeambitionId(item._id, `${date}.objects[${objectIndex}]._id`);
      if (seenRecordIds.has(item._id)) throw new Error(`工时记录 ID 重复 ${item._id}`);
      seenRecordIds.add(item._id);
      if (typeof item.objectType !== "string" || !item.objectType.trim()) throw new Error(`工时记录 ${item._id} 缺少 objectType`);
      if (!Number.isSafeInteger(item.workTime) || item.workTime < 0) throw new Error(`工时记录 ${item._id}.workTime 非法`);
      if (item.objectType === "task") requireTeambitionId(item._objectId, `工时记录 ${item._id}._objectId`);
      objectWorkTime += item.workTime;
    }
    if (objectWorkTime !== day.workTime) throw new Error(`${date}.workTime 与 objects 合计不符`);
    normalizedDays.push({ ...day, date });
  }
  const taskIds = [...new Set(normalizedDays.flatMap(day => day.objects)
    .filter(item => item.objectType === "task").map(item => item._objectId))];
  const bulk = taskIds.length === 0
    ? { ok: true, payload: [] }
    : await api("/work-time-server/api/tasks/bulk", {
        method: "POST",
        expectArrayPayload: true,
        body: { taskIds },
      });
  const tasks = reconcileBulkTasks(taskIds, bulk);

  return {
    taskIds,
    completed: tasks.filter(task => task.found === true && task.isDeleted === false && task.isArchived === false && task.isDone === true),
    incomplete: tasks.filter(task => task.found === true && task.isDeleted === false && task.isArchived === false && task.isDone === false),
    archived: tasks.filter(task => task.found === true && task.isDeleted === false && task.isArchived === true),
    deleted: tasks.filter(task => task.found === true && task.isDeleted === true),
    unknown: tasks.filter(task => task.found === false),
  };
}
```

日期聚合在真实环境中曾返回 `YYYY-MM-DD`，也曾返回 `YYYY-MM-DDT00:00:00.000Z`。查询代码只接受这两类可证明等价的格式，并统一归一化为 `YYYY-MM-DD`；不要对任意字符串直接 `slice(0, 10)`。

分类顺序为未知/缺失、已删除、已归档、已完成、未完成，命中前一类后不再进入后续类别。

## 创建任务

`POST /api/tasks`：

```json
{
  "content": "任务标题",
  "_tasklistId": "任务列表ID",
  "_stageId": "阶段ID",
  "_taskflowstatusId": "起始工作流状态ID",
  "_scenariofieldconfigId": "场景配置ID",
  "_executorId": "执行者ID",
  "priority": 0,
  "note": "可选备注"
}
```

`_scenariofieldconfigId` 必须与工作流匹配，`_taskflowstatusId` 必须使用 `kind: start` 的起始状态，不能在创建时使用中间态或终态。当前文档只有 S1867 需求 SFC 的起始态 `904` 和终态 `907` 经过验证；其他 SFC 的自动创建或完成必须停止，除非用户提供并确认了属于实际 SFC 工作流且分别为 `kind: start` / `kind: end` 的状态配置。不得猜测状态，也不得编造通用状态发现接口；`GET /api/stages` 返回阶段，不是工作流状态列表。

创建前应在循环外一次性查询任务列表、阶段和 SFC 元数据。响应只接受明确的直接数组，或对象中唯一且字段名已知的数组；结构不明时停止。创建响应应包含任务 `_id` 和 `content`，随后通过 `tasks/bulk` 加 GraphQL/明确任务详情独立校验标题、项目、任务列表、阶段、执行者、SFC、未删除/未归档、`isDone=false` 和起始状态；任何字段未能从查询结果确认时不得登记工时。

## 更新工作流状态

工作流项目只允许调用：

```http
PUT /api/tasks/{id}/taskflowstatus
```

```json
{
  "_taskflowstatusId": "目标终态ID",
  "_scenariofieldconfigId": "任务实际场景配置ID",
  "sfcRequiredValidateEnable": true,
  "persistentValidatorEnable": false,
  "disableRequiredCfIds": []
}
```

### 写前校验

生成批量状态变更计划前，先按首次出现顺序稳定去重任务 ID；调用 `POST /work-time-server/api/tasks/bulk` 前和发出 `PUT` 前再次使用去重后的 ID 集合，确保重复输入只执行一次并报告。随后对每个明确任务 ID 校验：

| 必检项 | 要求 |
|---|---|
| ID / 名称 | 与用户指定目标一致；重名或数量不符时停止 |
| 项目 | 是目标项目 |
| SFC | `_scenariofieldconfigId` 与预期类型、请求体一致 |
| 可操作性 | 未删除、未归档 |
| 当前状态 | 记录 `isDone` 和 `_taskflowstatusId`，避免重复写入 |

默认保持 `sfcRequiredValidateEnable=true`。仅在用户明确授权跳过目标状态必填校验时，才可使用 `sfcRequiredValidateEnable=false`；不得把它作为默认值。

### 写后验证

状态更新调用 `api` 时可显式使用 `allowEmptySuccess: true` 接受已知的 204/空成功响应；该返回值只能表示请求已接收。无论返回 200 还是 204，都必须重新调用 `tasks/bulk`，并用 `reconcileBulkTasks` 逐个确认：

- `found === true`；
- `isDone === true`；
- `taskflowstatusId === 目标终态ID`；
- 缺失项保持 `found=false`、状态未知，并停止该项，不能视为更新成功。

调用形式示意：`api(path, { method: "PUT", body, allowEmptySuccess: true })`。即使返回 `null`，后续 `tasks/bulk` 验证也不得跳过。

### 已确认的错误接口

| 错误用法 | 实际结果 |
|---|---|
| `PUT /api/tasks/{id}` 携带 `_taskflowstatusId` | 返回 `204`，但状态是空操作、不变化 |
| `PUT /api/tasks/{id}/isDone` | 工作流项目报 `NotSupportActionInTaskflowProject` |
| 把 `GET /api/stages` 当工作流状态列表 | 错误；该接口实际还需要 `_tasklistId`，返回的是阶段。工作流状态以任务返回值或已知项目配置为准 |

## 失败、重试与删除

- 批量操作发生部分失败时，保留逐项结果并重新查询现状，只重试已确认失败且当前状态仍需处理的项；不要整体盲目重跑。
- 创建任务和登记工时接口没有幂等键。写前查询、稳定任务 ID/标题、按日期缺口计算和写后对账只能降低重复风险，不能保证并发下绝对无重复。
- 删除工时记录和删除任务均不可恢复。当前资料尚未确认任务删除响应，以及删除后用于证明业务状态的完整查询契约；在通过只读观察补齐请求、响应和独立验证方法之前，不要根据 endpoint 猜测执行。契约确认后仍须先展示具体记录 ID / 任务 ID，并取得单独授权。
