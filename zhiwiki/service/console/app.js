/* Session shell and abortable routing; page modules own small task-specific views. */
import {api,PREFIX,restoreCSRF,setCSRF} from './api.js';
import {el,button,empty,feedback,showError,busy,roleLabels} from './ui.js';
import * as sources from './sources.js';
import * as tasks from './tasks.js';
import * as review from './review.js';
import * as evidence from './evidence.js';
import * as access from './access.js';
import * as operations from './operations.js';

const modules={documents:sources,tasks,review,evidence,access,operations};
let user=null,libraries=[],selected=null,limits={},controller=null,guard=null,lastHash='';
let evidenceState={};
const loginPanel=document.querySelector('#login-panel'),workbench=document.querySelector('#workbench');
const selector=document.querySelector('#knowledge-base'),loginError=document.querySelector('#login-error');

function showLogin(message='') {
  controller?.abort();guard=null;user=null;libraries=[];selected=null;evidenceState={};setCSRF('');
  document.querySelector('#view').replaceChildren();feedback('');
  document.querySelector('#login-form').reset();loginError.textContent=message;
  workbench.hidden=true;loginPanel.hidden=false;document.querySelector('#boot-status').hidden=true;
}
function navigate(route,values={}) {
  const parameters=new URLSearchParams();
  const data={kb:selected?.id,...values};
  for(const [key,value] of Object.entries(data)) if(value!==undefined && value!==null && value!=='') parameters.set(key,String(value));
  const hash='#'+route+(parameters.size?'?'+parameters:'');
  if(location.hash===hash) renderRoute();else location.hash=hash;
}
async function refreshLibraries(preferred,signal) {
  const result=await api(PREFIX+'/knowledge-bases',{signal});
  if(signal?.aborted) return;
  libraries=result.knowledge_bases;
  const next=libraries.find(item=>item.id===preferred) || libraries.find(item=>item.id===selected?.id) || libraries[0] || null;
  // Commit a library change only after the route's unsaved-content guard agrees.
  navigate('access',{kb:next?.id || ''});
}
function renderHeader() {
  selector.replaceChildren(...libraries.map(item=>el('option',{value:item.id,text:item.title})));
  if(!libraries.length) selector.append(el('option',{value:'',text:'暂无知识库'}));
  selector.disabled=!libraries.length;selector.value=selected?.id || '';
  document.querySelector('#identity').textContent=user.admin?'系统管理员':'受权团队成员';
  document.querySelector('#account-name').textContent=user.username;
  document.querySelector('#library-role').textContent=selected?roleLabels[selected.role]:'尚无授权';
  const editor=selected && selected.role!=='reader';
  document.querySelectorAll('[data-editor]').forEach(node=>{node.hidden=!editor;});
  document.querySelectorAll('[data-admin]').forEach(node=>{node.hidden=!user.admin;});
}
async function openWorkspace(identity) {
  user=identity;restoreCSRF();
  const [bases,capabilities]=await Promise.all([api(PREFIX+'/knowledge-bases'),api('/v1/capabilities')]);
  libraries=bases.knowledge_bases;limits=capabilities.limits;
  selected=libraries[0] || null;evidenceState={};
  loginPanel.hidden=true;workbench.hidden=false;document.querySelector('#boot-status').hidden=true;
  renderHeader();await renderRoute();
}

async function renderRoute() {
  if(!user) return;
  if(guard?.() && !window.confirm('有未保存正文或尚未保存的令牌，离开将清除本页内容。确认离开？')) {
    history.replaceState(null,'',lastHash || '#documents');renderHeader();return;
  }
  guard=null;controller?.abort();controller=new AbortController();
  const [name,search='']=location.hash.slice(1).split('?');
  const route=modules[name]?name:'documents',params=new URLSearchParams(search);
  const previous=selected?.id,requested=params.get('kb');
  if(requested) selected=libraries.find(item=>item.id===requested) || null;
  if(previous!==selected?.id) evidenceState={};
  renderHeader();lastHash=location.hash;
  const root=el('div'),frame=document.querySelector('#view');frame.replaceChildren(root);frame.setAttribute('aria-busy','true');
  document.querySelectorAll('nav a').forEach(link=>link.setAttribute('aria-current',link.dataset.view===route?'page':'false'));
  if(requested && !selected) {
    root.append(empty('无法访问这个知识库','权限可能已经撤销，请选择当前有权限的知识库。'),button('打开可用资料',()=>navigate('documents',{kb:libraries[0]?.id})));
    frame.setAttribute('aria-busy','false');return;
  }
  const signal=controller.signal;
  const ctx={root,route,params,user,kb:selected,limits,signal,evidence:evidenceState,
    canEdit:!!selected && selected.role!=='reader',canPublish:!!selected && ['publisher','admin'].includes(selected.role),
    setGuard:value=>{if(!signal.aborted)guard=value;},
    go:(destination,values)=>{if(!signal.aborted)navigate(destination,values);},
    notify:(message,error=false)=>{if(!signal.aborted)feedback(message,error);},
    invalidateEvidence:()=>{if(!signal.aborted)evidenceState.validation=null;},
    refreshLibraries:preferred=>signal.aborted?Promise.resolve():refreshLibraries(preferred,signal)};
  try {await modules[route].mount(ctx);}
  catch(error) {showError(root,error);}
  finally {if(!signal.aborted)frame.setAttribute('aria-busy','false');}
}

document.querySelector('#login-form').addEventListener('submit',event=>{
  event.preventDefault();loginError.textContent='';
  const form=event.target,control=form.querySelector('button');
  busy(control,async()=>{
    try {
      const result=await api('/v1/sessions',{method:'POST',body:{username:form.username.value,password:form.password.value},quiet401:true});
      setCSRF(result.csrf_token);form.password.value='';
      const identity=await api('/v1/me');await openWorkspace(identity);
    } catch(error) {
      form.password.value='';loginError.textContent=error.status===401?'用户名或密码不正确，或账号已经停用。':error.message;
    }
  });
});
document.querySelector('#logout').addEventListener('click',event=>busy(event.target,async()=>{
  if(guard?.() && !window.confirm('退出将清除未保存内容和令牌明文，确认退出？')) return;
  await api('/v1/sessions/current',{method:'DELETE'});showLogin('你已退出登录。');
}));
selector.addEventListener('change',()=>navigate('documents',{kb:selector.value}));
document.querySelector('nav').addEventListener('click',event=>{
  const link=event.target.closest('a[data-view]');
  if(link && !event.ctrlKey && !event.metaKey) {event.preventDefault();navigate(link.dataset.view);}
});
window.addEventListener('hashchange',()=>renderRoute());
window.addEventListener('session-expired',()=>showLogin('登录已失效，请重新登录。'));

async function boot() {
  try {const identity=await api('/v1/me',{quiet401:true});await openWorkspace(identity);}
  catch(error) {showLogin(error.status===401?'':error.message);}
}
boot();
