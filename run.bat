@echo off
setlocal
cd /d "%~dp0"

python build.py
if errorlevel 1 exit /b %errorlevel%
python run_m88.py --image build\bad-apple-fm.d88 %*
exit /b %errorlevel%
