/* Show measured service status, never infer deployment readiness from a badge. */
import {api,PREFIX,query} from './api.js';
import {el,button,heading,empty,actions,table,section,time,details} from './ui.js';

export async function mount(ctx) {
  ctx.root.append(heading('运行与审计','查看真实服务状态和操作记录。心跳不是容量证明，正式上线仍需要目标环境的备份、告警与恢复验收。'));
  if(!ctx.user.admin) {ctx.root.append(empty('需要系统管理员权限','知识库角色不等于全局系统管理员。'));return;}
  const [metrics,audit,health]=await Promise.all([
    api(PREFIX+'/metrics',{signal:ctx.signal}),
    api(query(PREFIX+'/audit-events',{after:ctx.params.get('audit_after') || 0,limit:20}),{signal:ctx.signal}),
    Promise.allSettled(['/health/live','/health/ready','/health/worker'].map(path=>api(path,{signal:ctx.signal})))
  ]);
  ctx.root.append(actions(button('刷新状态',()=>ctx.go('operations'))),table(['检查对象','服务返回','含义'],health.map((result,index)=>[
    ['API 存活','API 就绪','worker 心跳'][index],healthText(result),
    ['进程可响应存活检查','数据库、索引与可用磁盘检查','监督进程最近心跳，不保证解析容量'][index]
  ])));
  ctx.root.append(section('任务与资源',table(['项目','当前值'],[
    ['各状态任务数',JSON.stringify(metrics.jobs)],['进程内存',metrics.resources.rss_bytes===null?'当前平台无法取得':Math.round(metrics.resources.rss_bytes/1048576)+' MiB'],
    ['可用磁盘',Math.floor(metrics.resources.free_disk_bytes/1048576)+' MiB'],['最近 worker 心跳',time(metrics.worker_heartbeat_at)]
  ]),details('当前计数与指标',metrics)),section('上线仍需核实',el('p',{text:'TLS 与反向代理、进程自动重启、外部告警、备份定时与隔离副本、恢复演练、真实容量与试用反馈。此页面没有足够证据把这些项目标记为已验收。'}),
    el('p',{className:'hint',text:'备份恢复使用受控 CLI；参阅项目 docs/TEAM_SERVICE.md 和 docs/DEPLOYMENT_PREFLIGHT.md，不在网页提交磁盘路径或覆盖真实数据。'})));
  ctx.root.append(auditSection(ctx,audit.events));
}
function healthText(result) {
  if(result.status==='fulfilled') return result.value.status;
  return result.reason.status===503?'未就绪 / 不可用':'检查请求失败，需排查连接';
}
function auditSection(ctx,events) {
  const list=el('ul',{className:'audit-list'},events.map(item=>el('li',{},[
    el('strong',{text:item.action}),el('small',{text:time(item.at)+' · '+item.actor+' · '+item.resource}),details('操作附加信息',JSON.parse(item.metadata))
  ])));
  return section('关键操作审计',events.length?list:empty('当前页没有审计事件','可以返回起点，或完成一次导入与发布后刷新。'),
    actions(button('返回审计起点',()=>ctx.go('operations')),button('继续读取审计',()=>ctx.go('operations',{audit_after:events.at(-1)?.id}),false,events.length<20)));
}
