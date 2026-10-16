@echo off
rem Abre leer-facturas.ps1 sin tener que cambiar la politica de scripts de Windows, y deja la
rem ventana abierta al acabar para que se pueda leer lo que dice.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0leer-facturas.ps1" %*
pause
