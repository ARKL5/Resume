$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$val = Join-Path $root '.agents\skills\qiaomu-campus-resume\scripts\validate_resume.py'

$files = @(
    (Join-Path $root 'resume\resume-data-agent.json'),
    (Join-Path $root 'resume\resume-data-campus.json')
)
foreach ($file in $files) {
    uv run $val $file --theme swiss
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
