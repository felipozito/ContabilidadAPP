@echo off
chcp 65001 >nul 2>&1
title ContabilidadAPP
cd /d "%~dp0"

REM ==============================================
REM  Lanzador de emergencia (si falla el acceso directo)
REM ==============================================

if exist "python\python.exe" (
    echo Usando Python portable de la carpeta "python"...
    "python\python.exe" main.py
    goto fin
)

where python >nul 2>nul
if not errorlevel 1 (
    echo Usando Python del sistema...
    python main.py
    goto fin
)

echo.
echo [ERROR] No se encontro Python.
echo Ejecute primero instalador.bat para configurar la aplicacion.
echo.
pause

:fin