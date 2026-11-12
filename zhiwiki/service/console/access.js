/* Accounts, grants and scoped Agent credentials; raw tokens are shown once. */
import {api,PREFIX,query} from './api.js';
import {el,button,field,heading,empty,actions,table,section,time,busy,roleLabels} from './ui.js';

export async function mount(ctx) {
  ctx.root.append(heading('账号与接入','管理知识库访问与本人 Agent 令牌。令牌范围受到账号当前权限限制，撤权后不能继续使用旧授权。'));
  const tokenSection=section('本人 Agent 令牌');ctx.root.append(tokenSection);
  await tokens(ctx,tokenSection);
  if(ctx.user.admin) await administration(ctx);
  else ctx.root.append(section('团队授权',el('p',{className:'muted',text:'账号与知识库授权由系统管理员管理。当前页面仅管理你本人的只读 Agent 令牌。'})));
}

function listPager(ctx,key,next) {
  const parameters=Object.fromEntries(ctx.params);delete parameters.kb;
  return actions(button('返回第一页',()=>ctx.go('access',{...parameters,[key]:''}),false,!ctx.params.get(key)),
    button('下一页',()=>ctx.go('access',{...parameters,[key]:next}),false,!next));
}
async function tokens(ctx,root) {
  const listing=el('div'),secret=el('div',{className:'secret-result'});
  let issued=null;
  ctx.setGuard(()=>!!issued?.value);
  if(ctx.kb) root.append(tokenForm(ctx,secret,async()=>load('')));
  else root.append(el('p',{className:'hint',text:'取得知识库授权后才能创建有范围限制的 Agent 令牌。'}));
  root.append(secret,listing);
  async function load(cursor) {
    const data=await api(query('/v1/tokens',{cursor,limit:20}),{signal:ctx.signal});
    listing.replaceChildren();
    if(!data.tokens.length) {listing.append(empty('没有已发出的 Agent 令牌','令牌创建后，只在当次结果展示明文。'));return;}
    listing.append(table(['令牌标识','范围','状态与到期','操作'],data.tokens.map(item=>[
      el('code',{text:item.token_id.slice(0,14)+'…'}),el('div',{},[item.scopes.join('、'),el('small',{text:item.knowledge_base_ids.join('、')})]),
      `${item.revoked?'已撤销':item.expires_at*1000<Date.now()?'已到期':'有效'} · ${time(item.expires_at)}`,
      revokeToken(ctx,item,()=>load(cursor))
    ])),listPager(ctx,'token_cursor',data.next_cursor));
  }
  function showToken(value) {
    issued=el('textarea',{value,readOnly:true,'aria-label':'新 Agent 令牌明文',rows:3});
    const clear=()=>{issued.value='';secret.replaceChildren();issued=null;};
    secret.replaceChildren(el('h3',{text:'请立即保存这个新令牌'}),el('p',{className:'warning',text:'离开页面后不会再次显示明文。不要把它写进仓库、发给模型或放到公开网页。'}),issued,
      actions(button('复制令牌',async()=>{
        try {await navigator.clipboard.writeText(issued.value);ctx.notify('令牌已复制，请安全保存。');}
        catch {ctx.notify('自动复制不可用，请手动复制。',true);}
      }),button('已保存并清除明文',clear)));
  }
  root.addEventListener('token-issued',event=>showToken(event.detail),{signal:ctx.signal});
  ctx.signal.addEventListener('abort',()=>{if(issued)issued.value='';},{once:true});
  await load(ctx.params.get('token_cursor'));
}

function tokenForm(ctx,secret,reload) {
  const form=el('form',{className:'form-stack'}),error=el('div',{role:'alert'});
  const scopes=['retrieve','read','validate','download'].map(value=>({value,input:el('input',{type:'checkbox',checked:value!=='download'})}));
  const ttl=el('select',{'aria-label':'令牌有效期'},[el('option',{value:3600,text:'1 小时'}),el('option',{value:86400,text:'1 天'}),el('option',{value:604800,text:'7 天'})]);
  const submit=el('button',{type:'submit',text:'创建只读令牌',className:'primary'});
  form.append(el('p',{className:'hint',text:'目标知识库：'+ctx.kb.title}),...scopes.map(item=>el('label',{className:'check-row'},[item.input,item.value])),field('有效期',ttl),submit,error);
  form.addEventListener('submit',event=>{
    event.preventDefault();error.replaceChildren();
    busy(submit,async()=>{
      if(secret.querySelector('textarea')?.value && !window.confirm('当前令牌只显示一次，确认已经保存并创建另一个？')) return;
      const selected=scopes.filter(item=>item.input.checked).map(item=>item.value);
      if(!selected.length) throw new Error('至少选择一种只读能力。');
      const result=await api('/v1/tokens',{method:'POST',body:{knowledge_base_ids:[ctx.kb.id],scopes:selected,expires_in:Number(ttl.value)},signal:ctx.signal});
      form.parentElement.dispatchEvent(new CustomEvent('token-issued',{detail:result.token}));
      await reload();
    },error);
  });
  return form;
}
function revokeToken(ctx,item,reload) {
  const control=button('撤销',()=>busy(control,async()=>{
    if(!window.confirm('撤销后使用此令牌的 Agent 请求将被拒绝，确认撤销？')) return;
    await api('/v1/tokens/'+encodeURIComponent(item.token_id),{method:'DELETE',signal:ctx.signal});
    ctx.notify('令牌已撤销。');await reload();
  }),false,item.revoked);
  return control;
}

