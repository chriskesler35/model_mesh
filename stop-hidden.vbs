Set oShell = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = oFSO.GetParentFolderName(WScript.ScriptFullName)

oShell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & scriptDir & "\Stop-DevForgeAI.ps1""", 0, True

MsgBox "DevForgeAI stopped.", 64, "DevForgeAI"
