Set objShell = CreateObject("WScript.Shell")
strFolder = objShell.CurrentDirectory
objShell.Run "python """ & strFolder & "\MyfansDownloader_unified.py""", 1, False
