#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
val="$root/.agents/skills/qiaomu-campus-resume/scripts/validate_resume.py"
for file in resume/resume-data-agent.json resume/resume-data-campus.json; do
  uv run "$val" "$file" --theme swiss
done
