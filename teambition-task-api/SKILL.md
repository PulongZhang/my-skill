---
name: teambition-task-api
description: 使用 Teambition API 批量创建任务、添加工时、查询任务数据时调用。涵盖任务 CRUD、工时记录、项目配置查询等接口。默认生成 F12 控制台脚本，不依赖额外 MCP（chrome-mcp-server 不稳定）。
---

# Teambition 任务 API

通过 Teambition 内部 API 实现任务的批量创建、工时添加和数据查询。

## 适用场景

- 批量创建任务并分配执行者
- 为任务添加工时记录
- 查询项目的工作流、场景配置等元数据
- 自动化任务管理流程

## API 基础信息

基础域名：当前 Teambition 实例地址（如 `https://tb.cet-electric.com:4753`）

认证方式：所有接口都在 Teambition 同源页面下请求，浏览器自动携带 `cookie` 和 `authorization`，**无需手动处理认证，也无需任何 MCP**。工时相关接口额外需要 `x-organization-id` 和 `x-user-id` 两个自定义请求头。

## 执行方式（默认：生成 F12 控制台脚本）

**常规路径不依赖任何 MCP**：Claude 把「查现状 → 计算 → 创建/登记 → 验证」整合成**一段完整可粘贴的 IIFE 脚本**，由用户在 Teambition 页面的浏览器控制台（F12）运行。脚本用相对路径 `fetch('/api/...')`，同源自动带登录态。

步骤：

1. 浏览器打开 `https://tb.cet-electric.com:4753` 任意页面，确认已登录
2. `F12` → Console 控制台
3. 粘贴脚本，回车执行；脚本末尾打印验证结果

请求统一封装（工时接口必须带 `x-organization-id` / `x-user-id`）：

```javascript
const ORG_ID = '组织ID', USER_ID = '用户ID';
async function api(path, { method='GET', body }={}) {
  const res = await fetch(path, {
    method,
    headers: { 'Content-Type':'application/json', 'x-organization-id':ORG_ID, 'x-user-id':USER_ID },
    body: body ? JSON.stringify(body) : undefined
  });
  const txt = await res.text(); let data; try { data = JSON.parse(txt); } catch { data = txt; }
  if (!res.ok) throw new Error(`${method} ${path} -> ${res.status}: ${txt}`);
  return data;
}
// 例：const t = await api('/api/tasks', { method:'POST', body:{...} });
```

> 提示：生成脚本时让用户**只运行一次**；重复运行会重复建任务/工时。需要重跑时，先用脚本里打印出的任务 ID 删除旧数据。

## 备选：Chrome MCP 工具（可选，非默认）

> ⚠️ `chrome-mcp-server` 连接不稳定（常出现 `ConnectionRefused`）。**默认用上面的 F12 控制台方式**；仅当该 MCP 可用且希望 Claude 全自动执行（无需用户粘贴脚本）时才用此方式。

通过 **Chrome MCP Server** 的 `chrome_network_request` 工具发送 API 请求，自动复用浏览器登录态。

**工具名称：** `mcp__chrome-mcp-server__chrome_network_request`

**使用方式：**

1. 先用 `chrome_navigate` 打开 Teambition 页面，确保浏览器已登录
2. 用 `chrome_network_request` 发送 API 请求，工具会自动复用浏览器的认证信息

**示例（创建任务）：**

```
工具: mcp__chrome-mcp-server__chrome_network_request
参数:
  url: https://tb.cet-electric.com:4753/api/tasks
  method: POST
  headers: {"Content-Type": "application/json"}
  body: {"content": "任务标题", "_tasklistId": "...", "_stageId": "...", ...}
```

**示例（添加工时，需额外请求头）：**

```
工具: mcp__chrome-mcp-server__chrome_network_request
参数:
  url: https://tb.cet-electric.com:4753/work-time-server/api/work-time/batch?from=task&taskId={任务ID}&_userId={用户ID}
  method: POST
  headers: {"Content-Type": "application/json", "x-organization-id": "组织ID", "x-user-id": "用户ID"}
  body: {"_userId": "...", "_objectId": "...", "objectType": "task", "tagIds": [], "times": [...]}
```

