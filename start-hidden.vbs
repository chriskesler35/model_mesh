Set oShell = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")
scriptDir = oFSO.GetParentFolderName(WScript.ScriptFullName)

' Run PowerShell start script completely hidden
oShell.Run "powershell.exe -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & scriptDir & "\Start-DevForgeAI.ps1""", 0, True

MsgBox "DevForgeAI is running in the background." & vbCrLf & vbCrLf & _
       "Frontend: http://localhost:3001" & vbCrLf & _
       "Backend:  http://localhost:19000" & vbCrLf & vbCrLf & _
       "To stop: double-click stop-hidden.vbs", 64, "DevForgeAI"
