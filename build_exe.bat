@echo off
setlocal enabledelayedexpansion

echo ==============================================================================
echo        SecureChat E2EE - Procedura di Compilazione e Packaging Windows
echo ==============================================================================
echo.

:: 1. Verifica ambiente Python
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ATTENZIONE] Python non e' presente nel PATH. Provo con 'py'...
    py --version >nul 2>&1
    if %ERRORLEVEL% NEQ 0 (
        echo [ERRORE CRITICO] Python non e' stato trovato. Installa Python 3.10+ e riprova.
        pause
        exit /b 1
    ) else (
        set PY_CMD=py
    )
) else (
    set PY_CMD=python
)

echo [1/4] Installazione dipendenze da requirements.txt...
%PY_CMD% -m pip install --upgrade pip
%PY_CMD% -m pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Errore durante l'installazione dei pacchetti pip.
    pause
    exit /b 1
)

echo.
echo [2/4] Generazione icone applicazione (se mancanti)...
%PY_CMD% -c "from app.ui.tray_icon import create_default_icon_image; img=create_default_icon_image(256); img.save('assets/app_icon.png'); img.save('assets/app_icon.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])" 2>nul

echo.
echo [3/4] Compilazione con PyInstaller (Binario standalone)...
cd packaging
%PY_CMD% -m PyInstaller --clean --noconfirm pyinstaller.spec
if %ERRORLEVEL% NEQ 0 (
    echo [ERRORE] Compilazione PyInstaller fallita.
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo [4/4] Compilazione Installer con Inno Setup (ISCC.exe)...
set ISCC_PATH="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if not exist %ISCC_PATH% (
    set ISCC_PATH="C:\Program Files\Inno Setup 6\ISCC.exe"
)

if exist %ISCC_PATH% (
    echo Trovato Inno Setup compiler: %ISCC_PATH%
    %ISCC_PATH% packaging\installer.iss
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo ==============================================================================
        echo  COMPILAZIONE COMPLETATA CON SUCCESSO!
        echo  Installer generato in: dist_installer\SecureChat_Setup_v1.0.exe
        echo  Cartella applicazione: dist\SecureChatE2EE\
        echo ==============================================================================
    ) else (
        echo [ERRORE] Inno Setup ha restituito un codice di errore.
    )
) else (
    echo.
    echo [NOTA] Inno Setup non e' installato nel percorso standard.
    echo L'eseguibile compilato e' comunque disponibile e pronto in:
    echo   dist\SecureChatE2EE\SecureChatE2EE.exe
    echo.
    echo Per creare l'installer 'Setup.exe', scarica Inno Setup da:
    echo   https://jrsoftware.org/isdl.php
    echo e ricompila eseguendo: "ISCC.exe packaging\installer.iss"
)

echo.
pause
