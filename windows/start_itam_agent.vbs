Set WshShell = CreateObject("WScript.Shell")
' 1. Gracefully kill any existing background agents to prevent duplicates!
WshShell.Run "cmd /c taskkill /F /IM pythonw.exe", 0, True

' 2. Run the continuous Windows agent invisibly using pythonw
' The 0 means "Hide Window", and False means "Don't wait for it to finish"
WshShell.Run "pythonw.exe agent_windows_continuous.py", 0, False
