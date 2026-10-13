@echo off
rem ============================================================
rem  MODULER YEREL ZEKÂ - TEK TIKLA BASLATICI (Windows)
rem  Tum kontrolleri yapar, eksikleri kurar, paneli tarayicida acar.
rem ============================================================
cd /d "%~dp0"
title Modüler Yerel Zekâ - Başlatıcı
chcp 65001 >nul

echo ============================================================
echo    MODÜLER YEREL ZEKÂ SİSTEMİ - OTOMATİK BAŞLATMA
echo ============================================================
echo.

rem --- 1) Python bul: önce py çalıştırıcısı, sonra python ---
set "PY_CMD="
py -3 --version >nul 2>&1
if %errorlevel%==0 set "PY_CMD=py -3"
if not defined PY_CMD (
    python --version >nul 2>&1
    if %errorlevel%==0 set "PY_CMD=python"
)
if not defined PY_CMD (
    echo !! Python bulunamadı. https://python.org adresinden kurun
    echo    ^(kurulumda "Add Python to PATH" kutusunu işaretleyin^).
    pause
    exit /b 1
)
echo [OK] Python komutu: %PY_CMD%
echo.

rem --- 2) Sanal ortam yoksa oluştur ---
if not exist ".venv" (
    echo [..] İlk kurulum: sanal ortam oluşturuluyor...
    %PY_CMD% -m venv .venv
    if errorlevel 1 (
        echo !! Sanal ortam oluşturulamadı.
        pause & exit /b 1
    )
)

rem --- 3) Sanal ortama geç, bağımlılıkları kur/güncelle ---
call ".venv\Scripts\activate.bat"
echo [..] Bağımlılıklar kontrol ediliyor...
pip install --quiet --disable-pip-version-check -r gereksinimler.txt
if errorlevel 1 (
    echo !! Paket kurulumu başarısız. İnternet/kurulum günlüğünü kontrol edin.
    pause & exit /b 1
)

rem --- 4) Asıl başlatıcıyı çalıştır (tüm kontrollerin içi Python'da) ---
echo.
python baslat.py

echo.
pause
