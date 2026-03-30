Set oShell = CreateObject("WScript.Shell")
Set oFSO = CreateObject("Scripting.FileSystemObject")

' Get the directory this script is in
scriptDir = oFSO.GetParentFolderName(WScript.ScriptFullName)

' Kill anything on ports 3001 and 19000 first
oShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr "":19000 "" ^| findstr LISTENING') do taskkill /F /PID %a", 0, True
oShell.Run "cmd /c for /f ""tokens=5"" %a in ('netstat -ano ^| findstr "":3001 "" ^| findstr LISTENING') do taskkill /F /PID %a", 0, True

' Wait 2 seconds
WScript.Sleep 2000

' Start PM2 completely hidden (window style 0 = invisible)
oShell.Run "cmd /c cd /d """ & scriptDir & """ && pm2 delete all && pm2 start ecosystem.config.js && pm2 save", 0, True

MsgBox "DevForgeAI is running in the background." & vbCrLf & vbCrLf & "Frontend: http://localhost:3001" & vbCrLf & "Backend:  http://localhost:19000" & vbCrLf & vbCrLf & "To stop: double-click stop.bat", 64, "DevForgeAI"
