@echo off
setlocal
title QGIS Boundary Search Plugin Builder
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 goto try_python
py -3 "%~dp0build_boundary_plugin.py"
set "BUILD_EXIT=%ERRORLEVEL%"
goto result

:try_python
where python >nul 2>&1
if errorlevel 1 goto no_python
python "%~dp0build_boundary_plugin.py"
set "BUILD_EXIT=%ERRORLEVEL%"
goto result

:no_python
echo.
echo ERROR: Python 3 was not found.
echo Install Python 3 from https://www.python.org/downloads/
echo During installation, tick "Add Python to PATH".
echo.
pause
exit /b 1

:result
echo.
if not "%BUILD_EXIT%"=="0" (
    echo The plugin was not created. Read the error shown above.
) else (
    echo Finished successfully.
)
echo.
pause
exit /b %BUILD_EXIT%