**辅助工具：**

| 工具 | 用途 |
|------|------|
| `mcp__chrome-mcp-server__chrome_navigate` | 打开 Teambition 页面确保登录态 |
| `mcp__chrome-mcp-server__chrome_network_capture_start` | 抓取页面网络请求，分析 API 调用 |
| `mcp__chrome-mcp-server__chrome_network_capture_stop` | 停止抓取并查看结果 |
| `mcp__chrome-mcp-server__chrome_get_web_content` | 获取页面内容，提取项目 ID 等信息 |

## 一、创建任务

**接口：** `POST /api/tasks`

**请求体：**

```json
{
  "content": "任务标题",
  "_tasklistId": "任务列表ID",
  "_stageId": "阶段ID",
  "_taskflowstatusId": "工作流状态ID",
  "_scenariofieldconfigId": "场景配置ID",
  "_executorId": "执行者ID（可选）",
  "dueDate": "2026-06-15T09:45:00.000Z（可选）",
  "startDate": "2026-06-01T00:30:00.000Z（可选）",
  "priority": 0,
  "note": "备注内容（可选）"
}
```

**必填字段说明：**

| 字段 | 说明 |
|------|------|
| `content` | 任务名称 |
| `_tasklistId` | 所属任务列表 ID |
| `_stageId` | 所属阶段 ID |
| `_taskflowstatusId` | 工作流状态 ID，决定任务初始状态 |
| `_scenariofieldconfigId` | 场景配置 ID，决定任务类型（需求/缺陷/里程碑等） |

**返回值：** 创建成功返回完整任务对象，包含 `_id` 字段。

## 二、添加工时

**接口：** `POST /work-time-server/api/work-time/batch`

**Query 参数：**

| 参数 | 说明 |
|------|------|
| `from` | 固定值 `task` |
| `taskId` | 任务 ID |
| `_userId` | 操作用户 ID |

**必须请求头：**

| Header | 说明 |
|--------|------|
| `x-organization-id` | 组织 ID |
| `x-user-id` | 当前操作用户 ID |

**请求体：**

```json
{
  "_userId": "用户ID",
  "_objectId": "任务ID",
  "objectType": "task",
  "tagIds": [],
  "times": [
    {
      "date": "2026-05-28",
      "time": 3600000,
      "description": "实施"
    }
  ]
}
```

**工时单位：** 毫秒（1小时 = 3600000ms）。`times` 数组支持同一次请求提交多天的工时记录。

### 删除工时

**接口：** `DELETE /work-time-server/api/work-time/{recordId}`

**必须请求头：** 同添加工时，需 `x-organization-id` 和 `x-user-id`。

**URL 参数：**

| 参数 | 说明 |
|------|------|
| `recordId` | 工时记录 ID（从聚合查询返回的 `objects[]._id` 获取） |

**返回：** `{"ok": true, "payload": {...isDeleted: true}}`，删除后不可恢复。

## 三、查询工时

### 按日期查询工时汇总

**接口：** `POST /work-time-server/api/work-time/aggregation/dates`

**必须请求头：**

| Header | 说明 |
|--------|------|
| `x-organization-id` | 组织 ID |
| `x-user-id` | 当前操作用户 ID |

**请求体：**

```json
{
  "startDate": "2026-05-25",
  "endDate": "2026-05-28",
  "userIds": ["66c4be9751257bcd6ccc6033"],
  "filter": {
    "project": {},
    "task": { "isArchived": false },
    "customfield": {}
  }
}
```

**返回示例：**

```json
{
  "ok": true,
  "payload": [
    {
      "_id": "2026-05-28T00:00:00.000Z",
      "workTime": 7200000,
      "count": 2,
      "date": "2026-05-28T00:00:00.000Z",
      "userIds": ["66c4be9751257bcd6ccc6033"],
      "objects": [
        {
          "_id": "工时记录ID",
          "objectType": "task",
          "_objectId": "任务ID",
          "workTime": 3600000,
          "_submitterId": "提交者ID"
        }
      ],
      "objectIds": ["任务ID"]
    }
  ]
}
```

### 批量查询任务详情（含工时）

