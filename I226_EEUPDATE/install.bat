@ECHO OFF
REM Copyright Intel Corporation 2004-2022
REM Version 1.0
REM Function summary:
REM    This batch file helps install the driver needed for the tools to run
REM ------------------------------------------------------------------

REM Determine explicit location of .exe files used in this script
set drvload=%systemroot%\system32\drvload.exe
set pnputil=%systemroot%\system32\pnputil.exe
set powershell=%systemroot%\system32\WindowsPowerShell\v1.0\powershell.exe
set wmic=%systemroot%\system32\wbem\wmic.exe

set sysfilename=iqvsw64e.sys
REM Check if a sys already exists in the install directory that
REM the installation will get the file.
if exist .\%sysfilename% GOTO instfileexists
ECHO %sysfilename% file not found in installation directory.
ECHO Please make sure that %sysfilename% exists in the same
ECHO directory as install.bat
GOTO exit

:instfileexists
REM Check if a %sysfilename% already exists in the Windows install directory
echo Welcome to the Tools driver installation program.
echo After installation of the driver (%sysfilename%), the tool can be invoked.
echo -----------------------------------------------------------------------
echo Checking to see if %sysfilename% exists on system
if exist %systemroot%\system32\drivers\%sysfilename% GOTO chkver
GOTO clninst

:chkver
REM Compare versions to see if driver to install has lower version than installed driver
setlocal
set drvpath=%systemroot:\=\\%
set drvpath=%drvpath%\\system32\\drivers\\%sysfilename%

if exist %wmic% (
for /f "usebackq delims=" %%a in (`"%wmic% datafile where name='%drvpath%' get Version /format:Textvaluelist"`) do (
    for /f "delims=" %%# in ("%%a") do set "%%#"
)
) else ( for /f "tokens=*" %%a in (
  '%powershell% -NoLogo -NoProfile -Command "(Get-Item -Path '%drvpath%').VersionInfo.FileVersion"'
  ) do ( set version=%%a)
)
set instver=%version%
echo Installed version: %instver%

set newdrv=%~dp0%sysfilename%
set newdrv=%newdrv:\=\\%
set version=

if exist %wmic% (
for /f "usebackq delims=" %%a in (`"%wmic% datafile where name='%newdrv%' get Version /format:Textvaluelist"`) do (
    for /f "delims=" %%# in ("%%a") do set "%%#"
)
) else ( for /f "tokens=*" %%a in (
  '%powershell% -NoLogo -NoProfile -Command "(Get-Item -Path '%drvpath%').VersionInfo.FileVersion"'
  ) do ( set version=%%a)
)
set newver=%version%
echo New version: %newver%

for /f "tokens=1,2,3,4 delims=. " %%a in ("%instver%") do set /a vmaj=%%a&set /a vmin=%%b&set /a vpatch=%%c&set /a vbuild=%%d
for /f "tokens=1,2,3,4 delims=. " %%a in ("%newver%") do set /a vmajn=%%a&set /a vminn=%%b&set /a vpatchn=%%c&set /a vbuildn=%%d

if %vmajn% LSS %vmaj% GOTO chkextendg
if %vmajn% GTR %vmaj% GOTO nodowngrade
if %vminn% LSS %vmin% GOTO chkextendg
if %vminn% GTR %vmin% GOTO nodowngrade
if %vpatchn% LSS %vpatch% GOTO chkextendg
if %vpatchn% GTR %vpatch% GOTO nodowngrade
if %vbuildn% LSS %vbuild% GOTO chkextendg
if %vbuildn% GTR %vbuild% GOTO nodowngrade
:nodowngrade
set downgrade=0
GOTO chkexteny

:chkextendg
echo Driver is lower version number
if "%1" == "/dg" GOTO extenbldg
set downgrade=1
GOTO options

:extenbldg
echo /dg extension is enabled!
GOTO copysys

:chkexteny
REM Check to see if /y extension is enabled
if "%1" == "/y" GOTO extenbly
GOTO options

:extenbly
echo /y extension is enabled!
GOTO copysys

:options
REM %sysfilename% file existence has been confirmed
REM Time to tell the user the options
echo ----------------------------------------------------------------------
echo An %sysfilename% file is already present on your system.
echo By overwriting this file (it exists in %systemroot%\system32\drivers)
echo there is a potential of blue-screens in PROSet and/or other tools
echo that already EXIST on the system.
echo *  If PROSet is installed, please uninstall PROSet and perform
echo    this setup again.  Please note, by re-installing PROSet later on,
echo    PROSet could render this tool useless and will require
echo    running install.bat again to make the tool work.
echo *  If PROSet not installed, this file could be used by another
echo    corresponding tool.  This may cause a blue-screen or failure in
echo    existing tools using the old %sysfilename% file, so you may want to
echo    rename the file for backup reasons.  If you want to overwrite
echo    %sysfilename%, please re-run the installation with a /y extension
echo    (install.bat /y). If you are downgrading to an older version use
echo    the /dg extension (install.bat /dg).
echo ----------------------------------------------------------------------
echo.
goto exit

:clninst
REM This path is taken when a sys file does not exist on the system
echo No existing %sysfilename% file exists
GOTO copysys

:copysys
REM This copies the file whether or not something exist.
echo Copying %sysfilename% file to %systemroot%\system32\drivers
copy %sysfilename% %systemroot%\system32\drivers /y
rem for /f "tokens=4-7 delims=[.] " %i in ('ver') do @(if %i==Version (echo %j.%k.%l) else (echo %i.%j.%k))
for /f "tokens=4-7 delims=[.] " %%i in ('ver') do (if %%i==Version (set v=%%j.%%k) else (set v=%%i.%%j))
if /i "%v%" == "10.0" (
echo Installing INF file
%pnputil% /a iqvsw64e.inf
if not %ERRORLEVEL%==0 (
echo Trying to install driver by drvload
%drvload% iqvsw64e.inf
)
)

echo Installation done!  You can now invoke the tool.  To exit,
GOTO end

:exit
REM Exit point for a aborted install
cls
if %downgrade% equ 0 (
echo Aborting installation because driver already exists. Run install /y to override!
) else (
echo You attempted to downgrade the driver. Use the install script's /dg parameter to downgrade the driver.
)
echo To Exit,
:end
PAUSE
