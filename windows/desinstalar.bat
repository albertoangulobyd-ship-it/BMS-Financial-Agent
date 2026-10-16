@echo off
rem Abre desinstalar.ps1 sin tener que cambiar la politica de scripts de Windows. Todo en
rem una linea: la carpeta de este fichero puede borrarse mientras corre. Primero sale de ella
rem (cd): una ventana cuya carpeta actual es esa no deja borrarla.
cd /d "%SystemRoot%" & powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0desinstalar.ps1" %* & pause & exit /b