**接口：** `POST /work-time-server/api/tasks/bulk`

**请求体：**

```json
{
  "taskIds": ["任务ID1", "任务ID2"]
}
```

**返回：** 任务的完整信息，包括工时统计 `workTime` 字段。

### 其他工时聚合查询

| 接口 | 说明 |
|------|------|
| `POST /work-time-server/api/work-time/aggregation` | 工时汇总查询 |
| `POST /work-time-server/api/work-time/aggregation/users` | 按用户聚合工时 |
| `POST /work-time-server/api/work-time/aggregation/dates-users` | 按日期+用户聚合工时 |
| `POST /work-time-server/api/plan-time/aggregation/dates` | 计划工时按日期查询 |
| `POST /work-time-server/api/plan-time/aggregation/users` | 计划工时按用户查询 |

以上聚合接口的请求体格式与 `work-time/aggregation/dates` 一致。

## 四、查询项目元数据

### 查询场景配置（任务类型）

```
GET /api/v2/projects/{projectId}/scenariofieldconfigs
```

返回项目中所有可用的任务类型（需求、缺陷、里程碑等）及其 ID。

### 查询工作流

```
GET /api/projects/{projectId}/taskflows
```

返回项目中所有工作流及其 ID。

### 查询工作流状态

```
GET /api/stages?_taskflowId={taskflowId}
```

返回指定工作流下的所有状态（待处理、开发中、已完成等）。

### 查询任务列表

```
GET /api/tasklists?_projectId={projectId}
```

返回项目中的任务列表。

### 查询任务

```
GET /api/v2/projects/{projectId}/tasks?pageSize=10
```

分页查询项目下的任务列表。

## 五、GraphQL 查询任务

**接口：** `POST /api/v2/graphql`

**用途：** 通过 GraphQL 一次查询获取任务列表及关联信息（项目、执行者、子任务数等），比 REST API 更灵活。

**请求体：**

```json
{
  "query": "\n    query TasksByOrg($organizationId: ID!, $shortIds: [String], $tql: String, $userView: String, $after: String) {\n  organization(organizationId: $organizationId) {\n    tasks(first: 40, shortIds: $shortIds, tql: $tql, userView: $userView, after: $after) {\n      pageInfo {\n        hasNextPage\n        endCursor\n      }\n      nodes {\n        id\n        content\n        project {\n          id\n          name\n        }\n        isDone\n        executorUser {\n          userId\n          name\n          avatarUrl\n        }\n        projectSfc {\n          icon\n          originalId\n        }\n        parentTask {\n          content\n        }\n        tasklistId\n        stageId\n        sfcId\n        tfsId\n        subtaskCount {\n          total\n          done\n        }\n        startDate\n        dueDate\n        isDeleted\n        isArchived\n      }\n    }\n  }\n}\n    ",
  "variables": {
    "organizationId": "66acf1018881ceb6d5324658",
    "tql": "isArchived = false",
    "after": ""
  }
}
```

**变量说明：**

| 变量 | 说明 |
|------|------|
| `organizationId` | 组织 ID（必填） |
| `tql` | 过滤条件，如 `isArchived = false`、`isDone = false` |
| `first` | 每页数量，默认 40 |
| `after` | 分页游标，翻页时传上一页返回的 `endCursor` |
| `shortIds` | 按任务短 ID 精确查询（可选） |
| `userView` | 用户视图过滤（可选） |

**返回字段：**

| 字段 | 说明 |
|------|------|
| `pageInfo.hasNextPage` | 是否有下一页 |
| `pageInfo.endCursor` | 下一页游标 |
| `nodes[].id` | 任务 ID |
| `nodes[].content` | 任务标题 |
| `nodes[].isDone` | 是否完成 |
| `nodes[].isArchived` | 是否归档 |
| `nodes[].executorUser` | 执行者（userId、name、avatarUrl） |
| `nodes[].project` | 所属项目（id、name） |
| `nodes[].projectSfc` | 场景配置（icon: requirement/bug/call/order/resource） |
| `nodes[].parentTask` | 父任务（content） |
| `nodes[].subtaskCount` | 子任务数（total、done） |
| `nodes[].startDate` | 开始日期 |
| `nodes[].dueDate` | 截止日期 |

