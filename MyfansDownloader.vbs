Set objShell = CreateObject("WScript.Shell")
strFolder = objShell.CurrentDirectory
objShell.Run "python """ & strFolder & "\main.py""", 1, False
