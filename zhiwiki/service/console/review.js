/* Review the actual revision, preserve conflicts, and publish conditionally. */
import {api,PREFIX,query,requestKey} from './api.js';
import {el,button,field,heading,empty,actions,table,pager,badge,busy,metadata,details,dirtyGuard} from './ui.js';

export async function mount(ctx) {
  const book=ctx.params.get('book'),revision=ctx.params.get('revision');
  ctx.root.append(heading(book?'修订原文与发布':'复核与发布','逐页核对原始抽取和校订文本。校订会撤销复核，发布需要当前版本条件。'));
  if(book && revision) return revisionPage(ctx,book,revision);
  if(!ctx.canEdit || !ctx.kb) {ctx.root.append(empty('需要资料编辑权限','只读使用者可从资料目录打开当前公开原文。'));return;}
  const data=await api(query(PREFIX+'/review-queue',{knowledge_base_id:ctx.kb.id,cursor:ctx.params.get('cursor'),limit:20}),{signal:ctx.signal});
  ctx.root.append(actions(button('刷新待审列表',()=>ctx.go('review'))));
  if(!data.revisions.length) {ctx.root.append(empty('当前没有待审资料','新资料解析后会进入这里，已发布修订自动退出。'));return;}
  ctx.root.append(table(['资料与修订','状态','质量与复核','操作'],data.revisions.map(item=>[
    el('div',{},[el('strong',{text:item.title}),el('small',{text:'v'+item.number+' · '+item.source_key})]),badge(item.status),
    `${item.quality.flagged_pages??0} 页有提示 · ${item.reviewed?'已复核':'未复核'}`,
    button('核对修订',()=>ctx.go('review',{book:item.document_id,revision:item.revision_id}),true)
  ])),pager(ctx,data.next_cursor));
}

async function revisionPage(ctx,book,revision) {
  const path=`${PREFIX}/documents/${encodeURIComponent(book)}/revisions/${encodeURIComponent(revision)}`;
  const data=await api(path,{signal:ctx.signal});
  if(data.knowledge_base_id!==ctx.kb?.id) throw new Error('修订与当前知识库不一致，请从对应知识库的资料目录进入。');
  const pageNumber=Number(ctx.params.get('page') || 1);
  if(!Number.isInteger(pageNumber) || pageNumber<1 || pageNumber>Math.max(1,data.page_count)) throw new Error('页码不在当前修订范围内。');
  ctx.root.append(actions(button('返回资料目录',()=>ctx.go('documents')),ctx.canEdit?button('返回待审列表',()=>ctx.go('review')):null),
    el('div',{className:'paper'},[el('h2',{text:data.filename}),badge(data.status),metadata({'修订':'v'+data.number,'当前公开修订':data.current_revision || '尚无','复核状态':data.reviewed?'已复核':'未复核','正文页数':data.page_count})]));
  if(!data.page_count) {ctx.root.append(empty('当前没有可读取正文','请查看导入任务的状态和解析错误。'));return;}
  const page=await api(path+'/pages/'+pageNumber,{signal:ctx.signal});
  renderPage(ctx,{book,revision,path,data,page,pageNumber});
}

function renderPage(ctx,model) {
  const {book,revision,path,data,page,pageNumber}=model;
  const editable=ctx.canEdit && ['needs_review','awaiting_publish'].includes(data.status);
  const selector=el('input',{type:'number',min:1,max:data.page_count,value:pageNumber,'aria-label':'原文页码'});
  const editor=el('textarea',{value:page.text,rows:14,maxLength:500000,readOnly:!editable,'aria-label':'当前校订正文'});
  const note=el('textarea',{rows:3,minLength:5,maxLength:1000,'aria-label':'操作说明',placeholder:'说明本次校订或复核依据，至少 5 个字。'});
  const error=el('div',{role:'alert'});
  let original=page.text;
  const isDirty=()=>editor.value!==original;
  ctx.setGuard(isDirty); dirtyGuard(ctx.signal,isDirty);
  const refresh=()=>ctx.go('review',{book,revision,page:pageNumber});
  const pageControls=actions(field('页码',selector),button('读取此页',()=>ctx.go('review',{book,revision,page:selector.value})),button('重新读取本页',refresh));
  const source=el('section',{className:'paper'},[el('h2',{text:'原始抽取文本'}),el('div',{className:'prose',text:page.raw_text}),details('本页质量提示',page.quality)]);
  const current=el('section',{className:'form-stack'},[el('h2',{text:editable?'校订正文':'当前正文'}),editor]);
  if(editable) {
    current.append(field('校订或复核说明',note));
    const controls=reviewControls(ctx,model,editor,note,error,isDirty,()=>{original=editor.value;},refresh);
    current.append(controls,error);
  } else current.append(el('p',{className:'hint',text:'这份修订当前不可校订。已发布内容需要通过导入新修订更新。'}));
  const download=el('a',{href:path+'/file',text:'下载此修订原文件'});
  ctx.root.append(pageControls,el('div',{className:'two-col'},[source,current]),actions(download));
}

function reviewControls(ctx,model,editor,note,error,isDirty,markSaved,refresh) {
  const {path,page,pageNumber,data}=model;
  const explanation=()=>{
    if(note.value.trim().length<5) throw new Error('请填写至少 5 个字的操作说明，输入将保留。');
    return note.value.trim();
  };
  const save=button('保存校订',()=>busy(save,async()=>{
    await api(path+'/pages/'+pageNumber,{method:'PUT',body:{text:editor.value,expected_text_sha256:page.text_sha256,note:explanation()},signal:ctx.signal});
    markSaved(); ctx.notify('校订已保存，先前复核已撤销，需要重新复核。'); refresh();
  },error),true);
  const review=button('完成复核',()=>busy(review,async()=>{
    if(isDirty()) throw new Error('正文有未保存修改，请先保存校订。');
    await api(path+':review',{method:'POST',body:{note:explanation()},signal:ctx.signal});
    ctx.notify('复核已记录，资料尚未发布。'); refresh();
  },error),false,!ctx.canPublish);
  const publish=publishButton(ctx,model,isDirty,error);
  return actions(save,review,publish,el('p',{className:'hint',text:ctx.canPublish?'发布只在服务器复核状态有效时可用。':'当前角色可校订，需要发布复核员完成复核与发布。'}));
}

function publishButton(ctx,model,isDirty,error) {
  const key=requestKey(),{path,data}=model;
  const control=button('确认发布此修订',()=>busy(control,async()=>{
    if(isDirty()) throw new Error('正文有未保存修改，请先保存并重新复核。');
    if(!window.confirm(`确认发布 ${data.filename} v${data.number}？${data.current_revision?'这将替换当前公开版本，旧引用需要重新校验。':'这将成为此来源的首个公开版本。'}`)) return;
    const headers={'Idempotency-Key':key,...(data.current_revision?{'If-Match':'"'+data.current_revision+'"'}:{'If-None-Match':'*'})};
    await api(path+':publish',{method:'POST',headers,signal:ctx.signal});
    ctx.invalidateEvidence();
    ctx.notify('修订已完成发布。请重新取证并检查旧引用。'); ctx.go('review');
  },error),true,!ctx.canPublish || !data.reviewed);
  return control;
}