**使用场景：**
- 查找当前用户的所有未完成任务
- 按项目筛选任务
- 获取任务的父任务关系（判断归属的需求/缺陷大类）
- 分页遍历组织下全部任务

**TQL 字段名注意：** 过滤执行者用 `executorId = "用户ID"`（**不是** `executor`）；`project` 也是非法字段名。可用组合如 `isArchived = false AND executorId = "66c4be9751257bcd6ccc6033" AND isDone = true`。按执行者过滤用 GraphQL 比项目任务 REST 接口的 `_executorId` query 参数更可靠（后者不生效）。

## 六、删除任务

```
DELETE /api/tasks/{taskId}
```

## 七、更新任务状态（工作流状态变更 / 标记已完成）

工作流（taskflow）项目里**不能**用通用接口改状态，必须用专门的状态变更接口。

**接口：** `PUT /api/tasks/{taskId}/taskflowstatus`

**请求头：** `{"Content-Type": "application/json"}`

**请求体：**

```json
{
  "_taskflowstatusId": "目标状态ID",
  "_scenariofieldconfigId": "场景配置ID（任务类型）",
  "sfcRequiredValidateEnable": true,
  "persistentValidatorEnable": false,
  "disableRequiredCfIds": []
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `_taskflowstatusId` | 目标工作流状态 ID（如已完成 `695b09c72eadc394afddb907`） |
| `_scenariofieldconfigId` | 任务所属场景配置 ID，必须与任务类型一致 |
| `sfcRequiredValidateEnable` | 是否校验目标状态的必填字段，默认 `true`；不想填必填值时设 `false` 可跳过校验 |
| `persistentValidatorEnable` | 持久化校验，一般 `false` |
| `disableRequiredCfIds` | 指定豁免必填校验的 customfieldId 列表 |

**返回：** `200` 返回更新后的任务对象（含 `isDone`、`accomplished`、`taskflowstatus`）即成功。

> ⚠️ **该接口只改状态，不写入 `customfields` / `startDate` / `dueDate`。** 即使 body 里带上这些字段也不生效，填业务字段请改用 `PUT /api/tasks/{taskId}`。

### 跳过必填字段校验（批量标记完成常用）

某些终态（如需求工作流的「已完成」）要求开始时间、截止时间、需求来源、需求价值分析、干系人分析、需求描述等字段必填，缺字段会返回 `400 MissingRequiredField`。若不想逐个填值，把 `sfcRequiredValidateEnable` 设为 `false` 即可强制改状态（字段留空）：

```json
{
  "_taskflowstatusId": "695b09c72eadc394afddb907",
  "_scenariofieldconfigId": "695b09c82eadc394afddbc59",
  "sfcRequiredValidateEnable": false,
  "persistentValidatorEnable": false,
  "disableRequiredCfIds": []
}
```

### 不要用这两个接口改状态（踩坑）

| 错误接口 | 结果 |
|------|------|
| `PUT /api/tasks/{taskId}` + `{"_taskflowstatusId": "..."}` | 返回 `204` 但是**空操作**，状态不变（GET 验证仍是原状态，`updated` 不变） |
| `PUT /api/tasks/{taskId}/isDone` + `{"isDone": true}` | 工作流项目返回 `400 NotSupportActionInTaskflowProject`（工作流项目不支持该操作） |

## 批量创建示例

```javascript
const BASE = {
  _tasklistId: "任务列表ID",
  _stageId: "阶段ID",
};

const TASKS = [
  {
    content: "任务1",
    _scenariofieldconfigId: "场景配置ID",
    _taskflowstatusId: "工作流状态ID",
    _executorId: "执行者ID",
    dueDate: "2026-06-15T09:45:00.000Z",
  },
  {
    content: "任务2",
    _scenariofieldconfigId: "场景配置ID",
    _taskflowstatusId: "工作流状态ID",
    _executorId: "执行者ID",
  },
];

