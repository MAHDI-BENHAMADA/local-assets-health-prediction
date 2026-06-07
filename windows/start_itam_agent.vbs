Set WshShell = CreateObject("WScript.Shell")
' Run the continuous Windows agent invisibly using pythonw
' The 0 means "Hide Window", and False means "Don't wait for it to finish"
WshShell.Run "pythonw.exe agent_windows_continuous.py", 0, False
