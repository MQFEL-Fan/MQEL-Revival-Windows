@echo off
rem Builds xinput9_1_0.dll (32-bit, like MightyQuest.exe) with the MSVC Build Tools.
setlocal
set "HERE=%~dp0"
set "VCVARS="
for %%V in (2022 2019) do (
  for %%E in (BuildTools Community Professional Enterprise) do (
    if not defined VCVARS if exist "C:\Program Files (x86)\Microsoft Visual Studio\%%V\%%E\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=C:\Program Files (x86)\Microsoft Visual Studio\%%V\%%E\VC\Auxiliary\Build\vcvarsall.bat"
    if not defined VCVARS if exist "C:\Program Files\Microsoft Visual Studio\%%V\%%E\VC\Auxiliary\Build\vcvarsall.bat" set "VCVARS=C:\Program Files\Microsoft Visual Studio\%%V\%%E\VC\Auxiliary\Build\vcvarsall.bat"
  )
)
if not defined VCVARS (
  echo MSVC Build Tools not found.
  exit /b 1
)
call "%VCVARS%" x86 >nul || exit /b 1
if not exist "%HERE%bin" mkdir "%HERE%bin"
cd /d "%HERE%bin"
cl /nologo /O2 /W3 /MT /LD /D_CRT_SECURE_NO_WARNINGS "%HERE%xinput_wasd.c" /link /DEF:"%HERE%xinput9_1_0.def" /OUT:xinput9_1_0.dll ws2_32.lib user32.lib || exit /b 1
del /q xinput_wasd.obj xinput_wasd.lib xinput_wasd.exp 2>nul
echo Built %HERE%bin\xinput9_1_0.dll
