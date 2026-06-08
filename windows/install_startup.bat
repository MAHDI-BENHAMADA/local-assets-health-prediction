@echo off
echo Installing ITAM Agent to Windows Startup...

:: Get the exact paths
set "STARTUP_FOLDER=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "AGENT_DIR=%~dp0"
set "VBS_FILE=%STARTUP_FOLDER%\itam_agent_startup.vbs"

:: Generate the VBS script directly into the startup folder with absolute paths
echo Set WshShell = CreateObject("WScript.Shell") > "%VBS_FILE%"
echo WshShell.CurrentDirectory = "%AGENT_DIR%" >> "%VBS_FILE%"
echo WshShell.Run "cmd /c taskkill /F /IM pythonw.exe", 0, True >> "%VBS_FILE%"
echo WshShell.Run "pythonw.exe agent_windows_continuous.py", 0, False >> "%VBS_FILE%"

echo.
echo Successfully installed! The agent will now automatically start in the background every time Windows boots.
pause
