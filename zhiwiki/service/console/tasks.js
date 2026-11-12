/* Persistent task views poll only while active, and never invent completion. */
import {api,PREFIX,query} from './api.js';
import {el,button,heading,empty,actions,table,pager,badge,time,busy,showError,metadata,stateLabels} from './ui.js';

const active=new Set(['queued','parsing','cancel_requested','publishing']);
export async function mount(ctx) {
  ctx.root.append(heading('导入任务','查看服务器保存的处理状态。失败可以恢复，新稿处理不会中断已经发布的资料。'));
  if(!ctx.canEdit || !ctx.kb) {ctx.root.append(empty('需要知识库编辑权限','只读使用者请从资料目录检索已发布内容。'));return;}
  if(ctx.params.get('job')) return detail(ctx);
  const filter=el('select',{'aria-label':'任务状态'});
  filter.append(el('option',{value:'',text:'全部状态'}),...Object.entries(stateLabels).filter(([key])=>!['staging','published','archived'].includes(key)).map(([value,text])=>el('option',{value,text})));
  filter.value=ctx.params.get('status') || '';
  filter.addEventListener('change',()=>ctx.go('tasks',{status:filter.value}));
  ctx.root.append(actions(filter,button('刷新列表',()=>ctx.go('tasks',{status:filter.value})),button('导入资料',()=>ctx.go('documents',{action:'upload'}),true)));
  const data=await api(query(PREFIX+'/jobs',{knowledge_base_id:ctx.kb.id,status:filter.value,cursor:ctx.params.get('cursor'),limit:20}),{signal:ctx.signal});
  if(!data.jobs.length) {ctx.root.append(empty('没有符合条件的任务','可以调整状态，或导入一份新资料。'));return;}
  ctx.root.append(table(['资料与任务','状态','页数','尝试与更新','操作'],data.jobs.map(item=>[
    el('div',{},[el('strong',{text:item.title}),el('small',{text:item.job_id})]),badge(item.status),`${item.pages_done} / ${item.pages_total??'待确定'}`,
    el('div',{},[String(item.attempt)+' 次',el('small',{text:time(item.updated_at)})]),button('跟进任务',()=>ctx.go('tasks',{job:item.job_id}))
  ])),pager(ctx,data.next_cursor,{status:filter.value}));
}

async function detail(ctx) {
  const job=ctx.params.get('job'),body=el('div'),error=el('div');
  ctx.root.append(actions(button('返回任务列表',()=>ctx.go('tasks')),button('刷新状态',()=>load())),body,error);
  let timer;
  ctx.signal.addEventListener('abort',()=>clearTimeout(timer),{once:true});
  async function load() {
    clearTimeout(timer);
    if(ctx.signal.aborted) return;
    try {
      if(document.hidden) {timer=setTimeout(load,3000);return;}
      const result=await api(`${PREFIX}/jobs/${encodeURIComponent(job)}`,{signal:ctx.signal});
      if(result.knowledge_base_id!==ctx.kb.id) throw new Error('任务与当前知识库不一致，请从对应知识库的任务列表进入。');
      error.replaceChildren(); body.replaceChildren(taskSummary(result),taskActions(ctx,result,load,error));
      if(active.has(result.status)) timer=setTimeout(load,3000);
    } catch(problem) {showError(error,problem);}
  }
  await load();
}

function taskSummary(item) {
  const progress=el('progress',{className:'task-progress',max:item.pages_total || 1,value:item.pages_done,'aria-label':'已处理页数'});
  return el('section',{className:'paper'},[
    el('h2',{text:item.filename}),badge(item.status),progress,
    metadata({'任务 ID':item.job_id,'资料来源':item.source_key,'处理页数':`${item.pages_done} / ${item.pages_total??'待确定'}`,'尝试次数':item.attempt,'最后更新':time(item.updated_at)}),
    item.error?el('p',{className:'error-text',text:'后台处理失败：'+item.error+'。原始文件与任务记录保留，请检查原因后重试。'}):null,
    el('p',{className:'hint',text:'任务详情可通过当前网址重新进入。ready 表示发布链路完成；待审稿不会进入普通检索。'})
  ]);
}

function taskActions(ctx,item,reload,error) {
  const controls=[];
  for(const [action,label,enabled] of [['cancel','取消任务',['queued','parsing'].includes(item.status)],['retry','重试原任务',['failed','cancelled'].includes(item.status)&&item.attempt<3]]) {
    const control=button(label,()=>busy(control,async()=>{
      await api(`${PREFIX}/jobs/${encodeURIComponent(item.job_id)}:${action}`,{method:'POST',signal:ctx.signal});
      ctx.notify(action==='cancel'?'取消请求已提交，以服务端状态为准。':'重试已接收，将继续跟进原任务。'); await reload();
    },error),false,!enabled);
    controls.push(control);
  }
  if(['needs_review','awaiting_publish','ready'].includes(item.status)) controls.push(button('打开修订原文',()=>ctx.go('review',{book:item.document_id,revision:item.revision_id}),true));
  return actions(...controls);
}
