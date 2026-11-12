/* Real browser acceptance. Credentials arrive on stdin and are never logged. */
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
let config;
const redactions = new Set();
const checks=[];

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
}
async function importFile(page,text,update=false,source='policy') {
  await nav(page,'资料与版本','documents');
  if(update) await page.getByRole('row').filter({hasText:'policy.txt'}).getByRole('button',{name:'导入新版'}).click();
  else await page.getByRole('button',{name:'导入资料',exact:true}).click();
  await page.getByLabel('稳定来源键',{exact:true}).waitFor();
  if(!update) await page.getByLabel('稳定来源键',{exact:true}).fill(source);
  await page.getByLabel('选择资料文件',{exact:true}).setInputFiles({name:source+'.txt',mimeType:'text/plain',buffer:Buffer.from(text)});
  await page.getByRole('button',{name:'提交导入',exact:true}).click();
  await page.waitForFunction(()=>location.hash.startsWith('#tasks?')&&location.hash.includes('job='));
  await ready(page);
  if(!update) {
    // Refresh recovery is tested before taking v1 evidence. Evidence is deliberately
    // memory-only, so refreshing during v2 would discard the old browser snapshot.
    const url=page.url();await page.reload();
    await page.locator('#workbench').waitFor({state:'visible'});await ready(page);
    assert.equal(page.url(),url);
  }
  await page.getByRole('button',{name:'打开修订原文',exact:true}).click({timeout:45000});
  await page.getByLabel('校订或复核说明',{exact:true}).waitFor();await ready(page);
  checks.push(update?'真实 worker 处理更新修订':'真实文件导入、独立 worker 和任务刷新恢复');
}
async function publish(page) {
  await page.getByLabel('校订或复核说明',{exact:true}).fill('已核对虚构验收资料，确认本次适用范围。');
  await page.getByRole('button',{name:'完成复核',exact:true}).click();
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
  await capture(page,'02-conflict-preserves-input');
  await page.getByRole('button',{name:'重新读取本页',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('textarea[aria-label="当前校订正文"]')?.value.includes('另一窗口已核对'));
  await ready(page);
  await page.getByLabel('当前校订正文',{exact:true}).fill('售后申请需提交订单号、问题描述和商品照片。资料由客服复核后受理，此为虚构验收资料。');
  await page.getByLabel('校订或复核说明',{exact:true}).fill('按新版虚构政策核对，补齐材料要求。');
  await page.getByRole('button',{name:'保存校订',exact:true}).click();
  await page.getByText('校订已保存，先前复核已撤销，需要重新复核。',{exact:true}).waitFor();await ready(page);
  assert.equal(await page.getByRole('button',{name:'确认发布此修订',exact:true}).isDisabled(),true);
  checks.push('真实 412 冲突保留输入、重读比较和校订撤销复核');
}
async function staleEvidence(page) {
  await nav(page,'检索与取证','evidence');
  await page.getByRole('button',{name:'校验当前引用',exact:true}).click();
  await page.getByText('引用校验未通过。这些旧证据不能继续当作当前有效依据，请重新检索。',{exact:true}).waitFor();
  await capture(page,'03-stale-evidence');checks.push('新版发布后旧引用被服务端拒绝');
  await retrieve(page);
}
async function tokenLifecycle(page) {
  await nav(page,'账号与接入','access');
  await page.getByRole('button',{name:'创建只读令牌',exact:true}).click();
  const secret=page.getByLabel('新 Agent 令牌明文',{exact:true});await secret.waitFor();
  const token=await secret.inputValue();redactions.add(token);
  const data={query:'售后',knowledge_base_ids:['browser_kb']};
  const accepted=await page.request.post('/v1/workspaces/default/retrievals',{headers:{Authorization:'Bearer '+token,'Idempotency-Key':'browser-token-request'},data});
  assert.equal(accepted.status(),200);
  await page.getByRole('button',{name:'已保存并清除明文',exact:true}).click();
  await page.getByRole('button',{name:'撤销',exact:true}).click();
  await page.getByText('令牌已撤销。',{exact:true}).waitFor();await ready(page);
  const denied=await page.request.get('/v1/me',{headers:{Authorization:'Bearer '+token}});
  assert.equal(denied.status(),401);
  const storage=await page.evaluate(()=>[Object.keys(localStorage),Object.keys(sessionStorage)]);
  assert.deepEqual(storage,[[],[]]);checks.push('令牌生成、真实 Bearer 使用、清除明文与撤销生效；无持久浏览器存储');
}
async function readerAndMobile(page) {
  await nav(page,'运行与审计','operations');await capture(page,'04-live-operations');
  await page.getByRole('button',{name:'退出登录',exact:true}).click();
  await login(page,'workbench_reader',config.reader_password);
  assert.equal(await page.locator('nav [data-view="review"]').isVisible(),false);
  const rejected=await page.request.get('/v1/workspaces/default/jobs?knowledge_base_id=browser_kb');
  assert.equal(rejected.status(),403);
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
    const context=await browser.newContext({baseURL:config.base_url,viewport:{width:1440,height:1000}});
    const page=await context.newPage();page.setDefaultTimeout(20000);
    page.on('pageerror',error=>errors.push(error.message));page.on('dialog',dialog=>dialog.accept());
    await page.goto(config.base_url);await login(page,'workbench_admin',config.admin_password);
    await setupThroughUI(page);
    await importFile(page,'售后办理规则：申请售后需要提交订单号和问题描述。资料由客服核对后受理。此为虚构验收资料。');
    await publish(page);await nav(page,'资料与版本','documents');await capture(page,'01-published-source');
    await retrieve(page);
    await importFile(page,'售后办理规则：申请售后需要提交订单号、问题描述和商品照片。此为虚构验收资料。',true);
    await conflictAndCorrection(page);await publish(page);await staleEvidence(page);
    await tokenLifecycle(page);await readerAndMobile(page);
    assert.deepEqual(errors,[]);console.log(JSON.stringify({checks,uncaught_errors:errors,api:'real local service',worker:'real separate supervisor and parser processes'}));
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
