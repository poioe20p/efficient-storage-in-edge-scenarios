param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$LatexmkArgs
)

# MiKTeX sometimes scans PATH entries as directories. If PATH accidentally contains
# an executable path (e.g., C:\Users\you\ffmpeg.exe), MiKTeX can fail before
# producing a TeX log. Filter those entries out for this invocation.
$pathParts = ($env:Path -split ';') | Where-Object { $_ -and $_.Trim() -ne '' }
$invalidParts = $pathParts | Where-Object { $_ -match '(?i)\.exe\\?$' }
if ($invalidParts.Count -gt 0) {
  Write-Host "latexmk_wrapper: removing invalid PATH entries (must be directories):"
  $invalidParts | ForEach-Object { Write-Host "  $_" }
}
$env:Path = (
  $pathParts |
    Where-Object { $_ -notmatch '(?i)\.exe\\?$' } |
    Select-Object -Unique
) -join ';'

# latexmk requires Perl, which is not installed. Fall back to direct pdflatex+biber cycle.
# Extract the base file name (without .tex extension) from arguments.
$baseName = "main"
foreach ($arg in $LatexmkArgs) {
  if ($arg -notmatch '^-') {
    $baseName = $arg -replace '\.tex$', ''
    break
  }
}

Write-Host "latexmk_wrapper: Perl not found -- using pdflatex + biber directly"
Write-Host "latexmk_wrapper: building '$baseName.pdf'"

$pdflatexCmd = "pdflatex -interaction=nonstopmode -synctex=1 '$baseName.tex'"

# Pass 1: generate .aux, .bcf, .toc, etc.
Write-Host "=== pdflatex pass 1 ==="
Invoke-Expression $pdflatexCmd | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "ERROR: pdflatex pass 1 failed (exit code $LASTEXITCODE)"
  exit $LASTEXITCODE
}

# Biber: process bibliography
Write-Host "=== biber ==="
& biber "$baseName"
if ($LASTEXITCODE -ne 0) {
  Write-Host "ERROR: biber failed (exit code $LASTEXITCODE)"
  exit $LASTEXITCODE
}

# Pass 2: resolve citations and cross-references
Write-Host "=== pdflatex pass 2 ==="
Invoke-Expression $pdflatexCmd | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "ERROR: pdflatex pass 2 failed (exit code $LASTEXITCODE)"
  exit $LASTEXITCODE
}

# Pass 3: resolve all remaining cross-references
Write-Host "=== pdflatex pass 3 ==="
Invoke-Expression $pdflatexCmd | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "ERROR: pdflatex pass 3 failed (exit code $LASTEXITCODE)"
  exit $LASTEXITCODE
}

Write-Host "latexmk_wrapper: SUCCESS -- '$baseName.pdf' produced"
exit 0
