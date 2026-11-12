/* Source receipts remain in memory only and are cleared on logout/library change. */
import {api,PREFIX,requestKey} from './api.js';
import {el,button,field,heading,empty,actions,busy,metadata,details,time} from './ui.js';

export async function mount(ctx) {
  ctx.root.append(heading('检索与取证','只检索当前有权限的已发布资料。回到原文，检查引用版本；语义是否支持结论仍需另行核对。'));
  if(!ctx.kb) {ctx.root.append(empty('还没有可检索的知识库','请联系管理员确认资料和授权。'));return;}
  const state=ctx.evidence;
  const input=el('textarea',{required:true,maxLength:4000,rows:3,value:state.question || '',placeholder:'输入需要查证的问题','aria-label':'检索问题'});
  const form=el('form',{className:'form-stack'}),error=el('div',{role:'alert'}),results=el('div');
  const submit=el('button',{type:'submit',className:'primary',text:'检索已发布原文'});
  form.append(field('检索问题',input),submit,error); ctx.root.append(form,results);
  let pendingQuery='',key='';
  form.addEventListener('submit',event=>{
    event.preventDefault(); error.replaceChildren();
    busy(submit,async()=>{
      const question=input.value.trim(); if(!question) throw new Error('请输入检索问题。');
      if(question!==pendingQuery) {pendingQuery=question;key=requestKey();}
      state.question=question;state.receipt=null;state.validation=null;results.replaceChildren();
      const data=await api(PREFIX+'/retrievals',{method:'POST',body:{query:question,knowledge_base_ids:[ctx.kb.id]},headers:{'Idempotency-Key':key},signal:ctx.signal});
      state.receipt=data;key=requestKey();paint(ctx,results,error);ctx.notify('已取得服务端证据快照。');
    },error);
  });
  paint(ctx,results,error);
}

function paint(ctx,root,error) {
  root.replaceChildren();
  const state=ctx.evidence,receipt=state.receipt;
  if(!receipt) return;
  if(!receipt.evidence.length) {root.append(empty('当前没有命中证据','请调整问题，或确认资料已经复核发布。'));return;}
  const read=button('回读这些原文',()=>busy(read,async()=>{
    const data=await api(PREFIX+'/evidence:read',{method:'POST',headers:{'Idempotency-Key':requestKey()},
      body:{retrieval_ids:[receipt.retrieval_id],evidence_ids:receipt.evidence.map(item=>item.evidence_id)},signal:ctx.signal});
    state.receipt=data;state.validation=null;paint(ctx,root,error);ctx.notify('已回读服务器保存的原文证据。');
  },error));
  const validate=button('校验当前引用',()=>busy(validate,async()=>{
    try {
      const result=await api(PREFIX+'/citations:validate',{method:'POST',body:{retrieval_ids:[receipt.retrieval_id],
        citations:receipt.evidence.map(item=>({evidence_id:item.evidence_id,text_sha256:item.text_sha256}))},signal:ctx.signal});
      state.validation={valid:true,semantic:result.semantic_support,checkedAt:result.checked_at};paint(ctx,root,error);
    } catch(problem) {
      if(problem.name!=='AbortError') {state.validation={valid:false};paint(ctx,root,error);}
      throw problem;
    }
  },error),true);
  root.append(actions(read,validate),validationNotice(state.validation),el('p',{className:'hint',text:'取证凭据有效至北京时间 '+time(receipt.receipt_expires_at)+'。刷新页面后需重新检索；当前快照没有写入浏览器持久存储。'}));
  receipt.evidence.forEach((item,index)=>root.append(evidenceItem(item,index)));
}

function validationNotice(validation) {
  if(!validation) return el('p',{className:'hint',text:'这些是服务器返回的证据快照，尚未执行本次引用校验。'});
  if(!validation.valid) return el('p',{className:'error-text',text:'引用校验未通过。这些旧证据不能继续当作当前有效依据，请重新检索。'});
  return el('p',{className:'success-text',text:'上次校验（北京时间 '+time(validation.checkedAt)+'）版本和内容通过。再次使用前应重新校验。语义支持尚未核验，请核对原文是否支持结论。'});
}
function evidenceItem(item,index) {
  return el('article',{className:'section'},[
    el('h2',{text:'证据 '+(index+1)}),el('div',{className:'two-col'},[
      el('div',{className:'prose',text:item.text}),el('div',{className:'paper'},[
        metadata({'资料 ID':item.document_id,'来源修订':item.revision_id,'证据 ID':item.evidence_id,'质量提示':item.quality_flags.map(value=>value==='manually_corrected'?'已人工校订':value).join('、') || '无附加提示'}),
        details('原文定位与内容哈希',{locator:item.locator,text_sha256:item.text_sha256})
      ])
    ])
  ]);
}
