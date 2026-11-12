import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';

const project = '695b09c7b842a4a0fd053603';
const list = '695b09c72eadc394afddb900';
const stage = '695b09c72eadc394afddb970';
const origin = 'https://tb.cet-electric.com:4753';
const flow = '695b09c72eadc394afddb8ef';
const needFlow = '695b09c72eadc394afddb8e4';
const needSfc = '695b09c82eadc394afddbc59';
const startId = '695b09c72eadc394afddb904';
const testSfc = '695b09c82eadc394afddbd35';
const metadataFile = new URL('../references/api.md', import.meta.url);
const templateFile = new URL('../work-time-fill-template.js', import.meta.url);
const metadataDoc = readFileSync(metadataFile, 'utf8');
const template = readFileSync(templateFile, 'utf8').replace(/\r\n/g, '\n');
const example = metadataDoc.match(/<!-- workflow-metadata-example:start -->\s*```javascript\s*([\s\S]*?)\s*```\s*<!-- workflow-metadata-example:end -->/);
assert.ok(example, 'API 文档必须包含可执行的只读工作流查询示例');

function status(id, name, kind, flowId = flow) {
  return { _id: id, name, kind, _taskflowId: flowId, isArchived: false };
}

function testConfiguration() {
  return {
    _id: testSfc, name: '测试单', _projectId: project, objectType: 'task', isArchived: false,
    _taskflowId: flow, taskflowstatuses: [
      status('695b09c72eadc394afddb92d', '待处理', 'start'),
      status('695b09c72eadc394afddb92e', '已提测', 'unset'),
      status('695b09c72eadc394afddb92f', '已完成', 'end'),
    ],
    ignoredSensitiveField: 'signed-url-secret',
  };
}

async function runExample(data, action = 'start', overrides = {}) {
  const code = example[1]
    .replace('已确认的部署 origin', origin)
    .replace('本次项目 ID', project)
    .replace('本次任务类型名称', '测试单')
    .replace('action: "start"', `action: "${action}"`);
  const calls = [];
  const context = {
    location: overrides.location ?? { origin, pathname: '/project/current' },
    fetch: async (path, options) => {
      calls.push({ path, options });
      return { ok: true, redirected: false, status: 200, json: async () => data, ...overrides.response };
    },
  };
  const result = await runInNewContext(`(${code})`, context)();
  return { result: JSON.parse(JSON.stringify(result)), calls };
}

test('只读示例选择真实的起始、中间和终态，并只返回必要字段', async () => {
  for (const [action, expected] of [
    ['start', '695b09c72eadc394afddb92d'],
    ['submit', '695b09c72eadc394afddb92e'],
    ['end', '695b09c72eadc394afddb92f'],
  ]) {
    const { result, calls } = await runExample([testConfiguration()], action);
    assert.equal(result.status.id, expected);
    assert.equal(result.sfc.id, testSfc);
    assert.equal(calls.length, 1);
    assert.match(calls[0].path, /objectType=task&withTaskflowstatus=true$/);
    assert.equal(calls[0].options.credentials, 'same-origin');
    assert.equal(calls[0].options.method, undefined);
    assert.doesNotMatch(JSON.stringify(result), /signed-url-secret/);
  }
});

