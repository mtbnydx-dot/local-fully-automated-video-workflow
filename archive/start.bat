@echo off
setlocal

cd /d "%~dp0"

if not exist "%~dp0START_WORKFLOW.bat" (
    echo START_WORKFLOW.bat was not found in:
    echo %~dp0
    echo.
    echo Please keep start.bat in the project root folder.
    pause
    exit /b 1
)

call "%~dp0START_WORKFLOW.bat" %*
exit /b %ERRORLEVEL%
