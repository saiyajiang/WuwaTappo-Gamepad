' Wuwa Tappo Gamepad Bridge - tray launcher (no console window)
' This is what 一键启动.bat calls. You can also double-click this directly.

Option Explicit
Dim sh, fso, here, pyw, py, cmd, rc, o

Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here

pyw = ""
py  = ""

On Error Resume Next
pyw = sh.RegRead("HKCU\SOFTWARE\Python\PythonCore\3.15\InstallPath\") & "pythonw.exe"
If pyw <> "" And Not fso.FileExists(pyw) Then pyw = ""
py  = sh.RegRead("HKCU\SOFTWARE\Python\PythonCore\3.15\InstallPath\") & "python.exe"
If py  <> "" And Not fso.FileExists(py)  Then py  = ""
On Error GoTo 0

If pyw = "" Then
    Set o = sh.Exec("cmd /c where pythonw")
    pyw = Trim(o.StdOut.ReadAll)
    If InStr(pyw, vbCrLf) > 0 Then pyw = Left(pyw, InStr(pyw, vbCrLf) - 1)
End If
If py = "" Then
    Set o = sh.Exec("cmd /c where python")
    py = Trim(o.StdOut.ReadAll)
    If InStr(py, vbCrLf) > 0 Then py = Left(py, InStr(py, vbCrLf) - 1)
End If

If pyw = "" Then pyw = py

If pyw = "" Then
    MsgBox "Python not found. Install Python 3 first.", 16, "Wuwa Tappo Gamepad Bridge"
    WScript.Quit 1
End If

cmd = """" & pyw & """ """ & here & "\src\tray_app.py"""

rc = sh.Run(cmd, 0, False)   ' 0 = hidden, False = do not wait

If rc <> 0 Then
    MsgBox "Failed to start. Run 启动（控制台模式）.bat to see the error.", _
           16, "Wuwa Tappo Gamepad Bridge"
    WScript.Quit 1
End If
