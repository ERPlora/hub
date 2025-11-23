# Script PowerShell para compilar el instalador de ERPlora Hub con Inno Setup
# Requiere: Inno Setup 6+ instalado

param(
    [string]$Version = "0.8.0"
)

Write-Host "[INFO] Compilando instalador de ERPlora Hub v$Version para Windows" -ForegroundColor Green

# Verificar que Inno Setup está instalado
$InnoSetupPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $InnoSetupPath)) {
    $InnoSetupPath = "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
}

if (-not (Test-Path $InnoSetupPath)) {
    Write-Host "[ERROR] Inno Setup no encontrado. Descarga desde: https://jrsoftware.org/isdl.php" -ForegroundColor Red
    Write-Host "[INFO] Instalando Inno Setup via Chocolatey..." -ForegroundColor Yellow

    # Intentar instalar via chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install innosetup -y
        $InnoSetupPath = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
    }
    else {
        Write-Host "[ERROR] Instala Chocolatey (https://chocolatey.org) o Inno Setup manualmente" -ForegroundColor Red
        exit 1
    }
}

Write-Host "[OK] Inno Setup encontrado: $InnoSetupPath" -ForegroundColor Green

# Verificar que existe el build de PyInstaller
$BuildPath = "..\..\dist\main"
if (-not (Test-Path $BuildPath)) {
    Write-Host "[ERROR] Build de PyInstaller no encontrado en: $BuildPath" -ForegroundColor Red
    Write-Host "[INFO] Ejecuta primero: pyinstaller main.spec" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Build encontrado en: $BuildPath" -ForegroundColor Green

# Actualizar versión en setup.iss
Write-Host "[INFO] Actualizando versión en setup.iss..." -ForegroundColor Cyan
$SetupFile = "setup.iss"
$Content = Get-Content $SetupFile -Raw
$Content = $Content -replace '#define MyAppVersion ".*"', "#define MyAppVersion `"$Version`""
$Content | Set-Content $SetupFile -NoNewline

# Compilar con Inno Setup
Write-Host "[INFO] Compilando instalador con Inno Setup..." -ForegroundColor Cyan
& $InnoSetupPath $SetupFile /Q

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[OK] Instalador creado exitosamente!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Ubicación: dist\CPOS-Hub-$Version-Setup.exe" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Características del instalador:" -ForegroundColor White
    Write-Host "  - Instala en: C:\Program Files\ERPlora Hub" -ForegroundColor Gray
    Write-Host "  - Acceso directo en Menú Inicio" -ForegroundColor Gray
    Write-Host "  - Opción de acceso directo en Escritorio" -ForegroundColor Gray
    Write-Host "  - Autostart con Windows (opcional)" -ForegroundColor Gray
    Write-Host "  - Desinstalador incluido" -ForegroundColor Gray
    Write-Host ""
}
else {
    Write-Host "[ERROR] Error al compilar el instalador" -ForegroundColor Red
    exit 1
}
