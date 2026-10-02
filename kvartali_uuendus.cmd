@echo off
rem Kvartali automaatne uuendus: kogub kv.ee andmed nähtava Edge'i aknaga, arvutab tulemused
rem ja lükkab need GitHubi (leht uueneb GitHub Pagesis). Käivitab Windowsi Task Scheduler.
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
if not exist data\logid mkdir data\logid
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set STAMP=%%i
set LOG=data\logid\%STAMP%.log

echo === Kvartali uuendus %STAMP% === > "%LOG%"
git checkout main >> "%LOG%" 2>&1
git pull >> "%LOG%" 2>&1
python run.py --publish >> "%LOG%" 2>&1
echo === Lõpp, väljumiskood %ERRORLEVEL% === >> "%LOG%"
