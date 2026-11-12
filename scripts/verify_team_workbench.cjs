/* Real browser acceptance. Credentials arrive on stdin and are never logged. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
let config;
const redactions = new Set();
const checks=[];
const chapters=[];
let recordingStart=0,recordingEnded=false,recordingEnd=0;

async function scene(page,title,description,hold=3300) {
  if(!config.record_video || recordingEnded) return;
  chapters.push({start_seconds:(Date.now()-recordingStart)/1000,title,description});
  // This annotation belongs to the recording, not to the product interface.
  await page.evaluate(({title,description})=>{
    let overlay=document.querySelector('#recording-caption');
    if(!overlay) {
      overlay=document.createElement('div');overlay.id='recording-caption';
      Object.assign(overlay.style,{position:'fixed',bottom:'0',left:'0',width:'100%',padding:'15px 28px',background:'#080e18',color:'#eef4fc',fontFamily:'Microsoft YaHei, sans-serif',fontSize:'22px',lineHeight:'1.5',zIndex:'99999',borderTop:'1px solid #79efd0',boxSizing:'border-box',pointerEvents:'none'});
      document.body.append(overlay);
    }
    overlay.textContent='操作演示 · '+title+'　｜　'+description;
  },{title,description});
  await page.waitForTimeout(hold);
}

async function readInput() {
  let data='';
  for await (const chunk of process.stdin) data+=chunk;
  return JSON.parse(data);
}
async function ready(page) {
  await page.locator('#view[aria-busy="false"]').waitFor({timeout:30000});
}
async function nav(page,name,route) {
  await page.locator('nav').getByRole('link',{name,exact:true}).click();
  await page.waitForFunction(value=>document.querySelector(`nav [data-view="${value}"]`)?.getAttribute('aria-current')==='page',route);
  await ready(page);
}
async function capture(page,name) {
  await page.locator('nav a[aria-current="page"]').focus();
  await page.screenshot({path:path.join(config.output,name+'.png'),fullPage:true});
}
async function login(page,username,password) {
  await page.locator('#login-panel').waitFor({state:'visible'});
  await page.locator('#login-form').getByLabel('用户名',{exact:true}).fill(username);
  await page.locator('#login-form').getByLabel('密码',{exact:true}).fill(password);
  await page.locator('#login-form').getByRole('button',{name:'登录',exact:true}).click();
  await page.locator('#workbench').waitFor({state:'visible'});await ready(page);
}
async function setupThroughUI(page) {
  await nav(page,'账号与接入','access');
  await scene(page,'建立团队工作区','创建知识库与用户，再按知识库分配访问角色。');
  const view=page.locator('#view');
  await view.getByLabel('知识库名称',{exact:true}).fill('售后知识库验收示例');
  await view.getByLabel('知识库 ID 可选',{exact:true}).fill('browser_kb');
  await view.getByRole('button',{name:'创建知识库',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#knowledge-base').value==='browser_kb');await ready(page);
  await view.getByLabel('用户名',{exact:true}).fill('workbench_reader');
  await view.getByLabel('初始密码 至少 12 字符',{exact:true}).fill(config.reader_password);
  await view.getByRole('button',{name:'创建账号',exact:true}).click();
  await view.getByRole('row').filter({hasText:'workbench_reader'}).first().waitFor();await ready(page);
  const row=view.getByRole('row').filter({hasText:'workbench_reader'});
  await row.getByRole('button',{name:'选择授权'}).click();
  await view.getByLabel('知识库角色',{exact:true}).selectOption('reader');
  await view.getByRole('button',{name:'保存成员角色'}).click();
  await page.waitForFunction(()=>[...document.querySelectorAll('tbody tr')].filter(row=>row.textContent.includes('workbench_reader')).length===2);
  await ready(page);checks.push('网页创建用户、知识库并授予 reader');
  await scene(page,'按知识库授权','只读、编辑与发布权限由服务器执行，页面显示实际角色。');
}
async function importFile(page,text,update=false,source='policy') {
  await nav(page,'资料与版本','documents');
  if(update) await page.getByRole('row').filter({hasText:'policy.txt'}).getByRole('button',{name:'导入新版'}).click();
  else await page.getByRole('button',{name:'导入资料',exact:true}).click();
  await page.getByLabel('稳定来源键',{exact:true}).waitFor();
  if(!update) await page.getByLabel('稳定来源键',{exact:true}).fill(source);
  await page.getByLabel('选择资料文件',{exact:true}).setInputFiles({name:source+'.txt',mimeType:'text/plain',buffer:Buffer.from(text)});
  await scene(page,update?'导入来源的新修订':'提交真实文件','稳定来源键关联资料；202 仅表示接收，处理和发布分开。');
  await page.getByRole('button',{name:'提交导入',exact:true}).click();
  await page.waitForFunction(()=>location.hash.startsWith('#tasks?')&&location.hash.includes('job='));
  await ready(page);
  await scene(page,'跟进持久任务','处理状态来自服务器，刷新后用同一个任务 ID 继续跟进。');
  if(!update) {
    // Refresh recovery is tested before taking v1 evidence. Evidence is deliberately
    // memory-only, so refreshing during v2 would discard the old browser snapshot.
    const url=page.url();await page.reload();
    await page.locator('#workbench').waitFor({state:'visible'});await ready(page);
    assert.equal(page.url(),url);
  }
  await page.getByRole('button',{name:'打开修订原文',exact:true}).click({timeout:45000});
  await page.getByLabel('校订或复核说明',{exact:true}).waitFor();await ready(page);
  await scene(page,'核对原始资料','原始抽取与校订正文并列；未审核的新稿不进入普通检索。');
  checks.push(update?'真实 worker 处理更新修订':'真实文件导入、独立 worker 和任务刷新恢复');
}
async function publish(page) {
  await page.getByLabel('校订或复核说明',{exact:true}).fill('已核对虚构验收资料，确认本次适用范围。');
  await page.getByRole('button',{name:'完成复核',exact:true}).click();
  await page.getByRole('button',{name:'确认发布此修订',exact:true}).waitFor();await ready(page);
  await scene(page,'明确复核并条件发布','复核后仍需确认发布；使用当前修订作为版本条件。');
  await page.getByRole('button',{name:'确认发布此修订',exact:true}).click();
  await page.waitForFunction(()=>location.hash.startsWith('#review')&&!location.hash.includes('book='));
  await ready(page);
}
async function retrieve(page) {
  await nav(page,'检索与取证','evidence');
  await page.getByLabel('检索问题',{exact:true}).fill('售后需要提交哪些材料');
  await page.getByRole('button',{name:'检索已发布原文',exact:true}).click();
  await page.getByRole('heading',{name:'证据 1',exact:true}).waitFor();
  await page.getByRole('button',{name:'回读这些原文',exact:true}).click();
  await page.getByText('已回读服务器保存的原文证据。',{exact:true}).waitFor();
  await page.getByRole('button',{name:'校验当前引用',exact:true}).click();
  await page.locator('.success-text').filter({hasText:'版本和内容通过'}).waitFor();
  await scene(page,'取得可核验的原文证据','实际检索、回读、校验；语义是否支持结论仍需人工核对。');
  checks.push('真实检索、原文回读与引用校验');
}
async function conflictAndCorrection(page) {
  const parameters=new URLSearchParams(new URL(page.url()).hash.split('?')[1]);
  const route=`/v1/workspaces/default/documents/${parameters.get('book')}/revisions/${parameters.get('revision')}/pages/1`;
  const current=await (await page.request.get(route)).json();
  const csrf=await page.evaluate(()=>decodeURIComponent(document.cookie.split('; ').find(value=>value.startsWith('zw_csrf='))?.slice(8)||''));
  const changed=await page.request.put(route,{headers:{'X-CSRF-Token':csrf},data:{text:current.text+' 另一窗口已核对。',expected_text_sha256:current.text_sha256,note:'另一窗口的并发校订说明'}});
  assert.equal(changed.status(),200);
  const draft='本地尚未保存的售后规则：请提交订单号、问题描述和商品照片。此为虚构验收资料。';
  await page.getByLabel('当前校订正文',{exact:true}).fill(draft);
  await page.getByLabel('校订或复核说明',{exact:true}).fill('本地编辑窗口的说明。');
  await page.getByRole('button',{name:'保存校订',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'版本已被其他操作更新'}).waitFor();
  assert.equal(await page.getByLabel('当前校订正文',{exact:true}).inputValue(),draft);
  const editorSize=await page.getByLabel('当前校订正文',{exact:true}).evaluate(element=>({width:element.clientWidth,parent:element.parentElement.clientWidth}));
  assert.ok(editorSize.width>=editorSize.parent*0.95,'Review editor must use the available column width');
  await scene(page,'并发冲突保留输入','另一窗口已经更新时拒绝旧写入，保留本地正文供比较。',4200);
  await capture(page,'02-conflict-preserves-input');
  await page.getByRole('button',{name:'重新读取本页',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('textarea[aria-label="当前校订正文"]')?.value.includes('另一窗口已核对'));
  await ready(page);
  await page.getByLabel('当前校订正文',{exact:true}).fill('售后申请需提交订单号、问题描述和商品照片。资料由客服复核后受理，此为虚构验收资料。');
  await page.getByLabel('校订或复核说明',{exact:true}).fill('按新版虚构政策核对，补齐材料要求。');
  await page.getByRole('button',{name:'保存校订',exact:true}).click();
  await page.getByText('校订已保存，先前复核已撤销，需要重新复核。',{exact:true}).waitFor();await ready(page);
  assert.equal(await page.getByRole('button',{name:'确认发布此修订',exact:true}).isDisabled(),true);
  await scene(page,'校订后重新复核','修改正文会撤销复核结果，不能直接沿用旧审批发布。');
  checks.push('真实 412 冲突保留输入、重读比较和校订撤销复核');
}
async function staleEvidence(page) {
  await nav(page,'检索与取证','evidence');
  await page.getByRole('button',{name:'校验当前引用',exact:true}).click();
  await page.getByText('引用校验未通过。这些旧证据不能继续当作当前有效依据，请重新检索。',{exact:true}).waitFor();
  await scene(page,'旧引用失效','新版发布后，服务端拒绝旧证据；使用者需要重新取证。',4200);
  await capture(page,'03-stale-evidence');checks.push('新版发布后旧引用被服务端拒绝');
  await retrieve(page);
}
async function tokenLifecycle(page) {
  await nav(page,'账号与接入','access');
  if(config.record_video) await page.evaluate(()=>{
    const observer=new MutationObserver(()=>{
      const input=document.querySelector('textarea[aria-label="新 Agent 令牌明文"]');
      if(input) {input.style.opacity='0';input.style.userSelect='none';}
    });
    observer.observe(document.body,{childList:true,subtree:true});
  });
  await page.getByRole('button',{name:'创建只读令牌',exact:true}).click();
  const secret=page.getByLabel('新 Agent 令牌明文',{exact:true});await secret.waitFor();
  const token=await secret.inputValue();redactions.add(token);
  if(config.record_video) await secret.scrollIntoViewIfNeeded();
  await scene(page,'生成受限 Agent 令牌','录屏已遮挡明文；令牌只允许授权知识库与指定只读能力。');
  const data={query:'售后',knowledge_base_ids:['browser_kb']};
  const accepted=await page.request.post('/v1/workspaces/default/retrievals',{headers:{Authorization:'Bearer '+token,'Idempotency-Key':'browser-token-request'},data});
  assert.equal(accepted.status(),200);
  await page.getByRole('button',{name:'已保存并清除明文',exact:true}).click();
  await page.getByRole('button',{name:'撤销',exact:true}).click();
  await page.getByText('令牌已撤销。',{exact:true}).waitFor();await ready(page);
  const denied=await page.request.get('/v1/me',{headers:{Authorization:'Bearer '+token}});
  assert.equal(denied.status(),401);
  await scene(page,'撤销立即生效','真实 Bearer 请求被拒绝；演示凭证为临时生成并已撤销。');
  const storage=await page.evaluate(()=>[Object.keys(localStorage),Object.keys(sessionStorage)]);
  assert.deepEqual(storage,[[],[]]);checks.push('令牌生成、真实 Bearer 使用、清除明文与撤销生效；无持久浏览器存储');
}
async function readerAndMobile(page) {
  await nav(page,'运行与审计','operations');await capture(page,'04-live-operations');
  await scene(page,'运行状态与审计','显示真实健康、worker 心跳和操作记录；生产验收仍需现场完成。');
  await page.getByRole('button',{name:'退出登录',exact:true}).click();
  await login(page,'workbench_reader',config.reader_password);
  assert.equal(await page.locator('nav [data-view="review"]').isVisible(),false);
  const rejected=await page.request.get('/v1/workspaces/default/jobs?knowledge_base_id=browser_kb');
  assert.equal(rejected.status(),403);
  await scene(page,'只读账号的边界','管理入口不展示，直接调用管理 API 也由服务器返回 403。');
  await scene(page,'可复核交付','PRD、代码、验证脚本与验收边界随仓库保存。',4200);
  if(config.record_video) {recordingEnd=(Date.now()-recordingStart)/1000;recordingEnded=true;}
  await page.setViewportSize({width:390,height:844});await retrieve(page);
  await capture(page,'05-mobile-reader');
  const width=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.ok(width.scroll<=width.viewport,JSON.stringify(width));
  checks.push('reader 无管理入口且服务端拒绝管理查询；390px 页面无横向溢出');
}
async function main() {
  config=await readInput();redactions.add(config.admin_password);redactions.add(config.reader_password);
  const {chromium}=require(process.argv[2] || 'playwright');
  const browser=await chromium.launch({headless:true,...(config.browser?{executablePath:config.browser}:{})});
  const errors=[];
  try {
    const context=await browser.newContext({baseURL:config.base_url,viewport:config.record_video?{width:1600,height:900}:{width:1440,height:1000},
      ...(config.record_video?{recordVideo:{dir:config.output,size:{width:1600,height:900}}}:{})});
    const page=await context.newPage();page.setDefaultTimeout(20000);
    recordingStart=Date.now();
    page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
    await page.goto(config.base_url);await login(page,'workbench_admin',config.admin_password);
    await scene(page,'知证团队知识工作台','真实本机 API 与独立 worker，使用虚构资料和临时账号。',4200);
    await setupThroughUI(page);
    await importFile(page,'售后办理规则：申请售后需要提交订单号和问题描述。资料由客服核对后受理。此为虚构验收资料。');
    await publish(page);await nav(page,'资料与版本','documents');await capture(page,'01-published-source');
    await retrieve(page);
    await importFile(page,'售后办理规则：申请售后需要提交订单号、问题描述和商品照片。此为虚构验收资料。',true);
    await conflictAndCorrection(page);await publish(page);await staleEvidence(page);
    await tokenLifecycle(page);await readerAndMobile(page);
    assert.deepEqual(errors,[]);
    const video=page.video(),wallTotal=(Date.now()-recordingStart)/1000;await context.close();
    const recording=video?{path:await video.path(),end_seconds:recordingEnd,wall_total_seconds:wallTotal,chapters}:null;
    console.log(JSON.stringify({checks,uncaught_errors:errors,api:'real local service',worker:'real separate supervisor and parser processes',video:recording}));
  } catch(error) {
    // Only labels and headings: never dump inputs, cookies or token text.
    const pages=browser.contexts().flatMap(context=>context.pages());
    if(pages[0]) fs.writeFileSync(path.join(config.output,'diagnostic.json'),JSON.stringify({labels:await pages[0].locator('#view label').allTextContents(),headings:await pages[0].locator('#view h1').allTextContents()},null,2));
    throw error;
  } finally {await browser.close();}
}
main().catch(error=>{
  let message=error.stack || String(error);
  for(const secret of redactions) if(secret)message=message.split(secret).join('[credential]');
  console.error(message);process.exitCode=1;
});
