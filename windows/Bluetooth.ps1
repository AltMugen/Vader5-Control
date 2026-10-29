[CmdletBinding()]
param(
    [ValidateSet('Scan','Pair')][string]$Action = 'Scan',
    [string]$DeviceId
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Devices.Bluetooth.BluetoothLEDevice,Windows.Devices.Bluetooth,ContentType=WindowsRuntime]
$null = [Windows.Devices.Enumeration.DeviceInformation,Windows.Devices.Enumeration,ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.IsGenericMethodDefinition -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1
function Await($Operation, [Type]$ResultType) {
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    if (!$task.Wait(20000)) { throw 'Bluetooth operation timed out' }
    return $task.GetAwaiter().GetResult()
}
if ($Action -eq 'Pair') {
    if (!$DeviceId) { throw 'Device ID required' }
    $device = Await ([Windows.Devices.Enumeration.DeviceInformation]::CreateFromIdAsync($DeviceId)) ([Windows.Devices.Enumeration.DeviceInformation])
    if ($device.Name.Replace(' ','').ToLowerInvariant() -ne 'flydigivader5pro') { throw 'Unexpected Bluetooth device' }
    if (!$device.Pairing.IsPaired) {
        $result = Await ($device.Pairing.PairAsync()) ([Windows.Devices.Enumeration.DevicePairingResult])
        if ($result.Status.ToString() -notin @('Paired','AlreadyPaired')) { throw ('Pairing: ' + $result.Status) }
    }
    Write-Output '{}'
    exit
}
$found = @{}
foreach ($paired in @($false,$true)) {
    $selector = [Windows.Devices.Bluetooth.BluetoothLEDevice]::GetDeviceSelectorFromPairingState($paired)
    $properties = [string[]]@('System.Devices.Aep.DeviceAddress')
    $devices = Await ([Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync(
        $selector,$properties,[Windows.Devices.Enumeration.DeviceInformationKind]::AssociationEndpoint
    )) ([Windows.Devices.Enumeration.DeviceInformationCollection])
    foreach ($device in $devices) {
        if ($device.Name.Replace(' ','').ToLowerInvariant() -ne 'flydigivader5pro') { continue }
        $address = [string]$device.Properties['System.Devices.Aep.DeviceAddress']
        if ($address -notmatch '^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$') { continue }
        $found[$device.Id] = @{ name=$device.Name; address=$address; adapter=''; id=$device.Id }
    }
}
ConvertTo-Json -InputObject @($found.Values) -Depth 3 -Compress
