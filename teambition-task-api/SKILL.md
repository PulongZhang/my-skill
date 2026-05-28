---
name: teambition-task-api
description: 使用 Teambition API 批量创建任务、添加工时、查询任务数据时调用。涵盖任务 CRUD、工时记录、项目配置查询等接口。
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

认证方式：浏览器环境下自动携带 `cookie` 和 `authorization`，无需手动处理。

## 使用的 MCP 工具

通过 **Chrome MCP Server** 的 `chrome_network_request` 工具发送 API 请求。该工具会自动携带浏览器的登录态（cookie 和 authorization），无需手动处理认证。

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

## 五、删除任务

```
DELETE /api/tasks/{taskId}
```

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

| 状态 | ID |
|------|-----|
| 待处理 | `695b09c72eadc394afddb904` |
| 开发中 | `695b09c72eadc394afddb905` |
| 已完成 | `695b09c72eadc394afddb906` |
| 已验收 | `695b09c72eadc394afddb907` |

## 注意事项

1. 创建任务时 `_scenariofieldconfigId` 和 `_taskflowstatusId` 必须匹配，否则任务状态可能异常
2. 创建任务时 `_taskflowstatusId` 必须使用 `kind: "start"` 的状态（如待处理），不能使用已完成等非起始状态
3. 工时 API 必须携带 `x-organization-id` 和 `x-user-id` 请求头
4. 批量操作时建议控制频率，避免触发限流
5. 删除任务不可恢复，操作前请确认

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
