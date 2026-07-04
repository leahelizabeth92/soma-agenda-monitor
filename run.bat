@echo off
REM ===========================================================================
REM  SOMA West SF Agenda Monitor - manual runner (optional)
REM
REM  You normally do NOT need this: the scan runs automatically in the cloud
REM  (GitHub Actions) every Monday and Thursday, and you can run it on demand
REM  from the repo's "Actions" tab -> "Scan SF agendas" -> "Run workflow"
REM  (no laptop required).
REM
REM  This file is just a way to run a scan locally on your PC if you ever want
REM  to. It refreshes from GitHub first, scans, rebuilds docs\, and publishes.
REM ===========================================================================
cd /d "%~dp0"
"C:\Program Files\Git\cmd\git.exe" pull --ff-only
"C:\Python314\python.exe" scan_agendas.py
echo.
echo Done. See run.log for details, and docs\index.html for the result.
pause
