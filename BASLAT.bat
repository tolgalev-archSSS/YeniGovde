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

rem --- 1) Python bul: once venv, sonra py, sonra python ---
rem     Duz komut adlari tutulur ("!PY_ARGS!" ayrilmis), tirnak sorunu yok.
set "VPY=.venv\Scripts\python.exe"
set "PY_EXE="
set "PY_ARGS="
if exist "%VPY%" set "PY_EXE=%VPY%"
if not defined PY_EXE (
    py -3 --version >nul 2>&1
    if not errorlevel 1 (
        set "PY_EXE=py"
        set "PY_ARGS=-3"
    )
)
if not defined PY_EXE (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY_EXE=python"
)
if not defined PY_EXE (
    echo !! Python bulunamadi. https://python.org adresinden kurun
    echo    ^(kurulumda "Add Python to PATH" kutusunu isaretleyin^).
    pause
    exit /b 1
)
echo [OK] Python: !PY_EXE! !PY_ARGS!
echo.

rem --- 2) Sanal ortam yoksa olustur (venv'de pip genelde hazirdir;
rem     Windows'ta bazen eksik olur -> ensurepip ile tamamla) ---
if not exist "%VPY%" (
    echo [..] Ilk kurulum: sanal ortam olusturuluyor... ^(biraz surabilir^)
    set "OLUSTUR=!PY_EXE! !PY_ARGS!"
    !OLUSTUR! -m venv .venv
    if not exist "%VPY%" (
        echo !! Sanal ortam olusturulamadi. Python kurulumunu kontrol edin.
        pause & exit /b 1
    )
    "%VPY%" -m pip --version >nul 2>&1
    if errorlevel 1 (
        echo [..] venv icinde pip eksik, ensurepip ile tamamlaniyor...
        "%VPY%" -m ensurepip --upgrade >nul 2>&1
        "%VPY%" -m pip --version >nul 2>&1
        if errorlevel 1 (
            echo !! pip kurulamadi. Yedek yol: sistem Python'i ile devam ediliyor.
            set "PIP_TAM=!PY_EXE! !PY_ARGS!"
        )
    )
)

rem --- 3) Bagimliliklari kur/guncelle (activate yerine dogrudan venv python) ---
if not defined PIP_TAM (
    set "PIP_TAM=%VPY%"
)
echo [..] Bagimliliklar kontrol ediliyor...
!PIP_TAM! -m pip install --quiet --disable-pip-version-check -r gereksinimler.txt
if errorlevel 1 (
    echo !! Paket kurulumu basarisiz. Internet/kurulum gunlugunu kontrol edin.
    pause & exit /b 1
)

rem --- 4) Asil baslaticiyi calistir (tum kontrollerin ici Python'da) ---
rem     venv kullanilabilirse onun python'i, degilse sistem python'i ile calisir.
if exist "%VPY%" (
    set "RUN_PY=%VPY%"
) else (
    set "RUN_PY=!PY_EXE! !PY_ARGS!"
)
echo.
!RUN_PY! baslat.py
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
