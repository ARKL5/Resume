---
name: qiaomu-campus-resume
description: |
  本仓库裁剪副本：渲染 resume/ 下瑞士现代（swiss）投递件。实习件 resume-data-agent.json，校招件 resume-data-campus.json。不要访谈、不要按 JD 另写一份、不要一次生成多种风格。
---

# 简历渲染（本仓库裁剪）

本副本只保留本仓库投递件需要的渲染与校验。

- 数据：[`resume/resume-data-agent.json`](../../../resume/resume-data-agent.json)（实习）、[`resume/resume-data-campus.json`](../../../resume/resume-data-campus.json)（2027 届校招）
- 唯一主题：`swiss`
- 经历与数字只写已有证据

改 JSON 前读 [数据契约](references/data-contract.md)、[真实性与证据](references/content-integrity.md)、[写作与版式](references/best-practices.md)。中文 bullet 注意 92 字警告。

## 校验与渲染

解释器用仓库 `uv`：

```bash
uv run .agents/skills/qiaomu-campus-resume/scripts/validate_resume.py \
  resume/resume-data-agent.json --theme swiss

uv run .agents/skills/qiaomu-campus-resume/scripts/render_resume.py \
  resume/resume-data-agent.json --theme swiss \
  --output-dir resume/output
```

校招件把 JSON 换成 `resume/resume-data-campus.json`。产物文件名来自 JSON `filename`。验收见 [视觉与 PDF](references/visual-and-pdf.md)、[字体系统](references/typography-system.md)。