async function administration(ctx) {
  const users=await api(query('/v1/users',{cursor:ctx.params.get('user_cursor'),limit:20}),{signal:ctx.signal});
  const root=section('团队管理');ctx.root.append(root);
  root.append(el('div',{className:'two-col'},[accountForm(ctx),libraryForm(ctx)]));
  const grantInput=el('input',{required:true,placeholder:'从下方选择用户，或粘贴用户 ID','aria-label':'授权用户 ID'});
  if(ctx.kb) root.append(section('当前知识库成员',grantForm(ctx,grantInput)));
  root.append(section('账号目录',table(['用户名','身份与状态','操作'],users.users.map(item=>[
    el('div',{},[el('strong',{text:item.username}),el('small',{text:item.id})]),`${item.admin?'系统管理员':'普通账号'} · ${item.disabled?'已停用':'启用'}`,
    el('div',{className:'cell-actions'},[
      ctx.kb?button('选择授权',()=>{grantInput.value=item.id;grantInput.focus();}):null,
      disableUser(ctx,item)
    ])
  ])),listPager(ctx,'user_cursor',users.next_cursor)));
  if(ctx.kb) await members(ctx,root);
}

function accountForm(ctx) {
  const name=el('input',{required:true,minLength:2,maxLength:64,pattern:'[A-Za-z0-9_.\\-]{2,64}',autocomplete:'off'});
  const password=el('input',{type:'password',required:true,minLength:12,maxLength:1024,autocomplete:'new-password'});
  const admin=el('input',{type:'checkbox'}),form=el('form',{className:'form-stack'}),error=el('div',{role:'alert'});
  const submit=el('button',{type:'submit',text:'创建账号'});
  form.append(el('h3',{text:'创建账号'}),field('用户名',name),field('初始密码 至少 12 字符',password),el('label',{className:'check-row'},[admin,'全局系统管理员']),submit,error);
  form.addEventListener('submit',event=>{
    event.preventDefault();error.replaceChildren();
    busy(submit,async()=>{
      if(admin.checked && !window.confirm('此账号将获得全局管理权限，确认创建？')) return;
      try {
        await api('/v1/users',{method:'POST',body:{username:name.value,password:password.value,admin:admin.checked},signal:ctx.signal});
        ctx.notify('账号已创建，请在账号目录选择并设置知识库授权。');ctx.go('access');
      } finally {password.value='';}
    },error);
  });
  return form;
}
function libraryForm(ctx) {
  const title=el('input',{required:true,maxLength:200}),id=el('input',{pattern:'[A-Za-z0-9_\\-]{2,100}',maxLength:100,placeholder:'留空自动生成'});
  const form=el('form',{className:'form-stack'}),error=el('div',{role:'alert'}),submit=el('button',{type:'submit',text:'创建知识库'});
  form.append(el('h3',{text:'创建知识库'}),field('知识库名称',title),field('知识库 ID 可选',id),submit,error);
  form.addEventListener('submit',event=>{
    event.preventDefault();error.replaceChildren();
    busy(submit,async()=>{
      const result=await api(PREFIX+'/knowledge-bases',{method:'POST',body:{title:title.value,...(id.value?{id:id.value}:{})},signal:ctx.signal});
      ctx.notify('知识库已创建，请为资料维护者设置角色。');await ctx.refreshLibraries(result.knowledge_base_id);
    },error);
  });
  return form;
}
function grantForm(ctx,user) {
  const role=el('select',{},Object.entries(roleLabels).map(([value,text])=>el('option',{value,text})));
  const form=el('form',{className:'form-stack'}),error=el('div',{role:'alert'}),submit=el('button',{type:'submit',text:'保存成员角色'});
  form.append(field('用户 ID',user),field('知识库角色',role),submit,error);
  form.addEventListener('submit',event=>{
    event.preventDefault();error.replaceChildren();
    busy(submit,async()=>{
      await api(`${PREFIX}/knowledge-bases/${encodeURIComponent(ctx.kb.id)}/members/${encodeURIComponent(user.value)}`,{method:'PUT',body:{role:role.value},signal:ctx.signal});
      ctx.notify('知识库角色已更新。');ctx.go('access');
    },error);
  });
  return form;
}
function disableUser(ctx,item) {
  const control=button('停用',()=>busy(control,async()=>{
    if(!window.confirm('停用 '+item.username+' 后，其会话和令牌将无法继续访问，确认停用？')) return;
    await api(`${PREFIX}/users/${encodeURIComponent(item.id)}:disable`,{method:'POST',signal:ctx.signal});ctx.notify('账号已停用。');ctx.go('access');
  }),false,item.disabled || item.id===ctx.user.id);
  return control;
}
async function members(ctx,root) {
  const data=await api(query(`${PREFIX}/knowledge-bases/${encodeURIComponent(ctx.kb.id)}/members`,{cursor:ctx.params.get('member_cursor'),limit:20}),{signal:ctx.signal});
  const rows=data.members.map(item=>{
    const remove=button('撤销访问',()=>busy(remove,async()=>{
      if(!window.confirm('撤销 '+item.username+' 对当前知识库的授权？')) return;
      await api(`${PREFIX}/knowledge-bases/${encodeURIComponent(ctx.kb.id)}/members/${encodeURIComponent(item.id)}`,{method:'DELETE',signal:ctx.signal});
      ctx.notify('成员授权已撤销。');ctx.go('access');
    }));
    return [item.username,roleLabels[item.role],item.disabled?'已停用':'启用',remove];
  });
  root.append(section('成员授权记录',rows.length?table(['用户','知识库角色','账号状态','操作'],rows):empty('尚未分配成员','全局管理员仍可管理此知识库，普通用户需要显式授权。'),listPager(ctx,'member_cursor',data.next_cursor)));
}
