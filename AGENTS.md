# Project

个人求职投递件与投递进度维护；不是招聘平台、不是业务后端。所有回复使用简体中文。命令用 PowerShell 7（`pwsh`）。Python 用项目 `.venv`。git 只在本机 commit。

## Required reading

**工程标准**（改代码/设计之前、审查时）：[`docs/agents/engineering-standards.md`](docs/agents/engineering-standards.md)

**领域词**（用词、分列、入口、停驻）：[`CONTEXT.md`](CONTEXT.md)

**决策**（改分列规则、本机代聊/代提交、Boss 筛选、对照页之前）：[`docs/adr/`](docs/adr/)

**投递件**（改 JSON、PDF、headline、实习/校招列之前）：[`resume/`](resume/)

**渲染**（改简历数据、重渲染、或声称投递件完成时）：[`.agents/skills/qiaomu-campus-resume/SKILL.md`](.agents/skills/qiaomu-campus-resume/SKILL.md)

**投递资源**（网申填表/真提交、Boss 代聊；唯一结论）：[`docs/apply-research.md`](docs/apply-research.md)

**投递流水**（本机跑资源、开放题）：[`.agents/skills/resume-apply/SKILL.md`](.agents/skills/resume-apply/SKILL.md)

**临时文件**（口述、项目底稿）：[`.notes/`](.notes/)

## Project constraints

- 秘密不进 git。经历与数字只写仓库已有证据。
- Boss 筛选、对照页、代聊只改仓外 `D:\38993\Documents\get_jobs`。
- 开聊须本人明确说。

## Verification

投递件：`pwsh -File scripts/verify.ps1`（两份 JSON、swiss）。声称渲染完成时再按渲染 skill 出 PDF。

改仓外对照页：在 `D:\38993\Documents\get_jobs\front` 跑 `npx next build`，再 `node scripts/copy-dist.mjs`。
