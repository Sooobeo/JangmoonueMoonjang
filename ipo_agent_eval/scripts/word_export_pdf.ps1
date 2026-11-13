param([Parameter(Mandatory=$true)][string]$InputPath,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference = 'Stop'
$word = $null
$document = $null
try {
  $word = New-Object -ComObject Word.Application
  $word.Visible = $false
  $word.DisplayAlerts = 0
  $document = $word.Documents.Open($InputPath, $false, $true, $false)
  $document.Fields.Update() | Out-Null
  $document.ExportAsFixedFormat($OutputPath, 17)
  $document.Close(0)
  $document = $null
  $word.Quit()
  [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null
  $word = $null
  Write-Output 'Word PDF export completed'
} finally {
  if ($null -ne $document) { $document.Close(0) }
  if ($null -ne $word) { $word.Quit(); [System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($word) | Out-Null }
}
