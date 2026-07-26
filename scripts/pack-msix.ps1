<#
.SYNOPSIS
  Empaqueta el build Windows del Bridge como MSIX para Microsoft Store (ADR-0136 · hub#120).

.DESCRIPTION
  Paso POST-BUILD puro: no toca cómo compila Cargo. Un solo sabor (-Flavor):

    bridge (default) — ERPlora Bridge (apps/bridge, binario erplora-bridge). Requiere
           `cargo build --release -p erplora-bridge`. Sin front que stagear.

  1. Stage: exe + Assets/ (iconos que referencia el manifest).
  2. Patch: tokens __MSIX_*__ del Package.appxmanifest con la identidad real
     de Partner Center (Identity Name propio; el Publisher es el de la cuenta).
  3. Pack: `winapp pack` (CLI oficial: winget install microsoft.winappcli).
     SIN -Cert ⇒ MSIX sin firmar, que es lo que exige la submission (la Store firma).

.EXAMPLE
  pwsh scripts/pack-msix.ps1 -Flavor bridge -Version 0.2.0 `
    -IdentityName "12345Erplora.ERPloraBridge" -Publisher "CN=xxxx-..." `
    -PublisherDisplay "Erplora" -OutDir dist-msix

.NOTES
  Solo Windows (winapp CLI). En CI corre en el leg windows de bridge-release.yml.
  Para probar la INSTALACIÓN local (no la submission) añade -Cert con un devcert:
  `winapp cert generate` + `winapp cert install`.
#>
param(
  [Parameter(Mandatory = $true)][string]$Version,
  [Parameter(Mandatory = $true)][string]$IdentityName,
  [Parameter(Mandatory = $true)][string]$Publisher,
  [Parameter(Mandatory = $true)][string]$PublisherDisplay,
  [ValidateSet("bridge")][string]$Flavor = "bridge",
  [string]$OutDir = "dist-msix",
  [string]$Cert = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot   # hub/

# --- Presets por sabor ---
$presets = @{
  bridge = @{
    ExeCandidates = @("$repoRoot/target/release/erplora-bridge.exe")
    ExeName       = "erplora-bridge.exe"
    Manifest      = "$repoRoot/apps/bridge/msix/Package.appxmanifest"
    AssetsDir     = "$repoRoot/apps/bridge/msix/Assets"
    OutName       = "erplora-bridge.msix"
  }
}
$p = $presets[$Flavor]

# --- Versión: la Store exige 4 partes con revisión 0 (v1.2.3 → 1.2.3.0). ---
$v = $Version.TrimStart("v")
if ($v -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') { throw "Versión inválida: $Version" }
if ($v -match '^\d+\.\d+\.\d+$') { $v = "$v.0" }

# --- Localizar el exe de release. ---
$exe = $p.ExeCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) { throw "No hay exe en target/release/ para el sabor '$Flavor' — corre antes su build." }

# --- Stage: mismo layout que instala NSIS ($INSTDIR): exe + Assets/. ---
$stage = "$repoRoot/target/msix-stage-$Flavor"
if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
New-Item -ItemType Directory -Path "$stage/Assets" | Out-Null
Copy-Item $exe "$stage/$($p.ExeName)"

foreach ($i in "Square44x44Logo.png", "Square150x150Logo.png", "StoreLogo.png") {
  Copy-Item "$($p.AssetsDir)/$i" "$stage/Assets/$i"
}

# --- Manifest: patch de tokens → stage. ---
$manifest = Get-Content $p.Manifest -Raw
$manifest = $manifest.
  Replace("__MSIX_IDENTITY_NAME__", $IdentityName).
  Replace("__MSIX_PUBLISHER__", $Publisher).
  Replace("__MSIX_PUBLISHER_DISPLAY__", $PublisherDisplay).
  Replace("__MSIX_VERSION__", $v)
Set-Content "$stage/Package.appxmanifest" $manifest -Encoding utf8

# --- Pack: winapp lee el Package.appxmanifest del cwd (lo copia al target), así que corremos
# desde el propio stage. Sin --cert = sin firmar (submission a la Store). ---
$out = Join-Path $repoRoot $OutDir
New-Item -ItemType Directory -Path $out -Force | Out-Null
Push-Location $stage
try {
  $packArgs = @("pack", $stage)
  if ($Cert) { $packArgs += @("--cert", $Cert) }
  winapp @packArgs
  if ($LASTEXITCODE -ne 0) { throw "winapp pack falló ($LASTEXITCODE)" }
  $msix = Get-ChildItem -Path $stage -Filter "*.msix" | Select-Object -First 1
  if (-not $msix) { $msix = Get-ChildItem -Path . -Filter "*.msix" | Select-Object -First 1 }
  if (-not $msix) { throw "winapp pack no produjo ningún .msix" }
  Copy-Item $msix.FullName "$out/$($p.OutName)" -Force
}
finally { Pop-Location }

Write-Host "MSIX listo: $out/$($p.OutName) (sabor $Flavor, versión $v, sin firmar — la Store firma)"
