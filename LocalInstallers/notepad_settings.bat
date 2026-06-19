@echo off

:: 1. סגירת Notepad++ במידה והיא פתוחה
taskkill /f /im notepad++.exe >nul 2>&1
timeout /t 1 /nobreak >nul

:: 2. הגדרת נתיב קובץ הקונפיגורציה
set "CONFIG_FILE=%APPDATA%\Notepad++\config.xml"

:: 3. בדיקה ויצירה של התיקייה והקובץ אם הם לא קיימים (התקנה חדשה)
if not exist "%APPDATA%\Notepad++" mkdir "%APPDATA%\Notepad++"

if not exist "%CONFIG_FILE%" (
    echo ^<NotepadPlus^>^<GUIConfigs^>^<GUIConfig name="DarkMode" enable="yes" /^>^</GUIConfigs^>^</NotepadPlus^> > "%CONFIG_FILE%"
    echo [+] Created a new config.xml with Dark Mode enabled!
    timeout /t 3 >nul
    exit /b
)

:: 4. שימוש בפקודת PowerShell ישירה (בתוך ה-CMD) להחלפת הטקסט בצורה בטוחה
powershell -Command "(Get-Content '%CONFIG_FILE%') -replace 'name=\"DarkMode\" enable=\"no\"', 'name=\"DarkMode\" enable=\"yes\"' | Set-Content '%CONFIG_FILE%'"

echo [+] Notepad++ Dark Mode has been successfully enabled!
timeout /t 3 >nul