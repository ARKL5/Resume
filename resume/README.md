# resume

投递件。瑞士现代（`swiss`）。

| 投 | 数据 | PDF |
| --- | --- | --- |
| Agent 开发实习 | [resume-data-agent.json](resume-data-agent.json) | [output/王中宇_Agent开发实习_简历.pdf](output/王中宇_Agent开发实习_简历.pdf) |
| 2027 届 Agent 应用开发 | [resume-data-campus.json](resume-data-campus.json) | [output/王中宇_2027届_Agent应用开发_简历.pdf](output/王中宇_2027届_Agent应用开发_简历.pdf) |

重渲染：

```bash
python3 .agent/skills/qiaomu-campus-resume/scripts/validate_resume.py \
  resume/resume-data-agent.json --theme swiss
python3 .agent/skills/qiaomu-campus-resume/scripts/render_resume.py \
  resume/resume-data-agent.json --theme swiss \
  --output-dir resume/output

python3 .agent/skills/qiaomu-campus-resume/scripts/validate_resume.py \
  resume/resume-data-campus.json --theme swiss
python3 .agent/skills/qiaomu-campus-resume/scripts/render_resume.py \
  resume/resume-data-campus.json --theme swiss \
  --output-dir resume/output
```
