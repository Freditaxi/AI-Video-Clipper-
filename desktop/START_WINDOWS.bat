@echo off
setlocal
cd /d "%~dp0"
title Independent AI Clipper
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 bootstrap.py
    goto finished
)
where python >nul 2>nul
if %errorlevel% equ 0 (
    python bootstrap.py
    goto finished
)
echo Python is required. Install Python 3.12 64-bit from https://www.python.org/downloads/
echo Check Add Python to PATH during installation, then open this file again.
:finished
pause
