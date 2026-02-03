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

& latexmk @LatexmkArgs
exit $LASTEXITCODE
