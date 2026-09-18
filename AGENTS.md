# Project

个人求职投递件与投递进度维护；不是业务后端。人读入口：[`README.md`](README.md)。所有回复使用简体中文。

## Required reading

**投递件**（改 JSON、PDF、headline、实习/校招列之前）：[`resume/`](resume/)

**渲染与真实性**（改简历数据或重渲染时）：[`.agent/skills/qiaomu-campus-resume/SKILL.md`](.agent/skills/qiaomu-campus-resume/SKILL.md)

**临时文件**（渠道调研、口述、试跑清单）：[`.notes/`](.notes/)

## 检查

**完成命令**（声称投递件完成时跑；校招件把 JSON 换成 `resume-data-campus.json`）：

```bash
python3 .agent/skills/qiaomu-campus-resume/scripts/validate_resume.py \
  resume/resume-data-agent.json --theme swiss
python3 .agent/skills/qiaomu-campus-resume/scripts/render_resume.py \
  resume/resume-data-agent.json --theme swiss \
  --output-dir resume/output
```
