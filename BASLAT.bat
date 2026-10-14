@echo off
rem ============================================================
rem  MODULER YEREL ZEKA - TEK TIKLA BASLATICI (Windows)
rem  Tum kontrolleri yapar, eksikleri kurar, paneli tarayicida acar.
rem  NOT: Bu dosya bilerek TAMAMEN ASCII (Turkce karaktersiz) yazildi;
rem  Turkce karakterler konsolda kodlama hatasi yapip pencerenin
rem  kapanmasina yol acabiliyordu. Python tarafi Turkce devam eder.
rem ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Moduler Yerel Zeka - Baslatici
chcp 65001 >nul

echo ============================================================
echo    MODULER YEREL ZEKA SISTEMI - OTOMATIK BASLATMA
echo ============================================================
echo.

rem --- 1) Python bul: once venv, sonra py calistiricisi, sonra python ---
set "PY_CMD="
if exist ".venv\Scripts\python.exe" set "PY_CMD=.venv\Scripts\python.exe"
if not defined PY_CMD py -3 --version >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD python --version >nul 2>&1 && set "PY_CMD=python"
if not defined PY_CMD (
    echo !! Python bulunamadi. https://python.org adresinden kurun
    echo    ^(kurulumda "Add Python to PATH" kutusunu isaretleyin^).
    pause
    exit /b 1
)
echo [OK] Python komutu: !PY_CMD!
echo.

rem --- 2) Sanal ortam yoksa olustur ---
if not exist ".venv\Scripts\python.exe" (
    echo [..] Ilk kurulum: sanal ortam olusturuluyor... ^(biraz surabilir^)
    "!PY_CMD!" -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo !! Sanal ortam olusturulamadi.
        pause & exit /b 1
    )
)

rem --- 3) Bagimliliklari kur/guncelle (activate yerine dogrudan venv python) ---
set "VPY=.venv\Scripts\python.exe"
echo [..] Bagimliliklar kontrol ediliyor...
"!VPY!" -m pip install --quiet --disable-pip-version-check -r gereksinimler.txt
if errorlevel 1 (
    echo !! Paket kurulumu basarisiz. Internet/kurulum gunlugunu kontrol edin.
    pause & exit /b 1
)

rem --- 4) Asil baslaticiyi calistir (tum kontrollerin ici Python'da) ---
echo.
"!VPY!" baslat.py
set "RC=!errorlevel!"
if not "!RC!"=="0" (
    echo.
    echo ============================================================
    echo !! Sistem kapanis kodu: !RC!
    echo !! En sik nedenler:
    echo    - Port 8765 kullanmda: ayarlar\ayarlar.json icinde
    echo      "sunucu.port" degerini 8766 gibi baska bir sayi yapin.
    echo    - Eski bir sistem penceresi hala acik: gorev yonetcisinden
    echo      python.exe surecini kapatip tekrar deneyin.
    echo    - Windows Defender / antivirus .venv icinden calistirmayi
    echo      engelliyor olabilir: klasoru izin listesine ekleyin.
    echo ============================================================
)

echo.
pause
