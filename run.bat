@echo off
REM ===========================================================================
REM  SOMA West SF Agenda Monitor - scheduled runner
REM  Double-click to run a scan now, or let Windows Task Scheduler run it 2x/week.
REM  It scans the agendas, rebuilds the website in the docs\ folder, and (if a
REM  GitHub remote is set up) publishes the updated site to the web.
REM ===========================================================================
cd /d "%~dp0"

echo. >> run.log
echo ============================================== >> run.log
echo Run started %date% %time% >> run.log

"C:\Python314\python.exe" scan_agendas.py >> run.log 2>&1
set SCAN_RESULT=%errorlevel%

if not "%SCAN_RESULT%"=="0" (
    echo Scan FAILED with code %SCAN_RESULT% - see messages above. >> run.log
    goto :end
)

REM --- Publish to the web only if a GitHub remote named 'origin' exists ---
git remote get-url origin >nul 2>&1
if "%errorlevel%"=="0" (
    echo Publishing updated site to GitHub... >> run.log
    git add -A >> run.log 2>&1
    git commit -m "Agenda scan %date%" >> run.log 2>&1
    git push >> run.log 2>&1
) else (
    echo No GitHub remote configured yet - site saved locally in docs\ only. >> run.log
)

:end
echo Run finished %date% %time% >> run.log
