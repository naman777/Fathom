@echo off
REM Double-click or run `run.bat [flags]` from the project folder. Same as: python run.py [flags]
cd /d "%~dp0"
where py >nul 2>nul && (py -3 run.py %* & goto :eof)
where python >nul 2>nul && (python run.py %* & goto :eof)
echo Python 3.10+ was not found on PATH. Install it from https://www.python.org/downloads/
pause
