# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

内部资料编辑者、发布复核者、知识使用者、系统管理员及取得受限证据的 Agent。用户授权本轮按团队真实交付目标改造现有知证，并先写 PRD。真实试点人数与业务制度待确认。

## Product Purpose

把资料接入、持久任务、人工校订、复核发布与原文取证组织成可操作、可恢复的团队工作流。

## Capabilities and Constraints

保留现有 FastAPI、SQLite WAL、独立 worker 和原生网页。团队 /v1 与本地 /api 分离；本地工作台不开放到团队服务。现有产品不是结构化数仓，不承诺多机高可用，不新增问答生成模型。

## Evidence on Hand

基线提交 bc912b69f48b6827a1522302dcaf765e1c5ec63a、现有测试与部署说明。独立教学原型已供用户查看，延续其任务结构和现有深色薄荷色。生产容量、真实客户及现场验收仍未确认。

## Product Principles

- 用户完成完整任务，不依赖手工 HTTP 调用。
- 当前公开版本不因新稿处理失败而中断。
- 权限、复核和版本条件由服务器执行。
- 失败可恢复，证据可追溯，未验证状态明确显示。

## Scope

本版需求与验收编号由 docs/PRD_TEAM_WORKBENCH_V1.md 定义；只用隔离数据验证，不读取任何 .env 文件。
