---
name: resume-apply
description: |
  国内 Agent / LLM 应用岗投递流水：维护试跑清单、开放题草稿、渠道笔记。用户确认每条；插件与提交在用户浏览器。
---

# 投递流水

维护清单与草稿。登录、装插件、点提交只在用户本机浏览器。

## 已锁

- 国内。岗位名：Agent / LLM Agent / 智能体，以及要写代码的 LLM 应用 / AI 应用 / 大模型应用。
- 城市：杭州；JD 写明可远程才加。
- 两份投递件、一张总表。秋招网申/测评截止优先，剩时间才点实习。
- 分类看**投递入口**：校招系统/测评/2027 届网申 → 秋招列 + 校招 PDF。实习僧/Boss/官网实习入口 → 实习列 + 实习 PDF。「实习+转正」若走实习投递，仍用实习 PDF。例外写在当次清单。
- 简历 PDF 项目 bullet 不改（素材已锁）。
- 仓在 `D:\38993\Documents\Resume`。不迁回 WSL。不加 remote、不 `git push`。

投递件见 [`resume/`](../../../resume/)。改 JSON / 重渲染走仓根 `AGENTS.md` 的渲染指针，不要在本文件复述命令。

## 清单

你维护；用户逐条确认（公司、标题、链接、列、哪份 PDF、项目链接）后再进队列。

字段：公司｜标题｜链接｜实习或秋招｜城市/远程｜投递件｜项目链接｜试用工具｜状态｜下一步

项目链接：`https://github.com/ARKL5/retail-bench` 、 `https://github.com/ARKL5/rag-backend`

当次草稿：[`.notes/trial-list-2026-09-18.md`](../../../.notes/trial-list-2026-09-18.md)

## 开放题

按 JD 起草，用户提交前必看。只写 [`.notes/oral-source-material.md`](../../../.notes/oral-source-material.md) 能撑住的句子。数字回指 artifact。口述用「评测仪器」，92/114 只描述该 artifact，不是 HEAD KPI。

PDF 里仍有、仓库撑不住、不要写进开放题：「分别验证 System Prompt 与 Tool Description」「预演在独立内存副本中校验」。

## 试跑

顺序：官方填表 2 家（首选牛客网申助手，只填结构化字段）→ 第三方填表 1 家对照（首选塔塔网申）→ Boss 代聊（主号每天个位数到十几；限流/验证码墙/投诉则停这一档）。

插件与渠道证据：[`.notes/internship-apply-plugins-cn.md`](../../../.notes/internship-apply-plugins-cn.md)、[`.notes/internship-batch-apply-cn.md`](../../../.notes/internship-batch-apply-cn.md)、[`.notes/internship-platform-ecosystem-cn.md`](../../../.notes/internship-platform-ecosystem-cn.md)

Boss 开聊可进队列：固定第一句 + 简历；HR 回了用户接手。可接受 Boss 丢号；秋招网申走主身份。招呼语（发出前看输入框是否截断）：

> 您好，浙江理工大学，常驻杭州，每周 5 天，随时到岗。独立做过零售客服 Agent：在 tau2-bench 上做确定性评测和优化，任务通过率80.7%（92/114），另有用户隔离的可靠 RAG 后端。期待沟通。

## 红线

正向：清单、草稿、开放题在本仓改；提交按钮由用户按。

禁止：收密码/cookie；交代投；写定制爬虫/选择器/绕过检测；编仓库没有的经历；自动回 HR 第二句；在用户已登录 Chrome 里代点提交或代装扩展；把代提交/代聊工具写成用法。
