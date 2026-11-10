# 目标—任务树

本文件为新master范围投影，完整历史树与同记录原表在本地保全。挂树不授权；新增任务沿用AGENTS，并同步原表同记录、回读核验。保留父任务和依赖，不因源码退役改写历史验收。

- G-DELIVERY：已验收行情总览与前后端分离交付；原验收保持。
  - MASTER-BASE：保全历史和未验收改动 → 清理旧实现 → 回归 → 本地基线 → 一次限项代码独审；依赖 G-DELIVERY、BSE、DAILY-LIVE；推送和删枝单独确认。
  - OVERVIEW-PERF：加载性能｜执行：原只读预览已关闭，其后随STORAGE-BASELINE完成只读日常交付｜技术：代码完成（L2独审通过）｜用户验收：2026-11-10通过，本人确认加载时间符合预期｜前置BSE与原独审轮次/失败记录保持，1秒为后续优化目标，采集/定时保持关闭；本次获准与ETF、存储一起本地提交合并master，暂不推送。[任务书](tasks/TASK-20261106-overview-load-performance.md)；原表reczz28WIyuGvryK本次验收rev345已回读，父依赖保持。
- ETF-FLOW：首只ETF大资金动向｜当前目标，复用工2｜前置：master基线及ETF保全成果｜技术完成（独审通过）｜2026-11-10用户验收通过｜含单只近5/20日累计、事件/折算标记及证据；本次获准与存储、加载一起本地提交合并master，暂不推送。[任务书](tasks/TASK-20261107-etf-flow-integration.md)；原表reczz28VwbPFdeMp本次验收与Git授权rev359已回读。
- STOCK-QUERY：标的查询，未完成／未验收；本地保全，未纳入master。

- STORAGE-BASELINE：挂G-DELIVERY→OVERVIEW-PERF，复用切片2.1／工2；前置规则、基准、盘点与方案保持｜执行：方案独审→备份→导入→56版本核对→恢复→代码独审→只读日常切换→9项旧读取退役已完成｜技术完成（独审通过）｜用户验收：2026-11-10通过，本人确认加载时间符合预期｜本人限项追加P5/P6复查通过；本轮首页≤2.1秒、日增量≤90秒，原失败及后续目标保留；旧数据/备份保留、不加依赖、不扩功能、不恢复采集/定时。[任务书及报告](tasks/TASK-20261107-storage-read-baseline.md)；原表reczz28WIyuGvryK原技术收尾rev344已回读；本次验收rev345已回读，原记录/父依赖保持。

本轮Git交付：2026-11-10：本人确认ETF验收通过，并授权ETF大资金动向、存储迁移和加载优化一起提交Git并合并master，暂不推送。沿用ETF-FLOW／工2及STORAGE-BASELINE、OVERVIEW-PERF／2.1；既有独审及前置保持，不新增功能、采集或定时权限。原表同记录验收与Git授权rev359已回读。
