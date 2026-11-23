@echo off
REM Прошивка STM32 через D.UNI Probe без IDE.
REM Використання:  flash_stm32.bat firmware.elf     (або .hex; для .bin додайте адресу: firmware.bin 0x08000000)
REM OpenOCD: вкажіть шлях, якщо openocd.exe немає в PATH
set OPENOCD=openocd
if exist "%USERPROFILE%\.pico-sdk\openocd\0.12.0+dev\openocd.exe" set OPENOCD="%USERPROFILE%\.pico-sdk\openocd\0.12.0+dev\openocd.exe"
set SCRIPTS=
if exist "%USERPROFILE%\.pico-sdk\openocd\0.12.0+dev\scripts" set SCRIPTS=-s "%USERPROFILE%\.pico-sdk\openocd\0.12.0+dev\scripts"
%OPENOCD% %SCRIPTS% -f "%~dp0duni_stm32.cfg" -c "program %~1 %~2 verify reset exit"
pause
