@echo off
cd /d "%~dp0"
if exist ".python\cpython-3.13.13-windows-x86_64-none\python.exe" (
    ".python\cpython-3.13.13-windows-x86_64-none\python.exe" vanity_checker.py %*
) else (
    py vanity_checker.py %*
)
pause