test('只读示例遇到缺失、歧义、错误归属、重复 ID 或未知状态时停止', async () => {
  const duplicateSfc = testConfiguration();
  const wrongProject = { ...testConfiguration(), _projectId: 'aaaaaaaaaaaaaaaaaaaaaaaa' };
  const wrongFlow = testConfiguration();
  wrongFlow.taskflowstatuses[0]._taskflowId = needFlow;
  const duplicateStatus = testConfiguration();
  duplicateStatus.taskflowstatuses.push({ ...duplicateStatus.taskflowstatuses[0], _id: duplicateStatus.taskflowstatuses[0]._id.toUpperCase(), kind: 'end' });
  const twoStarts = testConfiguration();
  twoStarts.taskflowstatuses.push(status('aaaaaaaaaaaaaaaaaaaaaaaa', '重新打开', 'start'));
  const archived = testConfiguration();
  archived.taskflowstatuses[0].isArchived = true;
  const unknownKind = testConfiguration();
  unknownKind.taskflowstatuses[1].kind = 'unknown';
  const missingFlag = testConfiguration();
  delete missingFlag.taskflowstatuses[0].isArchived;
  for (const data of [[], [duplicateSfc, structuredClone(duplicateSfc)], [wrongProject], [wrongFlow],
    [duplicateStatus], [twoStarts], [archived], [unknownKind], [missingFlag], {}]) {
    await assert.rejects(runExample(data));
  }
  await assert.rejects(runExample([testConfiguration()], 'submit', {
    location: { origin: 'https://wrong.example', pathname: '/' },
  }));
  await assert.rejects(runExample([testConfiguration()], 'submit', {
    response: { redirected: true },
  }));
});

const commonStart = template.indexOf('  const PLACEHOLDER =');
const commonEnd = template.indexOf('  function normalizeApiDate(', commonStart);
const gateStart = template.indexOf('  function metadataArray(');
const gateEnd = template.indexOf('  const [beforeHours, beforeTasks, beforeBulk]', gateStart);
assert.ok(commonStart >= 0 && commonEnd > commonStart && gateStart >= 0 && gateEnd > gateStart, '工时模板校验入口缺失');
const gateCode = `(async () => {\n${template.slice(commonStart, commonEnd)}\n${template.slice(gateStart, gateEnd)}\nawait validateCreationMetadata();\n})()`;

function templateData() {
  return {
    lists: [{ _id: list, _projectId: project, isArchived: false }],
    stages: [{ _id: stage, _projectId: project, _tasklistId: list, isArchived: null }],
    sfcs: [{
      _id: needSfc, name: '需求', _projectId: project, objectType: 'task', isArchived: false,
      _taskflowId: needFlow, taskflowstatuses: [
        status(startId, '待处理', 'start', needFlow),
        status('695b09c72eadc394afddb907', '已完成', 'end', needFlow),
      ],
    }],
  };
}

async function runTemplateGate(data) {
  const calls = [];
  const context = {
    ORG_ID: '66acf1018881ceb6d5324658', PROJECT_ID: project, TASKLIST_ID: list, STAGE_ID: stage,
    SFC_ID: needSfc, TFS_START_ID: startId,
    api: async path => {
      calls.push(path);
      if (path.startsWith('/api/tasklists?')) return data.lists;
      if (path.startsWith('/api/stages?')) return data.stages;
      if (path.includes('/scenariofieldconfigs?objectType=task&withTaskflowstatus=true')) return data.sfcs;
      throw new Error('未预期的请求');
    },
  };
  await runInNewContext(gateCode, context);
  return calls;
}

test('工时模板写前实时验证固定 904，接受项目实际返回的阶段 null', async () => {
  const calls = await runTemplateGate(templateData());
  assert.equal(calls.length, 3);
  assert.ok(calls.some(path => path.includes('withTaskflowstatus=true')));
});

test('工时模板拒绝项目或阶段不匹配以及失效、歧义和重复的状态配置', async () => {
  const cases = [
    data => { data.lists[0]._projectId = 'aaaaaaaaaaaaaaaaaaaaaaaa'; },
    data => { data.lists.push(structuredClone(data.lists[0])); },
    data => { data.stages[0]._tasklistId = 'aaaaaaaaaaaaaaaaaaaaaaaa'; },
    data => { data.stages[0].isArchived = true; },
    data => { data.sfcs[0]._projectId = 'aaaaaaaaaaaaaaaaaaaaaaaa'; },
    data => { data.sfcs[0].taskflowstatuses[0]._taskflowId = flow; },
    data => { data.sfcs[0].taskflowstatuses[0].kind = 'unset'; },
    data => { data.sfcs[0].taskflowstatuses[0].isArchived = true; },
    data => { data.sfcs[0].taskflowstatuses.push(status('aaaaaaaaaaaaaaaaaaaaaaaa', '额外起始状态', 'start', needFlow)); },
    data => { data.sfcs[0].taskflowstatuses.push({ ...data.sfcs[0].taskflowstatuses[0], _id: startId.toUpperCase(), kind: 'end' }); },
    data => { delete data.sfcs[0].taskflowstatuses; },
  ];
  for (const change of cases) {
    const data = templateData();
    change(data);
    await assert.rejects(runTemplateGate(data));
  }
});

