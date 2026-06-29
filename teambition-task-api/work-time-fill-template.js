/**
 * 端到端脚本模板：按缺口把多天工时补到目标时长（如每天 8h）
 *
 * 用途：根据 git 记录新建任务、标记已完成，并把指定日期工时补到每天目标时长。
 *       已有工时按缺口自动缩减，确保不超标。
 *
 * 用法：
 *   1. 浏览器打开 https://tb.cet-electric.com:4753 任意页面，确认已登录
 *   2. F12 → Console 控制台
 *   3. 填好下方【配置区】和 TASKS 计划（每天各任务 hours 之和 = 目标时长）
 *   4. 复制本文件全部内容粘贴回车，弹窗确认；脚本末尾打印验证结果
 *   5. 只运行一次；重跑会重复建任务+工时
 *
 * 机制要点：
 *   - scale 保证不超标：当天已有工时越多，新增越少；已满则该天不登记
 *   - 每天所有任务 hours 之和必须 = 目标时长，缩放后才会精确补到目标
 */
(async () => {
  // ===== 配置（按项目替换）=====
  const ORG_ID = '66acf1018881ceb6d5324658';
  const USER_ID = '66c4be9751257bcd6ccc6033';
  const TASKLIST_ID = '695b09c72eadc394afddb900';
  const STAGE_ID = '695b09c72eadc394afddb970';
  const SFC_ID = '695b09c82eadc394afddbc59';          // 需求
  const TFS_START_ID = '695b09c72eadc394afddb904';    // 待处理(起始)
  const TFS_END_ID = '695b09c72eadc394afddb907';      // 已完成(终态)
  const DATES = ['2026-06-22','2026-06-23','2026-06-24'];
  const TARGET_MS = 8 * 3600000;  // 每天目标 8h

  // ===== 计划：每个任务及各天工时(hours)，每天合计必须 = 目标时长 =====
  const TASKS = [
    { content:'任务A', times:[{date:'2026-06-22',hours:4,description:'描述'}]},
    { content:'任务B', times:[
        {date:'2026-06-22',hours:4,description:'描述'},
        {date:'2026-06-23',hours:8,description:'描述'}]},
    // ...
  ];

  const headers = () => ({'Content-Type':'application/json','x-organization-id':ORG_ID,'x-user-id':USER_ID});
  async function api(path,{method='GET',body}={}){
    const res = await fetch(path,{method,headers:headers(),body:body?JSON.stringify(body):undefined});
    const txt = await res.text(); let data; try{data=JSON.parse(txt);}catch{data=txt;}
    if(!res.ok) throw new Error(`${method} ${path} -> ${res.status}: ${txt}`);
    return data;
  }
  async function queryDaily(){
    const r = await api('/work-time-server/api/work-time/aggregation/dates',{method:'POST',
      body:{startDate:DATES[0],endDate:DATES[DATES.length-1],userIds:[USER_ID],
            filter:{project:{},task:{isArchived:false},customfield:{}}}});
    const map = Object.fromEntries(DATES.map(d=>[d,0]));
    for(const it of (r.payload||[])){ const d=(it.date||'').slice(0,10); if(d in map) map[d]+=it.workTime||0; }
    return map;
  }

  if(!location.host.includes('tb.cet-electric.com')) console.warn('⚠️ 请在 Teambition 页面控制台运行');
  if(!confirm(`新建 ${TASKS.length} 个任务并标记完成，把工时补到每天 ${TARGET_MS/3600000}h。确认？`)) return;

  // 1) 现有工时 → 每天缺口缩放系数 = max(0, 目标-现有) / 目标
  const before = await queryDaily();
  const scale = Object.fromEntries(DATES.map(d=>[d,Math.max(0,TARGET_MS-before[d])/TARGET_MS]));
  console.log('现有工时(ms)/缩放系数：', before, scale);

  // 2) 创建任务（起始态）
  for(const t of TASKS){
    const c = await api('/api/tasks',{method:'POST',body:{content:t.content,_tasklistId:TASKLIST_ID,
      _stageId:STAGE_ID,_scenariofieldconfigId:SFC_ID,_taskflowstatusId:TFS_START_ID,priority:0}});
    t._id = c._id; console.log('创建:',t.content,t._id);
  }
  // 3) 标记已完成（跳过必填校验）
  for(const t of TASKS){
    await api(`/api/tasks/${t._id}/taskflowstatus`,{method:'PUT',body:{_taskflowstatusId:TFS_END_ID,
      _scenariofieldconfigId:SFC_ID,sfcRequiredValidateEnable:false,persistentValidatorEnable:false,disableRequiredCfIds:[]}});
  }
  // 4) 登记工时（按当天缺口缩放，已满则跳过）
  for(const t of TASKS){
    const times = t.times.map(w=>({date:w.date,time:Math.round(w.hours*3600000*scale[w.date]),description:w.description})).filter(x=>x.time>0);
    if(!times.length) continue;
    await api(`/work-time-server/api/work-time/batch?from=task&taskId=${t._id}&_userId=${USER_ID}`,
      {method:'POST',body:{_userId:USER_ID,_objectId:t._id,objectType:'task',tagIds:[],times}});
  }
  // 5) 验证
  const after = await queryDaily();
  for(const d of DATES){ const h=after[d]/3600000; console.log(`${d}: ${h.toFixed(2)}h`, h+1e-6>=TARGET_MS/3600000?'✓ 满':'✗ 不足'); }
})().catch(e=>console.error('出错：',e.message||e));
