@echo off
if "%DSHAPTICS_DIR%"=="" set DSHAPTICS_DIR=%~dp0..
cd /d %DSHAPTICS_DIR%
:loop
C:\Python314\python.exe -u refrec.py C:\Users\Public\dshaptics\ref DS2.exe StellarBlade SB-Win64 LOP-Win64 b1-Win64 >> refrec.log 2>&1
ping -n 6 127.0.0.1 >nul
goto loop
