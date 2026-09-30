' LuminaPhoto Silent Desktop Launcher
' Runs LuminaPhoto with zero console window flash using Windows Script Host and pythonw.exe

Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objShell = CreateObject("WScript.Shell")

strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Find pythonw.exe
strPythonw = "pythonw.exe"
If objFSO.FileExists("C:\Python313\pythonw.exe") Then
    strPythonw = "C:\Python313\pythonw.exe"
End If

strCommand = """" & strPythonw & """ """ & strScriptDir & "\start_desktop.py"""

' Run completely hidden (0 = hide window, false = do not wait)
objShell.Run strCommand, 0, False
