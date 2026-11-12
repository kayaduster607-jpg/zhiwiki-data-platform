# 团队工作台演示视频

[观看或下载 MP4](assets/zhizheng-workbench-demo.mp4) · [字幕文件](assets/zhizheng-workbench-demo.srt) · [视频校验与章节](assets/zhizheng-workbench-demo.json)

成片约 77 秒，1600 × 900，H.264，无音轨，画面内包含中文步骤说明。视频来自真实本机 API、独立 worker 和浏览器操作；没有使用 API 模拟响应或之前的教学原型。资料为虚构售后文本，账号密码临时生成。令牌明文在录制时完全遮挡，随后执行真实撤销并验证请求被拒绝。

## 主要内容

| 时间 | 操作 |
| --- | --- |
| 00:01 | 知证团队知识工作台 |
| 00:05 | 建立团队工作区 |
| 00:09 | 按知识库授权 |
| 00:13 | 提交真实文件 |
| 00:16 | 跟进持久任务 |
| 00:19 | 核对原始资料 |
| 00:23 | 明确复核并条件发布 |
| 00:27 | 取得可核验的原文证据 |
| 00:30 | 导入来源的新修订 |
| 00:34 | 跟进持久任务 |
| 00:37 | 核对原始资料 |
| 00:40 | 并发冲突保留输入 |
| 00:45 | 校订后重新复核 |
| 00:48 | 明确复核并条件发布 |
| 00:52 | 旧引用失效 |
| 00:56 | 取得可核验的原文证据 |
| 01:00 | 生成受限 Agent 令牌 |
| 01:03 | 撤销立即生效 |
| 01:07 | 运行状态与审计 |
| 01:10 | 只读账号的边界 |
| 01:14 | 可复核交付 |

录制后还运行了手机视口检查及隔离备份恢复，这两项在验证脚本和报告中保留，成片聚焦桌面操作。画面中的心跳、资料和审计是真实本机状态，不表示已有生产客户、容量或 SLA。

## 复现录制

准备项目测试依赖、Node、Playwright、可运行的 Chrome，以及 Playwright 配套的 FFmpeg。导出 MP4 需要另一个支持 libx264 的 FFmpeg；这些是开发验证工具，不是启动团队服务的依赖。视频录制方式参考 [Playwright 官方说明](https://playwright.dev/docs/videos)。

```powershell
python -B scripts/verify_team_workbench.py --record-video --output reports/local-demo --node PATH_TO_NODE --playwright-module PATH_TO_PLAYWRIGHT --browser PATH_TO_CHROME
python -B scripts/export_team_demo.py --report reports/local-demo/browser-verification.json --ffmpeg PATH_TO_FFMPEG --output docs/assets
```

将 PATH 参数替换为本机工具路径。第一步只创建全新的隔离目录，启动回环 API 和独立 worker，凭证通过进程内存传递；不会读取项目 .env 或复用真实业务数据。第二步输出 MP4、SRT 和无凭证的章节校验摘要，裁去后续手机检查片段，并完整解码输出视频检查所有帧。

原始录制、数据库、运行配置和临时工具不随视频提交。源代码保留可复现的录制与导出逻辑；正式部署门禁见 [交付验收](TEAM_WORKBENCH_ACCEPTANCE.md)。