for (const task of TASKS) {
  const res = await fetch("/api/tasks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...BASE, ...task }),
  });
  const data = await res.json();
  console.log(`创建: ${data.content} (${data._id})`);
}
```

## 批量添加工时示例

```javascript
const WORK_TIMES = [
  { taskId: "任务ID1", date: "2026-05-28", time: 3600000, description: "开发" },
  { taskId: "任务ID1", date: "2026-05-29", time: 7200000, description: "联调" },
  { taskId: "任务ID2", date: "2026-05-28", time: 1800000, description: "评审" },
];

for (const wt of WORK_TIMES) {
  const res = await fetch(
    `/work-time-server/api/work-time/batch?from=task&taskId=${wt.taskId}&_userId=用户ID`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-organization-id": "组织ID",
        "x-user-id": "用户ID",
      },
      body: JSON.stringify({
        _userId: "用户ID",
        _objectId: wt.taskId,
        objectType: "task",
        tagIds: [],
        times: [{ date: wt.date, time: wt.time, description: wt.description }],
      }),
    }
  );
  const data = await res.json();
  console.log(`工时: ${wt.taskId} - ${data.ok ? "成功" : "失败"}`);
}
```

## 常用 ID 速查（S1867_中联泰国DCOM 项目）

### 项目与组织

| 名称 | ID |
|------|-----|
| 组织 ID | `66acf1018881ceb6d5324658` |
| 项目 ID | `695b09c7b842a4a0fd053603` |
| 任务列表 ID | `695b09c72eadc394afddb900` |
| 阶段 ID（未分类） | `695b09c72eadc394afddb970` |

### 成员

| 姓名 | ID |
|------|-----|
| 张蒲龙 | `66c4be9751257bcd6ccc6033` |
| 周泽宇 | `66c4bf6a2e7e0c966313feb5` |
| 刘静 | `66c4bf782e7e0c966313ff9f` |
| 陈凌霄 | `69ba18dc6100bb5b257f5bbc` |
| 曾丹 | `66c4be9951257bcd6ccc605b` |
| 姚谦 | `66d055da1ec56add7497165d` |
| 陈多 | `67299cc43bcddea0ff1e749e` |
| 何秋平 | `66c4bf742e7e0c966313ff6e` |
| 郭敏 | `66c4bf6a51257bcd6ccc62fa` |

### 场景配置（任务类型）

| 名称 | ID |
|------|-----|
| 立项 | `695b09c82eadc394afddbc36` |
| 需求 | `695b09c82eadc394afddbc59` |
| 缺陷 | `695b09c82eadc394afddbc72` |
| 里程碑 | `695b09c82eadc394afddbc96` |
| 需求变更 | `695b09c82eadc394afddbcb7` |
| 开发任务 | `695b09c82eadc394afddbd21` |
| 测试任务 | `695b09c82eadc394afddbd35` |

### 工作流

| 名称 | ID |
|------|-----|
| 立项工作流 | `695b09c72eadc394afddb8e9` |
| 需求工作流 | `695b09c72eadc394afddb8e4` |
| 缺陷工作流 | `695b09c72eadc394afddb8e5` |
| 里程碑工作流 | `695b09c72eadc394afddb8e7` |
| 风险工作流 | `695b09c72eadc394afddb8e8` |
| 开发任务 | `695b09c72eadc394afddb8ee` |
| 测试任务 | `695b09c72eadc394afddb8ef` |

### 工作流状态（需求工作流）

> 终态「已完成」（`...907`，`kind: end`）用于标记任务完成；创建任务用起始态「待处理」（`...904`，`kind: start`）。

| 状态 | ID | kind |
|------|-----|------|
| 待处理（起始） | `695b09c72eadc394afddb904` | start |
| 开发中 | `695b09c72eadc394afddb905` | — |
| 已验收 | `695b09c72eadc394afddb906` | — |
| 已完成（终态） | `695b09c72eadc394afddb907` | end |

## 注意事项

1. 创建任务时 `_scenariofieldconfigId` 和 `_taskflowstatusId` 必须匹配，否则任务状态可能异常
2. 创建任务时 `_taskflowstatusId` 必须使用 `kind: "start"` 的状态（如待处理），不能使用已完成等非起始状态
3. 工时 API 必须携带 `x-organization-id` 和 `x-user-id` 请求头
4. 批量操作时建议控制频率，避免触发限流
5. 删除任务不可恢复，操作前请确认
6. 改工作流状态必须用 `PUT /api/tasks/{id}/taskflowstatus`；`PUT /api/tasks/{id}` 带 `_taskflowstatusId` 是空操作（返回 204 但状态不变），`PUT /api/tasks/{id}/isDone` 在工作流项目返回 `400`
7. 终态（如已完成）常带必填字段（开始/截止时间、需求来源等），缺值会报 `400 MissingRequiredField`；批量标记完成时把 `sfcRequiredValidateEnable` 设为 `false` 即可跳过校验
8. `taskflowstatus` 接口只改状态，不会写入 `customfields`/`startDate`/`dueDate`，业务字段要用 `PUT /api/tasks/{id}` 单独填

## 操作经验

### 根据 Git 提交登记工时的完整流程

1. **查 git 日志：** `git log <branch> --author="<name>" --since="<start>" --until="<end>" --format="%ad %s" --date=short --no-merges`
2. **分析 commit 归属：** 每个 commit 应该归属到具体的 TB 任务，不要塞进无关的"大杂烩"任务
3. **先创建 TB 任务：** 如果 commit 内容没有对应的 TB 任务，先新建任务（如 `feat(bpm): 消息模板提醒` → 新建"消息模板优化"需求）
4. **再登记工时：** 工时描述应简洁概括该任务当天的实际工作内容，与 TB 任务名称直接相关
5. **验证：** 用聚合查询确认每天是否满 8h，且每个任务的工时分布合理

### 常见错误

- **工时内容与任务不匹配：** 比如把"消息模板提醒"的工时挂到"服务台与个人中心优化"下 → 解决：先建正确的 TB 任务，再登记
- **周一算成周二：** 查 git 之前先确认日期是周几（如 `date` 命令或日历）
- **任务状态不合法：** 创建任务时用了非起始状态（如已完成）→ 解决：使用 `kind: "start"` 的状态

### 工时修改

已登记的工时可以通过以下方式修正：
1. `DELETE /work-time-server/api/work-time/{recordId}` 删除错误条目
2. `POST /work-time-server/api/work-time/batch` 重新添加正确条目
3. 聚合查询验证修改后每天是否满 8h

### 批量标记任务已完成

登记完工时后把对应需求标为已完成的推荐流程：

1. **确认终态状态 ID：** 用「已完成」（需求工作流为 `695b09c72eadc394afddb907`，`kind: end`）。注意本项目里 `907` 才是终态「已完成」，不是 `906`
2. **逐个调用状态变更接口：** `PUT /api/tasks/{taskId}/taskflowstatus`，body 带 `_taskflowstatusId` + `_scenariofieldconfigId`，并把 `sfcRequiredValidateEnable` 设为 `false` 跳过必填字段校验（否则会被开始/截止时间、需求来源等必填项挡住）
3. **并行批量：** 多个任务的状态变更互相独立，可在一次响应里并行发送加速
4. **验证：** 用 GraphQL `tql: "isArchived = false AND executorId = \"...\" AND isDone = true"` 确认这些任务都已进入终态

**常见错误：**
- **误用 `PUT /api/tasks/{id}` 改状态：** 返回 204 但状态不变 → 解决：改用 `/taskflowstatus` 子接口
- **误用 `/isDone`：** 工作流项目报 `NotSupportActionInTaskflowProject` → 解决：改用 `/taskflowstatus` 子接口
- **被必填字段挡住：** 报 `MissingRequiredField` → 解决：`sfcRequiredValidateEnable: false` 跳过，或在 `disableRequiredCfIds` 里列出豁免的 customfieldId

### 端到端脚本模板：按缺口把多天工时补到目标时长

适用：根据 git 记录新建任务、标记已完成，并把指定日期工时补到每天目标时长（如 8h）。已有工时按缺口自动缩减，确保不超标。在 Teambition 页面 F12 控制台粘贴运行，**只跑一次**。

完整脚本见 [`work-time-fill-template.js`](work-time-fill-template.js)：填好顶部【配置区】和 `TASKS` 计划后，复制整份文件到 F12 控制台运行。
