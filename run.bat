@echo off
REM ===========================================================================
REM  SOMA West SF Agenda Monitor - manual runner
REM  Double-click to run a scan now. It scans the agendas, rebuilds the website
REM  in the docs\ folder, writes run.log, and (if GitHub is set up) publishes
REM  the updated site automatically.
REM
REM  The twice-weekly Scheduled Task does NOT use this file -- it runs
REM  pythonw.exe directly (no console window) for reliability. This .bat is just
REM  a convenient way to trigger a scan by hand.
REM ===========================================================================
cd /d "%~dp0"
"C:\Python314\python.exe" scan_agendas.py
echo.
echo Done. See run.log for details, and docs\index.html for the result.
pause
