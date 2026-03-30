Set oShell = CreateObject("WScript.Shell")
oShell.Run "cmd /c pm2 stop all", 0, True
MsgBox "DevForgeAI stopped.", 64, "DevForgeAI"
