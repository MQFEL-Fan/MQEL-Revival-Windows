# Erzeugt DTO-Stub-JSONs aus den Original-Contracts (Toolbox-Assemblies).
# Gebrauch:
#   powershell -ExecutionPolicy Bypass -File server/gen_stub.ps1
# Liest Typen per Reflection, füllt rekursiv typkorrekte Defaults und
# serialisiert mit dem ORIGINALEN Newtonsoft.Json aus der Toolbox.
# Handgesetzte Werte (IDs, Namen) unten in $Seed s. Set-Seed.

param(
    [string]$ToolboxDir = "$env:TEMP\opencode\mqel-toolbox",
    [string]$OutDir = "server/stubs"
)

$ErrorActionPreference = 'Stop'

[void][System.Reflection.Assembly]::LoadFrom("$ToolboxDir\MongoDB.Bson.dll")
[void][System.Reflection.Assembly]::LoadFrom("$ToolboxDir\HyperQuest.GameServer.Contracts.dll")
$jsonAsm = [System.Reflection.Assembly]::LoadFrom("$ToolboxDir\Newtonsoft.Json.dll")
$JsonConvert = $jsonAsm.GetType('Newtonsoft.Json.JsonConvert')

$MaxDepth = 6

function New-StubValue {
    param([type]$T, [int]$Depth)

    if ($T.IsEnum) { return 0 }
    if ($T -eq [string]) { return '' }
    if ($T -eq [bool]) { return $false }
    if ($T -eq [char]) { return '' }
    if ($T -eq [datetime]) { return '' }  # Drahtformat MinValue, s. Client-Capture (CreationDate:"")
    if ($T -eq [guid]) { return '00000000-0000-0000-0000-000000000000' }
    if ($T.FullName -eq 'MongoDB.Bson.ObjectId') { return '000000000000000000000000' }  # Format-TODO, s. docs
    if ($T.IsPrimitive -or $T -eq [decimal]) {
        if ($T -eq [double] -or $T -eq [single] -or $T -eq [decimal]) { return [double]0 }
        return 0
    }
    $under = [Nullable]::GetUnderlyingType($T)
    if ($under) { return $null }
    if ($T.IsArray) { return ,@() }  # Komma: leeres Array als EIN Objekt zurückgeben (sonst kollabiert es zu $null)
    if ($T -eq [byte[]]) { return $null }
    if ($T.IsGenericType) {
        $gdef = $T.GetGenericTypeDefinition()
        if ($gdef -eq [System.Collections.Generic.List`1] -or
            $gdef -eq [System.Collections.Generic.IList`1] -or
            $gdef -eq [System.Collections.Generic.IEnumerable`1] -or
            $gdef -eq [System.Collections.Generic.HashSet`1]) { return ,@() }
        if ($gdef -eq [System.Collections.Generic.Dictionary`2]) { return @{} }
    }
    if ($T.IsInterface -and $T.Name -match 'Dictionary') { return @{} }
    if ($T.IsInterface -and ($T.Name -match 'List|Enumerable|Collection')) { return @() }
    if ($Depth -ge $MaxDepth) { return $null }
    if ($T.IsClass) {
        if ($T.GetConstructor([type[]]@()) -eq $null) { return $null }
        $o = [ordered]@{}
        foreach ($p in $T.GetProperties()) {
            if ($p.GetIndexParameters().Count -gt 0) { continue }
            if ($p.GetGetMethod() -eq $null) { continue }
            $o[$p.Name] = New-StubValue $p.PropertyType ($Depth + 1)
        }
        return $o
    }
    if ($T.IsValueType) {
        # Unbekannte Structs: Default-Instanz durch Original-Json.NET jagen.
        try {
            $inst = [Activator]::CreateInstance($T)
            $json = $JsonConvert::SerializeObject($inst)
            return ($json | ConvertFrom-Json)
        } catch { return $null }
    }
    return $null
}

function Write-Stub {
    param([string]$TypeName, [string]$File, [hashtable]$Seed = @{})
    $asm = [AppDomain]::CurrentDomain.GetAssemblies() |
        Where-Object { $_.GetType($TypeName) } | Select-Object -First 1
    $t = $asm.GetType($TypeName)
    if (-not $t) { throw "Typ nicht gefunden: $TypeName" }
    $stub = New-StubValue $t 0
    foreach ($k in $Seed.Keys) { $stub[$k] = $Seed[$k] }
    $mi = $JsonConvert.GetMethod('SerializeObject', [type[]]@([object]))
    $json = $mi.Invoke($null, [object[]]@($stub))
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    [System.IO.File]::WriteAllText("$OutDir\$File", $json, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "geschrieben: $OutDir\$File ($($json.Length) Zeichen)"
}

Write-Stub 'HyperQuest.GameServer.Contracts.AccountInformation' 'account-information.json' @{
    AccountId   = 1
    DisplayName = 'Reviver'
    CountryCode = 'DE'
}
