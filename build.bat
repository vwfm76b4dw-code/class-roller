@echo off
chcp 65001 >nul
echo ========================================
echo   课堂抽奖器 - 构建
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请安装 Python 3.10+
    echo         ^(仅构建时需要 Python，打好的软件不需要^)
    pause
    exit /b 1
)

echo [1/2] 安装构建依赖...
python -m pip install -q pyinstaller customtkinter pystray Pillow
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo [2/2] 构建...
python tools\build.py --zip %*
if errorlevel 1 (
    echo.
    echo [错误] 构建失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo   完成
echo   dist\class-roller\class-roller.exe   ^<- 双击运行
echo   dist\class-roller-*-win64.zip        ^<- 发给别人
echo ========================================
pause