async function runTemplateScenario(data) {
  const replacements = {
    REPLACE_WITH_ORGANIZATION_ID: '66acf1018881ceb6d5324658',
    REPLACE_WITH_CURRENT_USER_ID: '66c4be9751257bcd6ccc6033',
    REPLACE_WITH_PROJECT_ID: project,
    REPLACE_WITH_TASKLIST_ID: list,
    REPLACE_WITH_STAGE_ID: stage,
    REPLACE_WITH_SFC_ID: needSfc,
    REPLACE_WITH_VERIFIED_START_STATUS_ID: startId,
    REPLACE_WITH_TEAMBITION_ORIGIN: origin,
    REPLACE_WITH_TARGET_MILLISECONDS: '3600000',
  };
  let code = template;
  for (const [placeholder, value] of Object.entries(replacements)) code = code.replace(placeholder, value);
  const plansStart = code.indexOf('  const WORK_PLANS = [');
  const plansEnd = code.indexOf('\n\n  if (location.origin', plansStart);
  assert.ok(plansStart >= 0 && plansEnd > plansStart, '工时模板计划入口缺失');
  code = `${code.slice(0, plansStart)}  const WORK_PLANS = [{ date: '2026-11-12', mode: 'create-if-missing', title: '模拟任务', description: '模拟验证' }];${code.slice(plansEnd)}`;
  const calls = [];
  const errors = [];
  const context = {
    URL, location: { origin, href: `${origin}/project/current` }, window: { confirm: () => true },
    console: { table() {}, info() {}, warn() {}, error: (...args) => errors.push(args.map(String).join(' ')), log() {} },
    fetch: async (path, options = {}) => {
      const url = new URL(path, origin);
      calls.push({ path: url.pathname, method: options.method ?? 'GET' });
      let result;
      if (url.pathname === '/work-time-server/api/work-time/aggregation/dates') result = { ok: true, payload: [] };
      else if (url.pathname === '/api/v2/graphql') {
        result = { data: { organization: { tasks: { nodes: [], pageInfo: { hasNextPage: false, endCursor: null } } } } };
      } else if (url.pathname === '/api/tasklists') result = data.lists;
      else if (url.pathname === '/api/stages') result = data.stages;
      else if (url.pathname.endsWith('/scenariofieldconfigs')) result = data.sfcs;
      else if (url.pathname === '/api/tasks') throw new Error('模拟写入，未调用外部服务');
      else throw new Error(`未预期的模拟请求: ${url.pathname}`);
      return { ok: true, status: 200, redirected: false, url: url.href, text: async () => JSON.stringify(result) };
    },
  };
  let error = null;
  try { await runInNewContext(code, context); } catch (cause) { error = cause; }
  return { calls, error, errors };
}

test('完整工时模板在状态无效时不发起任务创建或工时写入', async () => {
  const invalid = templateData();
  invalid.sfcs[0].taskflowstatuses[0].kind = 'unset';
  const blocked = await runTemplateScenario(invalid);
  assert.match(blocked.errors.join('\n'), /有效起始状态不唯一或不是 904/);
  assert.ok(blocked.calls.some(call => call.path.endsWith('/scenariofieldconfigs')));
  assert.equal(blocked.calls.some(call => call.path === '/api/tasks'), false);
  assert.equal(blocked.calls.some(call => call.path === '/work-time-server/api/work-time/batch'), false);

  const valid = await runTemplateScenario(templateData());
  assert.ok(valid.calls.some(call => call.path === '/api/tasks' && call.method === 'POST'));
  assert.equal(valid.calls.some(call => call.path === '/work-time-server/api/work-time/batch'), false);
});
