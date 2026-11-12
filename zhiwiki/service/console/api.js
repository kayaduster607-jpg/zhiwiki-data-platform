/* One same-origin client. Credentials stay in HttpOnly cookies, never storage. */
let csrf = '';
export const PREFIX = '/v1/workspaces/default';

const messages = {
  UNAUTHENTICATED:'登录已失效，请重新登录。',PERMISSION_DENIED:'当前身份没有执行此操作的权限。',
  CSRF_FAILED:'会话校验失败，请刷新并重新登录后操作。',INVALID_CURSOR:'列表条件或权限已变化，请返回第一页刷新。',
  PRECONDITION_FAILED:'版本已被其他操作更新。你的输入已保留，请重新读取并比较。',
  KNOWLEDGE_CHANGED:'知识来源或授权已变化，请重新读取。',REVIEW_REQUIRED:'当前修订需要重新复核后才能发布。',
  REVISION_NOT_READY:'修订尚未就绪，或已经发布。请刷新查看。',JOB_NOT_RETRYABLE:'这个任务当前不能重试，或已达到尝试次数上限。',
  SOURCE_EXISTS:'来源键已经存在。请到资料目录选择该来源进行更新。',
  PAYLOAD_TOO_LARGE:'文件或请求超出允许大小，请调整后重试。',UNSUPPORTED_FILE:'文件类型不受支持。',
  UPLOAD_QUEUE_FULL:'导入队列已满，请稍后再试。',IMPORT_QUEUE_FULL:'导入队列已满，请稍后再试。',
  CANNOT_DISABLE_SELF:'不能停用当前自己的管理账户。',RESOURCE_NOT_FOUND:'记录不存在或已不可访问。',
  RECEIPT_EXPIRED:'取证凭据已过期，请重新检索。',CITATION_INVALID:'引用校验未通过，请重新取证。',
  VALIDATION_ERROR:'提交内容不符合接口要求，请检查必填项与长度。'
};

export class ApiError extends Error {
  constructor(code,status,requestId='') {
    super(messages[code] || `请求未完成（${code}）。请刷新状态后判断是否重试。`);
    this.code=code; this.status=status; this.requestId=requestId;
  }
}
export function setCSRF(value) { csrf=value || ''; }
export function restoreCSRF() {
  const cookie=document.cookie.split('; ').find(value=>value.startsWith('zw_csrf='));
  setCSRF(cookie ? decodeURIComponent(cookie.slice(8)) : '');
}
export function requestKey() {
  return 'web-'+(crypto.randomUUID ? crypto.randomUUID() : [...crypto.getRandomValues(new Uint32Array(4))].join('-'));
}
export async function api(path,{method='GET',body,headers={},signal,quiet401=false}={}) {
  const outgoing={...headers};
  if(method!=='GET' && method!=='HEAD') outgoing['X-CSRF-Token']=csrf;
  const isFile=body instanceof FormData;
  if(body!==undefined && !isFile) outgoing['Content-Type']='application/json';
  let response;
  try {
    response=await fetch(path,{method,headers:outgoing,body:body===undefined?undefined:isFile?body:JSON.stringify(body),credentials:'same-origin',cache:'no-store',signal});
  } catch(error) {
    if(error.name==='AbortError') throw error;
    throw new Error('网络请求未得到确认。请检查连接；写入可能已经接收，先查看任务或状态再重试。');
  }
  const data=await response.json().catch(()=>({error:{code:'INVALID_RESPONSE'}}));
  if(!response.ok) {
    if(response.status===401 && !quiet401) window.dispatchEvent(new CustomEvent('session-expired'));
    throw new ApiError(data.error?.code || 'REQUEST_FAILED',response.status,data.request_id || '');
  }
  return data;
}
export function query(path,values) {
  const parameters=new URLSearchParams();
  for(const [key,value] of Object.entries(values)) if(value!==null && value!==undefined && value!=='') parameters.set(key,String(value));
  return path+'?'+parameters;
}
