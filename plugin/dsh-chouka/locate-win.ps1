# dsh-chouka Windows 定位助手：WinRT Windows.Devices.Geolocation（WGS-84）
# 运行：powershell.exe -NoProfile -ExecutionPolicy Bypass -File locate-win.ps1
# 输出：{"lat":..,"lng":..,"accuracy":..} 或 {"error":".."}
# 前置：设置 → 隐私和安全性 → 位置 → 「位置服务」开 + 「允许桌面应用访问位置」开

$ErrorActionPreference = 'Stop'
$inv = [System.Globalization.CultureInfo]::InvariantCulture

try {
  Add-Type -AssemblyName System.Runtime.WindowsRuntime
  $null = [Windows.Devices.Geolocation.Geolocator,Windows.Devices.Geolocation,ContentType=WindowsRuntime]

  # IAsyncOperation<T> → Task<T>（PS 5.1 的经典桥接）
  $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]

  $locator = New-Object Windows.Devices.Geolocation.Geolocator
  $locator.DesiredAccuracyInMeters = 100
  $op = $locator.GetGeopositionAsync()
  $asTask = $asTaskGeneric.MakeGenericMethod([Windows.Devices.Geolocation.Geoposition])
  $netTask = $asTask.Invoke($null, @($op))
  if (-not $netTask.Wait(25000)) {
    Write-Output '{"error":"timeout"}'
    exit 2
  }
  $pos = $netTask.Result
  $p = $pos.Coordinate.Point.Position
  Write-Output ('{"lat":' + $p.Latitude.ToString('R', $inv) + ',"lng":' + $p.Longitude.ToString('R', $inv) + ',"accuracy":' + [Math]::Round($pos.Coordinate.Accuracy) + '}')
  exit 0
}
catch {
  $msg = $_.Exception.Message -replace '"', "'"
  if ($msg -match 'AccessDenied|0x80070005|访问被拒绝|拒绝访问') {
    Write-Output '{"error":"位置访问被拒绝：设置 → 隐私和安全性 → 位置，打开「位置服务」和「允许桌面应用访问位置」后重试","code":1}'
  }
  else {
    Write-Output ('{"error":"' + $msg + '"}')
  }
  exit 1
}
