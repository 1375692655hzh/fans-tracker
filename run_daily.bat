@echo off
rem fans-tracker daily 09:00 scheduled entry (idempotent: skips if done)
cd /d %~dp0
if not exist logs mkdir logs
python main.py daily >> logs\daily.log 2>&1
