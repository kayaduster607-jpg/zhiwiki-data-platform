/* Document directory, bounded revision history and real multipart imports. */
import {api,PREFIX,query,requestKey} from './api.js';
import {el,button,field,heading,empty,actions,table,pager,badge,time,busy} from './ui.js';

export async function mount(ctx) {
  const mode=ctx.params.get('action');
  if(mode==='upload') return uploadForm(ctx);
  if(mode==='history') return history(ctx);
  ctx.root.append(heading('资料与版本','更新新修订时，当前公开版本继续服务。只有明确复核发布后，使用者才会取得新版。'));
  if(!ctx.kb) { ctx.root.append(empty('还没有可访问的知识库','管理员可在账号与接入页创建知识库并授权。')); return; }
  if(ctx.canEdit) ctx.root.append(actions(button('导入资料',()=>ctx.go('documents',{action:'upload'}),true)));
  const result=await api(query(PREFIX+'/documents',{knowledge_base_id:ctx.kb.id,cursor:ctx.params.get('cursor'),limit:20}),{signal:ctx.signal});
  if(!result.documents.length) {ctx.root.append(empty('当前没有资料','编辑员导入资料后，复核发布才能进入普通使用者的目录。'));return;}
  ctx.root.append(table(['资料来源','当前公开版本','操作'],result.documents.map(item=>[
    el('div',{},[el('strong',{text:item.title}),el('small',{text:item.source_key})]),
    item.current_revision?el('div',{},[badge('published'),el('small',{text:'v'+item.current_number})]):badge('staging'),
    documentActions(ctx,item)
  ])),pager(ctx,result.next_cursor));
}

function documentActions(ctx,item) {
  const controls=[];
  if(item.current_revision) controls.push(button('查看原文',()=>ctx.go('review',{book:item.id,revision:item.current_revision})));
  if(ctx.canEdit) {
    controls.push(button('修订历史',()=>ctx.go('documents',{action:'history',book:item.id})));
    if(item.current_revision) controls.push(button('导入新版',()=>ctx.go('documents',{action:'upload',book:item.id,revision:item.current_revision})));
  }
  return el('div',{className:'cell-actions'},controls);
}

async function history(ctx) {
  ctx.root.append(heading('修订历史','保留历史版本与原文件，区分当前公开版和仍在处理的修订。'));
  if(!ctx.canEdit) {ctx.root.append(empty('需要资料编辑权限','只读使用者可从目录查看当前公开原文。'));return;}
  const book=ctx.params.get('book');
  const result=await api(query(`${PREFIX}/documents/${encodeURIComponent(book)}/revisions`,{cursor:ctx.params.get('cursor'),limit:20}),{signal:ctx.signal});
  ctx.root.append(actions(button('返回资料目录',()=>ctx.go('documents'))));
  if(!result.revisions.length) {ctx.root.append(empty('没有修订记录','请刷新或查看导入任务。'));return;}
  ctx.root.append(table(['版本','状态','原始文件','创建时间','操作'],result.revisions.map(item=>[
    'v'+item.number+(item.revision_id===result.current_revision?' · 当前公开':''),badge(item.status),item.filename,time(item.created),
    button('打开修订',()=>ctx.go('review',{book,revision:item.revision_id}))
  ])),pager(ctx,result.next_cursor,{action:'history',book}));
}

async function uploadForm(ctx) {
  const book=ctx.params.get('book'),revision=ctx.params.get('revision');
  ctx.root.append(heading(book?'导入新版资料':'导入资料','文件接收后交给独立 worker 处理。提交成功仅表示已接收，不代表已经对外发布。'));
  if(!ctx.canEdit || !ctx.kb) {ctx.root.append(empty('需要知识库编辑权限','请联系管理员确认知识库授权。'));return;}
  let current=null;
  if(book) {
    current=await api(`${PREFIX}/documents/${encodeURIComponent(book)}/revisions/${encodeURIComponent(revision)}`,{signal:ctx.signal});
    if(current.knowledge_base_id!==ctx.kb.id) throw new Error('更新目标与当前知识库不一致，请重新选择资料。');
    if(current.current_revision!==revision) {ctx.root.append(empty('当前公开版已经变化','请返回资料目录重新选择最新版本。'),actions(button('返回资料目录',()=>ctx.go('documents'))));return;}
  }
  buildUploadForm(ctx,current,book,revision);
}

function buildUploadForm(ctx,current,book,revision) {
  const file=el('input',{type:'file',accept:'.pdf,.md,.txt,.docx,.csv,.json',required:true});
  const source=el('input',{value:current?.source_key || '',maxLength:200,required:true,readOnly:!!book,placeholder:'例如 return-policy，用于识别同一资料来源'});
  const error=el('div',{role:'alert'}),form=el('form',{className:'form-stack'});
  const submit=el('button',{type:'submit',className:'primary',text:'提交导入'});
  let lastSignature='',key='';
  form.append(field('当前知识库',el('input',{value:ctx.kb.title,readOnly:true})),field('稳定来源键',source),field('选择资料文件',file),
    el('p',{className:'hint',text:`文本资料最大 ${Math.floor(ctx.limits.max_text_upload_bytes/1048576)} MiB，PDF 最大 ${Math.floor(ctx.limits.max_upload_bytes/1048576)} MiB。`}),submit,error);
  form.addEventListener('submit',event=>{
    event.preventDefault(); error.replaceChildren();
    busy(submit,async()=>{
      const selected=file.files[0]; validateFile(selected,ctx.limits);
      const signature=JSON.stringify([ctx.kb.id,source.value,book,revision,selected.name,selected.size,selected.lastModified]);
      if(signature!==lastSignature) {lastSignature=signature;key=requestKey();}
      const data=uploadBody(selected,source.value,ctx.kb.id,book,revision);
      const result=await api(query(PREFIX+'/uploads',{knowledge_base_id:ctx.kb.id}),{method:'POST',body:data,headers:{'Idempotency-Key':key},signal:ctx.signal});
      ctx.notify('资料已接收。请继续跟进任务，完成复核发布。'); ctx.go('tasks',{job:result.job_id});
    },error);
  });
  ctx.root.append(form,actions(button('返回资料目录',()=>ctx.go('documents'))));
}

function validateFile(file,limits) {
  if(!file) throw new Error('请选择一个资料文件。');
  if(file.name.toLowerCase().startsWith('.env')) throw new Error('不允许选择环境或凭证文件。');
  const suffix=file.name.split('.').pop().toLowerCase();
  if(!['pdf','md','txt','docx','csv','json'].includes(suffix)) throw new Error('不支持这个文件类型。');
  const maximum=suffix==='pdf'?limits.max_upload_bytes:limits.max_text_upload_bytes;
  if(!file.size || file.size>maximum) throw new Error('文件为空或超过允许大小，请调整后重试。');
}
function uploadBody(file,source,kb,book,revision) {
  const body=new FormData();
  body.set('file',file); body.set('knowledge_base_id',kb); body.set('mode',book?'update':'new'); body.set('logical_source_key',source.trim());
  if(book) {body.set('document_id',book);body.set('expected_revision_id',revision);}
  return body;
}
