@echo off
rem ============================================================
rem  AI 学习助手 - 一键启动（Windows）
rem  双击本文件即可启动；首次运行会自动建环境、装依赖，之后再双击直接启动。
rem
rem  也可以在命令行使用：
rem    start.bat                 启动（默认 8000 端口）
rem    start.bat 8001            指定端口（兼容旧写法）
rem    start.bat setup           只做环境准备（装依赖，网络慢可加 --mirror）
rem    start.bat stop            停止服务
rem    start.bat status          查看运行状态
rem    start.bat doctor          环境诊断
rem
rem  真正的逻辑在 scripts\launcher.py（Windows 与 Linux 共用同一份实现）
rem ============================================================
setlocal
rem 切到 UTF-8 代码页，让中文正常显示（失败也不影响运行）
chcp 65001 >nul 2>&1

set "DIR=%~dp0"
set "LAUNCHER=%DIR%scripts\launcher.py"

rem ---------- 查找 Python ----------
set "PY="
where py >nul 2>&1
if %errorlevel%==0 set "PY=py -3"
if defined PY goto :havepy
where python >nul 2>&1
if %errorlevel%==0 set "PY=python"
:havepy
if not defined PY (
    echo [FAIL] 未找到 Python。请先安装 Python 3.9+
    echo        下载: https://www.python.org/downloads/
    echo        安装时务必勾选 "Add Python to PATH"
    pause
    exit /b 1
)

if not exist "%LAUNCHER%" (
    echo [FAIL] 找不到启动器: %LAUNCHER%
    echo        请确认在项目根目录下运行本脚本。
    pause
    exit /b 1
)

set "FIRST=%~1"
set "SECOND=%~2"
set "PORTARG="

rem ---------- 无参数：启动 ----------
if "%FIRST%"=="" (
    %PY% "%LAUNCHER%" start
    goto :end
)

rem ---------- 第二个参数是纯数字：统一转成 --port（兼容 stop 8001 等旧写法）----------
if "%SECOND%"=="" goto :nosecond
echo %SECOND%|findstr /r "^[0-9][0-9]*$" >nul 2>&1
if %errorlevel%==0 set "PORTARG=--port %SECOND%"
:nosecond

rem ---------- 第一个参数是纯数字：视为端口 ----------
echo %FIRST%|findstr /r "^[0-9][0-9]*$" >nul 2>&1
if %errorlevel%==0 (
    %PY% "%LAUNCHER%" start --port %FIRST% %3 %4 %5
    goto :end
)

rem ---------- 子命令 ----------
if /i "%FIRST%"=="setup" (
    %PY% "%LAUNCHER%" setup %2 %3 %4 %5
    goto :end
)
if /i "%FIRST%"=="stop" (
    if defined PORTARG (
        %PY% "%LAUNCHER%" stop %PORTARG% %3 %4 %5
    ) else (
        %PY% "%LAUNCHER%" stop %2 %3 %4 %5
    )
    goto :end
)
if /i "%FIRST%"=="status" (
    if defined PORTARG (
        %PY% "%LAUNCHER%" status %PORTARG% %3 %4 %5
    ) else (
        %PY% "%LAUNCHER%" status %2 %3 %4 %5
    )
    goto :end
)
if /i "%FIRST%"=="doctor" (
    if defined PORTARG (
        %PY% "%LAUNCHER%" doctor %PORTARG% %3 %4 %5
    ) else (
        %PY% "%LAUNCHER%" doctor %2 %3 %4 %5
    )
    goto :end
)

rem ---------- 其他参数原样透传 ----------
%PY% "%LAUNCHER%" start %*

:end
if errorlevel 1 (
    echo.
    echo [INFO] 上面有错误信息，按任意键关闭窗口...
    pause >nul
)
endlocal
