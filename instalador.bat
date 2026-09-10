@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion
title ContabilidadAPP - Instalador
cd /d "%~dp0"

set "PYTHON_VERSION=3.12.10"
set "PYTHON_EMBED_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/python-%PYTHON_VERSION%-embed-amd64.zip"
set "EMBED_ZIP=python-%PYTHON_VERSION%-embed-amd64.zip"
set "PYTHON_DIR=%~dp0python"
set "APP_NAME=ContabilidadAPP"

echo ==============================================
echo   ContabilidadAPP - Instalador para Windows
echo ==============================================
echo.
echo Este instalador va a:
echo   1. Verificar/instalar Python portable (sin tocar el sistema)
echo   2. Instalar las dependencias de la aplicacion
echo   3. Ejecutar las migraciones de la base de datos
echo   4. Crear el acceso directo en el Escritorio
echo.
echo [NOTA] Se necesita internet SOLO la primera vez para
echo        descargar Python (~11 MB). Despues todo funciona offline.
echo.

if "%~1"=="--silent" goto start_nocheck
choice /C SN /M "¿Desea continuar? [S]i / [N]o"
if errorlevel 2 exit /b
:start_nocheck

echo.

REM ==============================================
REM PASO 1: Verificar o instalar Python portable
REM ==============================================
echo [1/4] Verificando Python portable...

if exist "%PYTHON_DIR%\python.exe" (
    echo   [OK] Python portable encontrado en: python\
    goto paso2
)

echo   Python portable NO encontrado.
echo   Se descargara Python %PYTHON_VERSION% portable...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri '%PYTHON_EMBED_URL%' -OutFile '%EMBED_ZIP%' -UseBasicParsing; exit 0 } catch { Write-Host 'Error: ' $_; exit 1 }"
if errorlevel 1 (
    echo.
    echo   [ERROR] No se pudo descargar Python portable.
    echo   Verifique su conexion a internet e intente de nuevo.
    echo   Si ya tiene el archivo %EMBED_ZIP%, coloquelo junto a este
    echo   instalador y ejecutelo de nuevo.
    echo.
    pause
    exit /b 1
)

echo   Descargado. Extrayendo...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Path '%EMBED_ZIP%' -DestinationPath '%PYTHON_DIR%' -Force"
if errorlevel 1 (
    echo   [ERROR] No se pudo extraer Python. Elimine la carpeta 'python' y reintente.
    pause
    exit /b 1
)

REM --- Preparar python3xx._pth para que pip/paquetes funcionen ---
for %%Z in ("%PYTHON_DIR%\python*.zip") do set "ZIP_NAME_ACTUAL=%%~nxZ"
for %%F in ("%PYTHON_DIR%\python*._pth") do set "PTH_FILE=%%F"
if defined PTH_FILE (
    > "%PTH_FILE%" (
        echo %ZIP_NAME_ACTUAL%
        echo .
        echo Lib
        echo Lib\site-packages
        echo import site
    )
    echo   Configuracion de Python portable preparada.
) else (
    echo   [AVISO] No se encontro el archivo ._pth. La instalacion podria fallar.
)

REM --- Instalar pip ---
echo   Instalando pip...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile 'get-pip.py' -UseBasicParsing; exit 0 } catch { Write-Host 'Error: ' $_; exit 1 }"
if errorlevel 1 (
    echo   [ERROR] No se pudo descargar get-pip.py. Reintente.
    pause
    exit /b 1
)
"%PYTHON_DIR%\python.exe" get-pip.py --no-warn-script-location 2>nul
if errorlevel 1 (
    echo   [ERROR] No se pudo instalar pip.
    pause
    exit /b 1
)
echo   pip instalado correctamente.

:paso2
echo.
echo [2/4] Instalando dependencias de la aplicacion...
echo   Esto puede tomar unos minutos la primera vez...
"%PYTHON_DIR%\python.exe" -m pip install -r requirements.txt --no-warn-script-location
if errorlevel 1 (
    echo.
    echo   [ERROR] No se pudieron instalar las dependencias.
    echo   Ejecute de nuevo el instalador para reintentar.
    pause
    exit /b 1
)
echo   Dependencias instaladas correctamente.

echo.
echo [3/4] Ejecutando migraciones de la base de datos...
"%PYTHON_DIR%\python.exe" manage.py migrate --no-input
if errorlevel 1 (
    echo   [ERROR] No se pudieron aplicar las migraciones.
    pause
    exit /b 1
)
echo   Base de datos lista.

echo.
echo [4/4] Creando acceso directo en el Escritorio...
REM --- Crear acceso directo con VBScript ---
set "VBS=%TEMP%\crear_acceso.vbs"
set "SHORTCUT=%USERPROFILE%\Desktop\%APP_NAME%.lnk"
set "TARGET=%PYTHON_DIR%\pythonw.exe"
set "ARGS=%CD%\main.py"
set "WORKDIR=%CD%"
> "%VBS%" (
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo sDesktop = oWS.SpecialFolders^("Desktop"^)
    echo Set oLink = oWS.CreateShortcut^(sDesktop ^& "\%APP_NAME%.lnk"^)
    echo oLink.TargetPath = "%TARGET%"
    echo oLink.Arguments = "%ARGS%"
    echo oLink.WorkingDirectory = "%WORKDIR%"
    echo oLink.IconLocation = "%TARGET%,0"
    echo oLink.Description = "ContabilidadAPP - Software Contable"
    echo oLink.WindowStyle = 1
    echo oLink.Save
)
cscript //nologo "%VBS%"
if errorlevel 1 (
    echo   [AVISO] No se pudo crear el acceso directo. Puede usar ejecutar.bat.
) else (
    del "%VBS%" 2>nul
    echo   Acceso directo creado en el Escritorio: "%APP_NAME%.lnk"
)

echo.
echo ==============================================
echo   ¡Instalacion completada correctamente!
echo ==============================================
echo.
echo   Doble click en el icono "%APP_NAME%" del Escritorio
echo   para abrir la aplicacion.
echo.
echo   Todos los datos se guardan dentro de esta carpeta:
echo     %CD%
echo.
pause