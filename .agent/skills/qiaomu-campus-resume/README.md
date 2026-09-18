# 简历渲染（本仓库裁剪）

上游：https://github.com/joeseesun/qiaomu-campus-resume

本副本只保留渲染与校验脚本。投递件与重渲染命令见仓库 [`resume/README.md`](../../../resume/README.md)。

```bash
python3 .agent/skills/qiaomu-campus-resume/scripts/render_resume.py \
  resume/resume-data-agent.json --theme swiss \
  --output-dir resume/output
```
