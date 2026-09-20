param(
    [string]$Message = "get_jobs 需要你处理 Boss 页面"
)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$n = New-Object System.Windows.Forms.NotifyIcon
$n.Icon = [System.Drawing.SystemIcons]::Exclamation
$n.BalloonTipTitle = "get_jobs 需要你"
$n.BalloonTipText = $Message
$n.BalloonTipIcon = [System.Windows.Forms.ToolTipIcon]::Warning
$n.Visible = $true
$n.ShowBalloonTip(20000)
try { [Console]::Beep(880, 350); [Console]::Beep(1175, 450) } catch {}
Start-Sleep -Seconds 22
$n.Dispose()
