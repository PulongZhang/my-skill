/**
 * Teambition F12 工时补录兜底模板。
 * 适用范围：已验证的 S1867“需求”SFC 与起始态 904；配置值仍须按本次运行逐项核验，不能把示例当默认输入。
 * 其他 SFC 不得复用该状态，必须先提供并核验其实际工作流中 kind:start 的配置。
 * 本模板仅用于本人补录：当前登录用户、工时所属用户和任务执行者必须是同一人。
 *
 * 每次运行都会重新查询任务和每日总工时，优先复用，仅补剩余缺口，不修改任务状态。
 * 部分失败后可重新运行，但并发写入下仍不能承诺绝对幂等，不能盲目重放旧请求。
 */
(async () => {
  // ===== 本次运行输入（从当前页面和项目元数据核验后填写） =====
  const ORG_ID = 'REPLACE_WITH_ORGANIZATION_ID';
  // 本模板是本人补录模板：该 ID 同时代表当前登录用户、工时所属用户和任务执行者。
  const SELF_USER_ID = 'REPLACE_WITH_CURRENT_USER_ID';
  const PROJECT_ID = 'REPLACE_WITH_PROJECT_ID';
  const TASKLIST_ID = 'REPLACE_WITH_TASKLIST_ID';
  const STAGE_ID = 'REPLACE_WITH_STAGE_ID';
  const SFC_ID = 'REPLACE_WITH_SFC_ID';
  const TFS_START_ID = 'REPLACE_WITH_VERIFIED_START_STATUS_ID';
  const TEAMBITION_ORIGIN = 'REPLACE_WITH_TEAMBITION_ORIGIN';
  const TARGET_MS = Number('REPLACE_WITH_TARGET_MILLISECONDS');

  // 本模板要求每个日期仅一项；同日多任务必须另行设计显式分配方案。
  const WORK_PLANS = [
    {
      date: 'REPLACE_WITH_DATE_1',
      mode: 'reuse',
      id: 'REPLACE_WITH_TASK_ID',
      expectedTitle: 'REPLACE_WITH_EXACT_EXISTING_TASK_TITLE',
      description: 'REPLACE_WITH_ACTUAL_WORK_DESCRIPTION_1',
    },
    {
      date: 'REPLACE_WITH_DATE_2',
      mode: 'create-if-missing',
      title: 'REPLACE_WITH_EXACT_NEW_TASK_TITLE',
      description: 'REPLACE_WITH_ACTUAL_WORK_DESCRIPTION_2',
    },
  ];

  if (location.origin !== TEAMBITION_ORIGIN) {
    throw new Error(`请在 ${TEAMBITION_ORIGIN} 的已登录页面运行，当前 origin 为 ${location.origin}`);
  }

  const PLACEHOLDER = /REPLACE_WITH|<[^>]+>|组织ID|用户ID|项目ID|任务ID|YYYY-MM-DD/i;
  const ID_PATTERN = /^[a-f0-9]{24}$/i;
  const stableUnique = (values) => [...new Set(values)];
  const formatMs = (value) => `${(value / 3600000).toFixed(2)}h`;

  function assertObject(value, label) {
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} 必须是对象`);
  }

  function requireConfigText(value, label) {
    if (typeof value !== 'string' || !value.trim() || value !== value.trim() || PLACEHOLDER.test(value)) {
      throw new Error(`${label} 尚未替换或不是有效字符串`);
    }
    return value;
  }

  function requireApiText(value, label) {
    if (typeof value !== 'string' || !value.trim()) throw new Error(`${label} 缺失或不是非空字符串`);
    return value;
  }

  function requireId(value, label) {
    if (typeof value !== 'string' || value !== value.trim() || !ID_PATTERN.test(value)) {
      throw new Error(`${label} 不是无首尾空白的 24 位 ID`);
    }
    return value;
  }

  function assertVerifiedS1867Configuration() {
    if (
      ORG_ID !== '66acf1018881ceb6d5324658' ||
      PROJECT_ID !== '695b09c7b842a4a0fd053603' ||
      TASKLIST_ID !== '695b09c72eadc394afddb900' ||
      STAGE_ID !== '695b09c72eadc394afddb970' ||
      SFC_ID !== '695b09c82eadc394afddbc59' ||
      TFS_START_ID !== '695b09c72eadc394afddb904'
    ) {
      throw new Error('当前模板仅支持已验证的 S1867 组织、项目、任务列表、阶段、需求 SFC 与起始态 904 组合');
    }
  }

  function normalizeApiDate(value, label) {
    if (typeof value !== 'string') throw new Error(`${label} 不是字符串`);
    const match = value.match(/^(\d{4}-\d{2}-\d{2})(?:T00:00:00(?:\.000)?Z)?$/);
    if (!match) throw new Error(`${label} 不是 YYYY-MM-DD 或 UTC 零点时间戳`);
    const date = match[1];
    const parsed = new Date(`${date}T00:00:00.000Z`);
    if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) {
      throw new Error(`${label} 不是有效日期`);
    }
    return date;
  }

  function isPlanDate(value) {
    try {
      return normalizeApiDate(value, '计划日期') === value;
    } catch {
      return false;
    }
  }

  function validateConfiguration() {
    assertVerifiedS1867Configuration();
    for (const [label, value] of Object.entries({
      ORG_ID, SELF_USER_ID, PROJECT_ID, TASKLIST_ID, STAGE_ID, SFC_ID, TFS_START_ID,
    })) requireId(value, label);
    requireConfigText(TEAMBITION_ORIGIN, 'TEAMBITION_ORIGIN');
    if (new URL(TEAMBITION_ORIGIN).origin !== TEAMBITION_ORIGIN) {
      throw new Error('TEAMBITION_ORIGIN 必须是不含路径和结尾斜杠的 origin');
    }
    if (!Number.isSafeInteger(TARGET_MS) || TARGET_MS <= 0) throw new Error('TARGET_MS 必须是正整数毫秒数');
    if (!Array.isArray(WORK_PLANS) || WORK_PLANS.length === 0) throw new Error('WORK_PLANS 至少需要一项');

    const dates = new Set();
    WORK_PLANS.forEach((plan, index) => {
      assertObject(plan, `WORK_PLANS[${index}]`);
      requireConfigText(plan.date, `WORK_PLANS[${index}].date`);
      requireConfigText(plan.description, `WORK_PLANS[${index}].description`);
      if (!isPlanDate(plan.date)) throw new Error(`WORK_PLANS[${index}].date 必须是 YYYY-MM-DD`);
      if (dates.has(plan.date)) throw new Error(`日期 ${plan.date} 重复；每个日期只能有一项`);
      dates.add(plan.date);
      if (plan.mode === 'reuse') {
        requireId(plan.id, `WORK_PLANS[${index}].id`);
        requireConfigText(plan.expectedTitle, `WORK_PLANS[${index}].expectedTitle`);
      } else if (plan.mode === 'create-if-missing') {
        requireConfigText(plan.title, `WORK_PLANS[${index}].title`);
      } else {
        throw new Error(`WORK_PLANS[${index}].mode 只能是 reuse 或 create-if-missing`);
      }
    });
  }

  validateConfiguration();
  const TARGET_DATES = WORK_PLANS.map((plan) => plan.date);
  const SORTED_DATES = [...TARGET_DATES].sort();
  const START_DATE = SORTED_DATES[0];
  const END_DATE = SORTED_DATES[SORTED_DATES.length - 1];
  const REUSE_IDS = stableUnique(WORK_PLANS.filter((plan) => plan.mode === 'reuse').map((plan) => plan.id));

  async function api(path, {
    method = 'GET', body, expectArrayPayload = false, allowArray = false, allowEmptySuccess = false,
  } = {}) {
    if (typeof path !== 'string' || !path.startsWith('/')) throw new Error('API 路径必须是同源相对路径');
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin) throw new Error('拒绝跨源 API 请求');
    const isWorkTimeService = url.pathname.startsWith('/work-time-server/');
    const headers = body === undefined ? {} : { 'Content-Type': 'application/json' };
    if (isWorkTimeService) {
      headers['x-organization-id'] = ORG_ID;
      headers['x-user-id'] = SELF_USER_ID;
    }
    const response = await fetch(`${url.pathname}${url.search}`, {
      method, headers, body: body === undefined ? undefined : JSON.stringify(body), credentials: 'same-origin',
    });
    if (!response.ok) throw new Error(`${method} ${url.pathname} HTTP ${response.status}`);
    const finalUrl = new URL(response.url || location.href, location.origin);
    if (response.redirected || finalUrl.origin !== location.origin || finalUrl.pathname.startsWith('/login')) {
      throw new Error(`${method} ${url.pathname} 返回认证重定向`);
    }
    const text = await response.text();
    if (!text) {
      if (allowEmptySuccess) return null;
      throw new Error(`${method} ${url.pathname} 成功响应为空`);
    }
    let data;
    try { data = JSON.parse(text); } catch {
      throw new Error(`${method} ${url.pathname} 返回非 JSON 内容，可能登录已失效`);
    }
    if (Array.isArray(data)) {
      if (!allowArray || isWorkTimeService) throw new Error(`${method} ${url.pathname} 返回了未授权的数组结构`);
      return data;
    }
    assertObject(data, `${method} ${url.pathname} 响应`);
    if (isWorkTimeService) {
      if (data.ok !== true) throw new Error(`${method} ${url.pathname} 返回 ok !== true`);
      if (expectArrayPayload && !Array.isArray(data.payload)) throw new Error(`${method} ${url.pathname} 的 payload 不是数组`);
    }
    return data;
  }

  function parseDailySnapshot(payload) {
    if (!Array.isArray(payload)) throw new Error('日期聚合 payload 不是数组');
    const days = {};
    const recordIds = new Set();
    payload.forEach((day, dayIndex) => {
      assertObject(day, `日期聚合 payload[${dayIndex}]`);
      const date = normalizeApiDate(day.date, `日期聚合 payload[${dayIndex}].date`);
      if (days[date]) throw new Error(`日期聚合重复日期 ${date}`);
      for (const field of ['workTime', 'count']) {
        if (!Number.isSafeInteger(day[field]) || day[field] < 0) {
          throw new Error(`日期聚合 ${date}.${field} 不是非负安全整数`);
        }
      }
      if (!Array.isArray(day.objects)) throw new Error(`日期聚合 ${date}.objects 不是数组`);
      if (day.count !== day.objects.length) throw new Error(`日期聚合 ${date} 的 count 与 objects 数量不符`);
      let objectWorkTime = 0;
      const objects = day.objects.map((item, itemIndex) => {
        assertObject(item, `日期聚合 ${date}.objects[${itemIndex}]`);
        requireId(item._id, `日期聚合 ${date}.objects[${itemIndex}]._id`);
        if (typeof item.objectType !== 'string' || !item.objectType.trim()) throw new Error(`工时记录 ${item._id}.objectType 缺失`);
        if (recordIds.has(item._id)) throw new Error(`日期聚合重复工时记录 ID ${item._id}`);
        recordIds.add(item._id);
        if (!Number.isSafeInteger(item.workTime) || item.workTime < 0) throw new Error(`工时记录 ${item._id}.workTime 非法`);
        if (item.objectType === 'task') requireId(item._objectId, `工时记录 ${item._id}._objectId`);
        objectWorkTime += item.workTime;
        return { id: item._id, objectType: item.objectType, taskId: item._objectId ?? null, time: item.workTime };
      });
      if (objectWorkTime !== day.workTime) throw new Error(`日期聚合 ${date} 的 workTime 与 objects 合计不符`);
      days[date] = { date, workTime: day.workTime, count: day.count, objects };
    });
    for (const date of TARGET_DATES) {
      if (!days[date]) days[date] = { date, workTime: 0, count: 0, objects: [] };
    }
    return { days, hours: Object.fromEntries(TARGET_DATES.map((date) => [date, days[date].workTime])) };
  }

  let lastDailySnapshot = null;
  let dailyQueryToken = 0;
  async function queryDailyHours() {
    const token = ++dailyQueryToken;
    const result = await api('/work-time-server/api/work-time/aggregation/dates', {
      method: 'POST', expectArrayPayload: true,
      body: {
        startDate: START_DATE, endDate: END_DATE, userIds: [SELF_USER_ID],
        // 每日总工时必须包含归档任务，避免漏算后重复补录。
        filter: { project: {}, task: {}, customfield: {} },
      },
    });
    const snapshot = parseDailySnapshot(result.payload);
    if (token === dailyQueryToken) lastDailySnapshot = snapshot;
    return snapshot.hours;
  }

  async function queryAllIncompleteTasks() {
    const query = `
      query TasksByOrg($organizationId: ID!, $tql: String, $after: String) {
        organization(organizationId: $organizationId) {
          tasks(first: 40, tql: $tql, after: $after) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id content isDeleted isArchived isDone tasklistId stageId sfcId
              project { id name }
              executorUser { userId name }
            }
          }
        }
      }
    `;
    const tql = `isArchived = false AND isDone = false AND executorId = "${SELF_USER_ID}"`;
    const nodes = [];
    const cursors = new Set();
    const taskIds = new Set();
    let after = null;
    let hasNextPage = true;
    while (hasNextPage) {
      const result = await api('/api/v2/graphql', {
        method: 'POST', body: { query, variables: { organizationId: ORG_ID, tql, after } },
      });
      if (result.errors !== undefined && result.errors !== null) {
        if (!Array.isArray(result.errors) || result.errors.length > 0) throw new Error('GraphQL 返回 errors');
      }
      const connection = result.data?.organization?.tasks;
      assertObject(connection, 'GraphQL organization.tasks');
      if (!Array.isArray(connection.nodes)) throw new Error('GraphQL tasks.nodes 不是数组');
      assertObject(connection.pageInfo, 'GraphQL pageInfo');
      if (typeof connection.pageInfo.hasNextPage !== 'boolean') throw new Error('GraphQL hasNextPage 不是 boolean');
      if (connection.pageInfo.endCursor != null && typeof connection.pageInfo.endCursor !== 'string') {
        throw new Error('GraphQL endCursor 类型异常');
      }
      connection.nodes.forEach((task, index) => {
        assertObject(task, `GraphQL task[${index}]`);
        requireId(task.id, `任务 id`);
        if (taskIds.has(task.id)) throw new Error(`GraphQL 跨页重复任务 ID ${task.id}`);
        taskIds.add(task.id);
        if (task.project?.id !== PROJECT_ID) return;
        requireApiText(task.content, `任务 ${task.id}.content`);
        requireId(task.sfcId, `任务 ${task.id}.sfcId`);
        if (task.executorUser?.userId !== SELF_USER_ID) throw new Error(`任务 ${task.id} 执行者不匹配`);
        for (const field of ['isDeleted', 'isArchived', 'isDone']) {
          if (typeof task[field] !== 'boolean') throw new Error(`任务 ${task.id}.${field} 缺失或不是 boolean`);
        }
        nodes.push(task);
      });
      hasNextPage = connection.pageInfo.hasNextPage;
      if (hasNextPage) {
        const cursor = connection.pageInfo.endCursor;
        if (!cursor) throw new Error('分页不完整：endCursor 为空');
        if (cursor === after || cursors.has(cursor)) throw new Error('分页不完整：游标重复或无进展');
        cursors.add(cursor);
        after = cursor;
      }
    }
    return nodes.filter((task) =>
      task.project?.id === PROJECT_ID && task.executorUser?.userId === SELF_USER_ID &&
      task.isDeleted === false && task.isArchived === false && task.isDone === false
    );
  }

  function reconcileBulkTasks(requestedIds, response) {
    const uniqueIds = stableUnique(requestedIds);
    uniqueIds.forEach((id, index) => requireId(id, `requestedIds[${index}]`));
    assertObject(response, 'tasks/bulk 响应');
    if (response.ok !== true || !Array.isArray(response.payload)) throw new Error('tasks/bulk 响应结构异常');
    const requested = new Set(uniqueIds);
    const byId = new Map();
    response.payload.forEach((task, index) => {
      assertObject(task, `tasks/bulk payload[${index}]`);
      requireId(task._id, `tasks/bulk payload[${index}]._id`);
      if (!requested.has(task._id) || byId.has(task._id)) throw new Error(`tasks/bulk 返回未请求或重复任务 ${task._id}`);
      requireApiText(task.content, `任务 ${task._id}.content`);
      for (const field of ['isDeleted', 'isArchived', 'isDone']) {
        if (typeof task[field] !== 'boolean') throw new Error(`任务 ${task._id}.${field} 缺失或不是 boolean`);
      }
      for (const field of ['_projectId', '_scenariofieldconfigId', '_taskflowstatusId']) requireId(task[field], `任务 ${task._id}.${field}`);
      byId.set(task._id, task);
    });
    return uniqueIds.map((requestedId) => ({
      requestedId, found: byId.has(requestedId), task: byId.get(requestedId) ?? null,
    }));
  }

  async function queryTasksByIds(requestedIds) {
    const taskIds = stableUnique(requestedIds);
    if (taskIds.length === 0) return [];
    const result = await api('/work-time-server/api/tasks/bulk', {
      method: 'POST', expectArrayPayload: true, body: { taskIds },
    });
    return reconcileBulkTasks(taskIds, result);
  }

  function requireBulkTask(entries, id, label) {
    const entry = entries.find((item) => item.requestedId === id);
    if (!entry?.found) throw new Error(`${label} 的 tasks/bulk 结果缺失`);
    return entry.task;
  }

  function assertGraphTask(task, title, label) {
    if (!task) throw new Error(`${label} 不在组织级未完成任务结果中`);
    if (task.content !== title) throw new Error(`${label} 标题不匹配`);
    if (task.project?.id !== PROJECT_ID || task.executorUser?.userId !== SELF_USER_ID) throw new Error(`${label} 项目或执行者不匹配`);
    if (task.sfcId !== SFC_ID) throw new Error(`${label} SFC 不匹配`);
    if (task.isDeleted !== false || task.isArchived !== false || task.isDone !== false) throw new Error(`${label} 不可复用`);
    return task;
  }

  function assertBulkTask(task, title, label, requireStart = false) {
    if (task.content !== title || task._projectId !== PROJECT_ID || task._scenariofieldconfigId !== SFC_ID) {
      throw new Error(`${label} 的标题、项目或 SFC 不匹配`);
    }
    if (task.isDeleted !== false || task.isArchived !== false || task.isDone !== false) throw new Error(`${label} 不可写工时`);
    if (requireStart && task._taskflowstatusId !== TFS_START_ID) throw new Error(`${label} 不是已验证的起始状态`);
    return task;
  }

  function findExactTask(tasks, title) {
    const matches = tasks.filter((task) => task.content === title);
    if (matches.some((task) => task.sfcId !== SFC_ID)) throw new Error(`标题“${title}”存在不同 SFC 的同名任务，需人工消歧`);
    if (matches.length > 1) throw new Error(`标题“${title}”命中多个任务，需人工消歧`);
    return matches.length === 0 ? null : assertGraphTask(matches[0], title, `标题“${title}”候选`);
  }

  function resolvePlans(tasks, bulkEntries) {
    return WORK_PLANS.map((plan) => {
      if (plan.mode === 'reuse') {
        const graphTask = assertGraphTask(tasks.find((task) => task.id === plan.id), plan.expectedTitle, `复用任务 ${plan.id}`);
        const bulkTask = assertBulkTask(requireBulkTask(bulkEntries, plan.id, `复用任务 ${plan.id}`), plan.expectedTitle, `复用任务 ${plan.id}`);
        return {
          ...plan, resolution: 'reuse-by-id', taskId: graphTask.id, taskTitle: graphTask.content,
          sfcId: graphTask.sfcId, statusId: bulkTask._taskflowstatusId,
        };
      }
      const task = findExactTask(tasks, plan.title);
      return task
        ? { ...plan, resolution: 'reuse-by-title', taskId: task.id, taskTitle: task.content, sfcId: task.sfcId, statusId: null }
        : { ...plan, resolution: 'create', taskId: null, taskTitle: plan.title, sfcId: SFC_ID, statusId: TFS_START_ID };
    });
  }

  const fingerprint = (plan) => JSON.stringify({
    date: plan.date, mode: plan.mode, resolution: plan.resolution, taskId: plan.taskId,
    taskTitle: plan.taskTitle, sfcId: plan.sfcId, statusId: plan.statusId,
  });
  const resolutionText = (plan) => plan.resolution === 'create'
    ? '新建（仅缺失时）'
    : plan.resolution === 'reuse-by-id' ? '复用（明确 ID）' : '复用（精准标题）';

  function metadataArray(raw, knownFields, label) {
    if (Array.isArray(raw)) return raw;
    assertObject(raw, `${label} 响应`);
    const arrays = Object.entries(raw).filter(([, value]) => Array.isArray(value));
    if (arrays.length !== 1 || !knownFields.includes(arrays[0][0])) throw new Error(`${label} 响应没有唯一已知数组字段`);
    return arrays[0][1];
  }

  function metadataId(item, label) {
    assertObject(item, label);
    const ids = stableUnique([item._id, item.id].filter((value) => value != null));
    if (ids.length !== 1) throw new Error(`${label} 的 ID 缺失或冲突`);
    return requireId(ids[0], `${label}.id`);
  }

  async function validateCreationMetadata() {
    assertVerifiedS1867Configuration();
    const [tasklistsRaw, stagesRaw, sfcsRaw] = await Promise.all([
      api(`/api/tasklists?_projectId=${encodeURIComponent(PROJECT_ID)}`, { allowArray: true }),
      api(`/api/stages?_tasklistId=${encodeURIComponent(TASKLIST_ID)}`, { allowArray: true }),
      api(`/api/v2/projects/${encodeURIComponent(PROJECT_ID)}/scenariofieldconfigs`, { allowArray: true }),
    ]);
    const tasklists = metadataArray(tasklistsRaw, ['tasklists'], '任务列表');
    const stages = metadataArray(stagesRaw, ['stages'], '阶段');
    const sfcs = metadataArray(sfcsRaw, ['scenariofieldconfigs', 'scenarioFieldConfigs'], 'SFC');
    if (!tasklists.some((item, index) => metadataId(item, `tasklists[${index}]`) === TASKLIST_ID)) throw new Error('TASKLIST_ID 不属于目标项目');
    if (!stages.some((item, index) => metadataId(item, `stages[${index}]`) === STAGE_ID)) throw new Error('STAGE_ID 不属于目标任务列表');
    if (!sfcs.some((item, index) => metadataId(item, `sfcs[${index}]`) === SFC_ID)) throw new Error('SFC_ID 不属于目标项目');
  }

  const [beforeHours, beforeTasks, beforeBulk] = await Promise.all([
    queryDailyHours(), queryAllIncompleteTasks(), queryTasksByIds(REUSE_IDS),
  ]);
  for (const date of TARGET_DATES) {
    if (beforeHours[date] > TARGET_MS) throw new Error(`${date} 已超额/并发冲突，停止补录`);
  }
  const beforePlans = resolvePlans(beforeTasks, beforeBulk).map((plan) => ({
    ...plan, beforeMs: beforeHours[plan.date], gapMs: Math.max(0, TARGET_MS - beforeHours[plan.date]),
  }));
  console.table(beforePlans.map((plan) => ({
    日期: plan.date, 已有: formatMs(plan.beforeMs), 目标: formatMs(TARGET_MS), 缺口: formatMs(plan.gapMs),
    任务: plan.taskId ? `${plan.taskTitle} (${plan.taskId})` : plan.taskTitle,
    '复用/新建': resolutionText(plan), 描述: plan.description,
  })));
  const activeBefore = beforePlans.filter((plan) => plan.gapMs > 0);
  if (activeBefore.length === 0) {
    console.info('所有日期已达到目标工时，无需写入。');
    return;
  }
  const proposedTitles = stableUnique(activeBefore.filter((plan) => plan.resolution === 'create').map((plan) => plan.taskTitle));
  const confirmation = [
    `拟补录总时长：${formatMs(activeBefore.reduce((sum, plan) => sum + plan.gapMs, 0))}`,
    `拟新建任务：\n${proposedTitles.length ? proposedTitles.map((title) => `- ${title}`).join('\n') : '- 无'}`,
    '确认后会再次查询；只允许缩小缺口，方案变化会停止。',
    '本模板不会修改任务状态。取消不会产生写入。',
    '并发写入下不能保证绝对幂等。是否继续？',
  ].join('\n\n');
  if (!window.confirm(confirmation)) {
    console.info('用户取消，未执行任何写入。');
    return;
  }

  const [latestHours, latestTasks, latestBulk] = await Promise.all([
    queryDailyHours(), queryAllIncompleteTasks(), queryTasksByIds(REUSE_IDS),
  ]);
  for (const date of TARGET_DATES) {
    if (latestHours[date] > TARGET_MS) throw new Error(`${date} 重查后超额/并发冲突，停止补录`);
  }
  const latestPlans = resolvePlans(latestTasks, latestBulk).map((plan) => ({
    ...plan, beforeMs: latestHours[plan.date], gapMs: Math.max(0, TARGET_MS - latestHours[plan.date]),
  }));
  latestPlans.forEach((plan, index) => {
    const before = beforePlans[index];
    if (plan.gapMs > before.gapMs) throw new Error(`${plan.date} 缺口增加，请重新运行查看新计划`);
    if (fingerprint(plan) !== fingerprint(before)) throw new Error(`${plan.date} 的任务或 SFC 方案发生变化，请重新运行`);
  });
  const createScope = (plans) => stableUnique(plans.filter((plan) => plan.resolution === 'create').map((plan) => plan.taskTitle));
  if (JSON.stringify(createScope(latestPlans)) !== JSON.stringify(createScope(beforePlans))) {
    throw new Error('拟新建任务范围发生变化，请重新运行查看新计划');
  }
  const activeLatest = latestPlans.filter((plan) => plan.gapMs > 0);
  if (activeLatest.length === 0) {
    console.info('重查后所有日期均已达到目标工时，无需写入。');
    return;
  }
  const titlesToCreate = createScope(activeLatest);
  titlesToCreate.forEach((title) => {
    if (findExactTask(latestTasks, title) !== null) throw new Error(`任务“${title}”已出现，请重新运行`);
  });
  if (titlesToCreate.length > 0) await validateCreationMetadata();

  // 从这里开始才出现写接口；此前只有查询、预览、确认、重查和元数据校验。
  async function createTask(title) {
    assertVerifiedS1867Configuration();
    const task = await api('/api/tasks', {
      method: 'POST',
      body: {
        content: title, _tasklistId: TASKLIST_ID, _stageId: STAGE_ID,
        _scenariofieldconfigId: SFC_ID, _taskflowstatusId: TFS_START_ID,
        _executorId: SELF_USER_ID, priority: 0,
      },
    });
    requireId(task._id, `创建任务“${title}”响应._id`);
    if (task.content !== undefined && task.content !== title) throw new Error(`创建任务“${title}”响应标题不匹配`);
    return { title, id: task._id };
  }

  function validateCreatedTask(created, graphTask, bulkTask) {
    assertVerifiedS1867Configuration();
    assertGraphTask(graphTask, created.title, `新建任务 ${created.id}`);
    assertBulkTask(bulkTask, created.title, `新建任务 ${created.id}`, true);
    if (graphTask.tasklistId !== TASKLIST_ID || graphTask.stageId !== STAGE_ID || graphTask.sfcId !== SFC_ID) {
      throw new Error(`新建任务 ${created.id} 的任务列表、阶段或 SFC 不匹配`);
    }
    for (const [field, expected] of [['_tasklistId', TASKLIST_ID], ['_stageId', STAGE_ID], ['_executorId', SELF_USER_ID]]) {
      if (bulkTask[field] !== undefined && bulkTask[field] !== expected) throw new Error(`新建任务 ${created.id}.${field} 不匹配`);
    }
  }

  function validateBatchRecords(request, result) {
    if (result.payload.length !== request.times.length) throw new Error('工时 batch 返回记录数与 times 数量不符');
    const desired = new Map(request.times.map((time) => [time.date, time]));
    const ids = new Set();
    const dates = new Set();
    return result.payload.map((record, index) => {
      assertObject(record, `工时 batch payload[${index}]`);
      requireId(record._id, `工时 batch payload[${index}]._id`);
      if (ids.has(record._id)) throw new Error(`工时 batch 重复记录 ID ${record._id}`);
      ids.add(record._id);
      if (record.objectType !== 'task' || record._objectId !== request.taskId) throw new Error(`工时记录 ${record._id} 任务不匹配`);
      const date = normalizeApiDate(record.date, `工时记录 ${record._id}.date`);
      if (dates.has(date) || !desired.has(date)) throw new Error(`工时记录 ${record._id} 日期不匹配`);
      dates.add(date);
      if (!Number.isSafeInteger(record.workTime) || record.workTime !== desired.get(date).time) {
        throw new Error(`工时记录 ${record._id} 时长不匹配`);
      }
      return { id: record._id, taskId: request.taskId, date, time: record.workTime };
    });
  }

  async function submitWorkTime(request) {
    const result = await api(`/work-time-server/api/work-time/batch?from=task&taskId=${encodeURIComponent(request.taskId)}&_userId=${encodeURIComponent(SELF_USER_ID)}`, {
      method: 'POST', expectArrayPayload: true,
      body: { _userId: SELF_USER_ID, _objectId: request.taskId, objectType: 'task', tagIds: [], times: request.times },
    });
    return validateBatchRecords(request, result);
  }

  const operationResults = [];
  const writeReceipts = [];
  const report = () => {
    if (writeReceipts.length > 0) console.table(writeReceipts);
    if (operationResults.length > 0) console.table(operationResults);
  };
  const createSettled = await Promise.allSettled(titlesToCreate.map((title) => createTask(title)));
  const created = [];
  createSettled.forEach((result, index) => {
    if (result.status === 'fulfilled') {
      created.push(result.value);
      writeReceipts.push({
        操作: '创建任务', 任务: result.value.title, 任务ID: result.value.id,
        结果: '响应已接受、等待独立验证', ok: null,
      });
    } else operationResults.push({ 操作: '创建任务', 任务: titlesToCreate[index], 结果: '失败或未知', 详情: String(result.reason?.message ?? result.reason), ok: false });
  });
  if (stableUnique(created.map((item) => item.id)).length !== created.length) throw new Error('创建接口为不同任务返回重复 ID');

  const verifiedCreated = new Map();
  if (created.length > 0) {
    try {
      const [createdBulk, createdGraph] = await Promise.all([
        queryTasksByIds(created.map((item) => item.id)), queryAllIncompleteTasks(),
      ]);
      created.forEach((item) => {
        try {
          validateCreatedTask(
            item,
            createdGraph.find((task) => task.id === item.id),
            requireBulkTask(createdBulk, item.id, `新建任务 ${item.id}`),
          );
          verifiedCreated.set(item.title, item.id);
          const receipt = writeReceipts.find((entry) => entry.操作 === '创建任务' && entry.任务ID === item.id);
          if (receipt) Object.assign(receipt, { 结果: '任务字段已验证、等待最终核对', ok: null });
        } catch (error) {
          const receipt = writeReceipts.find((entry) => entry.操作 === '创建任务' && entry.任务ID === item.id);
          if (receipt) Object.assign(receipt, { 结果: '响应已接受、独立验证失败/未知', 详情: error.message, ok: false });
          operationResults.push({ 操作: '验证新建任务', 任务: `${item.title} (${item.id})`, 结果: '失败', 详情: error.message, ok: false });
        }
      });
    } catch (error) {
      created.forEach((item) => {
        const receipt = writeReceipts.find((entry) => entry.操作 === '创建任务' && entry.任务ID === item.id);
        if (receipt) Object.assign(receipt, { 结果: '响应已接受、独立验证失败/未知', 详情: error.message, ok: false });
        operationResults.push({
          操作: '验证新建任务', 任务: `${item.title} (${item.id})`, 结果: '失败', 详情: error.message, ok: false,
        });
      });
    }
  }

  const candidatePlans = activeLatest.map((plan) => ({
    ...plan, taskId: plan.resolution === 'create' ? verifiedCreated.get(plan.taskTitle) ?? null : plan.taskId,
  }));
  candidatePlans.filter((plan) => !plan.taskId).forEach((plan) => operationResults.push({
    操作: '登记工时', 任务: plan.taskTitle, 结果: '跳过', 详情: `${plan.date} 无已验证任务 ID`, ok: false,
  }));
  const candidateIds = stableUnique(candidatePlans.map((plan) => plan.taskId).filter(Boolean));

  // 最终写前严格按 GraphQL → bulk → 日期聚合执行；日期聚合后除 batch 外不再发网络请求。
  const preBatchTasks = await queryAllIncompleteTasks();
  const graphValidIds = new Set();
  candidateIds.forEach((taskId) => {
    const plan = candidatePlans.find((item) => item.taskId === taskId);
    try {
      assertGraphTask(preBatchTasks.find((task) => task.id === taskId), plan.taskTitle, `写前任务 ${taskId}`);
      graphValidIds.add(taskId);
    } catch (error) {
      operationResults.push({ 操作: '最终任务预检', 任务: `${plan.taskTitle} (${taskId})`, 结果: '失败', 详情: error.message, ok: false });
    }
  });
  const preBatchBulk = await queryTasksByIds([...graphValidIds]);
  const validTaskIds = new Set();
  graphValidIds.forEach((taskId) => {
    const plans = candidatePlans.filter((plan) => plan.taskId === taskId);
    const title = plans[0].taskTitle;
    try {
      assertBulkTask(
        requireBulkTask(preBatchBulk, taskId, `写前任务 ${taskId}`), title, `写前任务 ${taskId}`,
        plans.some((plan) => plan.resolution === 'create'),
      );
      validTaskIds.add(taskId);
    } catch (error) {
      operationResults.push({ 操作: '最终任务预检', 任务: `${title} (${taskId})`, 结果: '失败', 详情: error.message, ok: false });
    }
  });
  const preBatchHours = await queryDailyHours();
  const preBatchSnapshot = lastDailySnapshot;
  if (!preBatchSnapshot) throw new Error('写前日期聚合快照缺失');

  const byTaskId = new Map();
  candidatePlans.forEach((plan) => {
    if (!plan.taskId || !validTaskIds.has(plan.taskId)) return;
    if (preBatchHours[plan.date] > TARGET_MS) throw new Error(`${plan.date} 写前已超额，疑似并发写入`);
    const gapMs = Math.max(0, TARGET_MS - preBatchHours[plan.date]);
    if (gapMs > plan.gapMs) throw new Error(`${plan.date} 写前缺口增加，超出已确认授权`);
    if (gapMs === 0) return;
    if (!byTaskId.has(plan.taskId)) byTaskId.set(plan.taskId, { taskId: plan.taskId, taskTitle: plan.taskTitle, times: [] });
    byTaskId.get(plan.taskId).times.push({ date: plan.date, time: gapMs, description: plan.description });
  });

  const workRequests = [...byTaskId.values()];
  const workSettled = await Promise.allSettled(workRequests.map((request) => submitWorkTime(request)));
  const unknownDates = new Set();
  let submittedRecords = [];
  workSettled.forEach((result, index) => {
    const request = workRequests[index];
    if (result.status === 'fulfilled') {
      submittedRecords.push(...result.value);
      result.value.forEach((record) => writeReceipts.push({
        操作: '登记工时', 任务: request.taskTitle, 任务ID: record.taskId, 工时记录ID: record.id,
        日期: record.date, 时长: formatMs(record.time), 结果: '响应已接受、等待独立验证', ok: null,
      }));
    } else {
      request.times.forEach((time) => unknownDates.add(time.date));
      operationResults.push({
        操作: '登记工时', 任务: `${request.taskTitle} (${request.taskId})`, 结果: '失败或未知',
        详情: String(result.reason?.message ?? result.reason), ok: false,
      });
    }
  });
  const submittedIds = submittedRecords.map((record) => record.id);
  if (stableUnique(submittedIds).length !== submittedIds.length) {
    workRequests.flatMap((request) => request.times).forEach((time) => unknownDates.add(time.date));
    operationResults.push({ 操作: '登记工时响应校验', 任务: '全部请求', 结果: '失败', 详情: '跨 batch 返回重复记录 ID', ok: false });
    submittedRecords = [];
  }

  let afterHours;
  let afterSnapshot;
  try {
    afterHours = await queryDailyHours();
    afterSnapshot = lastDailySnapshot;
    if (!afterSnapshot) throw new Error('写后日期聚合快照缺失');
  } catch (error) {
    writeReceipts.forEach((entry) => {
      if (entry.ok !== false) {
        Object.assign(entry, { 结果: '响应已接受、独立验证失败/未知', 详情: error.message, ok: false });
      }
    });
    report();
    throw error;
  }
  writeReceipts.filter((entry) => entry.操作 === '创建任务' && entry.ok === null).forEach((entry) => {
    Object.assign(entry, { 结果: '独立验证成功', ok: true });
  });
  const verification = TARGET_DATES.map((date) => {
    const before = preBatchSnapshot.days[date];
    const after = afterSnapshot.days[date];
    const expected = submittedRecords.filter((record) => record.date === date);
    const expectedTime = expected.reduce((sum, record) => sum + record.time, 0);
    const recordsMatch = expected.every((record) => {
      const found = after.objects.find((item) => item.id === record.id);
      return found?.objectType === 'task' && found.taskId === record.taskId && found.time === record.time &&
        !before.objects.some((item) => item.id === record.id);
    });
    const countMatch = after.count - before.count === expected.length;
    const timeMatch = after.workTime - before.workTime === expectedTime;
    let result = '成功';
    if (afterHours[date] > TARGET_MS) result = '超额/并发冲突';
    else if (afterHours[date] < TARGET_MS) result = '不足';
    else if (unknownDates.has(date)) result = '写入结果未知';
    else if (!recordsMatch || !countMatch || !timeMatch) result = '记录核对失败';
    expected.forEach((record) => {
      const receipt = writeReceipts.find((entry) => entry.工时记录ID === record.id);
      if (receipt) Object.assign(receipt, {
        结果: result === '成功' ? '独立验证成功' : '响应已接受、独立验证失败/未知',
        详情: result === '成功' ? undefined : result,
        ok: result === '成功',
      });
    });
    return {
      日期: date, 写前: formatMs(before.workTime), 写后: formatMs(afterHours[date]), 目标: formatMs(TARGET_MS),
      新增记录: expected.length, count变化: after.count - before.count, 结果: result,
    };
  });
  report();
  console.table(verification);
  const failed = writeReceipts.some((item) => item.ok !== true) || operationResults.some((item) => item.ok === false) || verification.some((item) => item.结果 !== '成功');
  if (failed) {
    console.error('存在失败、未知、记录不匹配、不足或超额日期。请重新运行查询当前缺口，不要盲目重放旧请求。');
  } else {
    console.info('所有日期严格达到目标工时，本次记录已逐项核对；任务状态未被修改。');
  }
})().catch((error) => {
  console.error('脚本安全停止：', error instanceof Error ? error.message : String(error));
  console.info('若此前已有写请求，可能已部分成功；请重新运行查询当前缺口，不要重放旧请求。');
});
