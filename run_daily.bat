@echo off
rem fans-tracker 每天 09:00 计划任务入口(幂等: 当天已完成则直接退出)
cd /d %~dp0
if not exist logs mkdir logs
python main.py daily >> logs\daily.log 2>&1
