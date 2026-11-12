/* Safe DOM primitives: source text is never interpreted as HTML. */
export function el(tag,properties={},children=[]) {
  const node=document.createElement(tag);
  for(const [key,value] of Object.entries(properties)) {
    if(value===null || value===undefined) continue;
    if(key==='text') node.textContent=String(value);
    else if(key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(),value);
    else if(key in node) node[key]=value;
    else node.setAttribute(key,String(value));
  }
  for(const child of Array.isArray(children)?children:[children]) if(child!==null && child!==undefined) node.append(child instanceof Node?child:document.createTextNode(String(child)));
  return node;
}
export function button(label,action,primary=false,disabled=false) {
  return el('button',{type:'button',text:label,className:primary?'primary':'',disabled,onClick:action});
}
export function field(label,input) {
  // Explicit names keep select options from becoming part of the field label.
  input.setAttribute('aria-label',label);
  return el('label',{},[label,input]);
}
export function heading(title,description) { return el('div',{className:'page-heading'},el('div',{},[el('h1',{text:title}),el('p',{className:'intro',text:description})])); }
export function empty(title,description) { return el('div',{className:'empty'},[el('h2',{text:title}),el('p',{text:description})]); }
export function actions(...children) { return el('div',{className:'actions'},children); }
export function section(title,...children) { return el('section',{className:'section'},[el('h2',{text:title}),...children]); }
export function feedback(text,error=false) {
  const node=document.querySelector('#feedback');
  node.textContent=text; node.classList.toggle('is-error',error); node.hidden=!text;
}
export function showError(parent,error) {
  if(error.name==='AbortError') return;
  feedback('');
  parent.replaceChildren(el('div',{className:'error-panel',role:parent.getAttribute('role')==='alert'?null:'alert'},[
    el('span',{text:error.message}),error.requestId?el('small',{text:'请求编号 '+error.requestId}):null]));
}
export async function busy(node,action,errorTarget) {
  const label=node.textContent; node.disabled=true; node.textContent='处理中…';
  try { await action(); }
  catch(error) { if(error.name!=='AbortError') errorTarget?showError(errorTarget,error):feedback(error.message,true); }
  finally { node.disabled=false; node.textContent=label; }
}
export function table(headers,rows) {
  return el('div',{className:'table-wrap'},el('table',{},[
    el('thead',{},el('tr',{},headers.map(text=>el('th',{scope:'col',text})))),
    el('tbody',{},rows.map(row=>el('tr',{},row.map(cell=>el('td',{},cell??'—')))))
  ]));
}
export function pager(ctx,next,parameters={}) {
  return el('div',{className:'pagination'},[
    button('返回第一页',()=>ctx.go(ctx.route,{...parameters,cursor:''}),false,!ctx.params.get('cursor')),
    button('下一页',()=>ctx.go(ctx.route,{...parameters,cursor:next}),false,!next)
  ]);
}
export function time(value) {
  if(value===null || value===undefined || value==='') return '—';
  const milliseconds=Number.isFinite(Number(value))?Number(value)*1000:Date.parse(value);
  if(!Number.isFinite(milliseconds)) return '—';
  return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',dateStyle:'short',timeStyle:'medium'}).format(new Date(milliseconds));
}
export const stateLabels={queued:'排队中',parsing:'解析中',cancel_requested:'取消请求中',cancelled:'已取消',failed:'失败',needs_review:'待人工复核',awaiting_publish:'待发布',publishing:'发布中',ready:'已完成发布',staging:'处理中',published:'已发布',archived:'历史版本'};
export const roleLabels={reader:'只读使用者',editor:'资料编辑员',publisher:'发布复核员',admin:'管理员'};
export function badge(status) {
  const kind=['failed','cancelled'].includes(status)?'error':['needs_review','awaiting_publish','parsing','queued','cancel_requested','publishing','staging'].includes(status)?'warn':'';
  return el('span',{className:'status '+kind,text:stateLabels[status] || status});
}
export function metadata(values) {
  return el('dl',{},Object.entries(values).flatMap(([key,value])=>[el('dt',{text:key}),el('dd',{text:value??'—'})]));
}
export function details(title,value) {
  return el('details',{className:'details'},[el('summary',{text:title}),el('pre',{text:JSON.stringify(value,null,2)})]);
}
export function dirtyGuard(signal,isDirty) {
  const guard=event=>{if(isDirty()){event.preventDefault();event.returnValue='';}};
  window.addEventListener('beforeunload',guard,{signal});
}
