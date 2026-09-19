$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = Join-Path $root '.venv\Scripts\python.exe'
$val = Join-Path $root '.agents\skills\qiaomu-campus-resume\scripts\validate_resume.py'
if (-not (Test-Path $py)) {
    Write-Error "missing .venv python: $py"
    exit 1
}

$files = @(
    (Join-Path $root 'resume\resume-data-agent.json'),
    (Join-Path $root 'resume\resume-data-campus.json')
)
foreach ($file in $files) {
    & $py $val $file --theme swiss
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
