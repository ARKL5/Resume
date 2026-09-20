@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
chcp 65001 >nul

REM 结束本机 Boss API / CDP 端口
set PORTS=9527 7866

echo ===============================================
echo 关闭端口进程: %PORTS%
echo ===============================================

for %%P in (%PORTS%) do call :KILL_BY_PORT %%P

echo 完成。
goto :EOF

:KILL_BY_PORT
set PORT=%~1
echo [端口 %PORT%] 检查监听中进程...
set FOUND=
for /f "tokens=5" %%I in ('netstat -ano ^| findstr /R /C:"LISTENING" ^| findstr /C:":%PORT%"') do (
  set FOUND=1
  set PID=%%I
  echo [端口 %PORT%] 结束 PID !PID! ...
  taskkill /F /PID !PID! >nul 2>&1
  if !ERRORLEVEL! EQU 0 (
    echo [端口 %PORT%] 已结束 PID !PID!
  ) else (
    echo [端口 %PORT%] 结束 PID !PID! 失败(可能已退出)
  )
)
if not defined FOUND (
  echo [端口 %PORT%] 未发现监听进程
)
goto :EOF
