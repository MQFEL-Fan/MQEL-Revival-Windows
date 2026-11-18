# Erzeugt einen DTO-Katalog aller öffentlichen Typen in den Contract-Assemblies:
#   Klassen mit Basistyp + Properties (Name + Typname),
#   Enums mit Namen + Werten.
# Gebrauch:
#   powershell -NoProfile -ExecutionPolicy Bypass -File server/dto_catalog.ps1
# Ergebnis: docs/analysis/dto-catalog.txt

param(
    [string]$ToolboxDir = "$env:TEMP\opencode\mqel-toolbox",
    [string]$OutFile = "docs/analysis/dto-catalog.txt"
)

$ErrorActionPreference = 'Stop'

$dlls = @('MongoDB.Bson.dll', 'Contracts.Common.Enum.dll', 'Contracts.Common.dll',
    'HyperQuest.GameServer.Contracts.Enum.dll', 'HyperQuest.GameServer.Contracts.dll',
    'HyperQuest.GameServer.Entities.dll')
foreach ($d in $dlls) {
    $p = Join-Path $ToolboxDir $d
    if (Test-Path $p) { [void][System.Reflection.Assembly]::LoadFrom($p) }
}

function ShortName([type]$t) {
    if ($t -eq [string]) { return 'string' }
    if ($t -eq [int]) { return 'int' }
    if ($t -eq [long]) { return 'long' }
    if ($t -eq [bool]) { return 'bool' }
    if ($t -eq [double]) { return 'double' }
    if ($t -eq [float]) { return 'float' }
    if ($t -eq [decimal]) { return 'decimal' }
    if ($t -eq [datetime]) { return 'DateTime' }
    if ($t -eq [byte]) { return 'byte' }
    if ($t -eq [object]) { return 'object' }
    if ($t.IsArray) { return (ShortName $t.GetElementType()) + '[]' }
    if ($t.IsGenericType) {
        $g = $t.GetGenericTypeDefinition()
        $n = $g.FullName
        if ($n -like 'System.Nullable*') { return (ShortName $t.GetGenericArguments()[0]) + '?' }
        $args = ($t.GetGenericArguments() | ForEach-Object { ShortName $_ }) -join ','
        $simple = $g.Name.Substring(0, $g.Name.IndexOf('`'))
        return "$simple<$args>"
    }
    if ($t.IsGenericParameter) { return $t.Name }
    return $t.FullName
}

$sb = New-Object System.Text.StringBuilder
$asms = [AppDomain]::CurrentDomain.GetAssemblies() | Where-Object {
    $_.FullName -like 'HyperQuest.GameServer.Contracts*' -or $_.FullName -like 'Contracts.Common*'
}
foreach ($a in ($asms | Sort-Object FullName)) {
    [void]$sb.AppendLine("### ASSEMBLY " + $a.GetName().Name)
    $types = $a.GetTypes() | Where-Object { $_.IsPublic -and -not $_.IsInterface } | Sort-Object FullName
    foreach ($t in $types) {
        if ($t.IsEnum) {
            $vals = [Enum]::GetValues($t) | ForEach-Object {
                "$_=" + [int]$_
            }
            [void]$sb.AppendLine("ENUM " + $t.FullName + " : " + ($vals -join ' '))
        } else {
            $base = if ($t.BaseType) { ShortName $t.BaseType } else { '' }
            [void]$sb.AppendLine("CLASS " + $t.FullName + " : " + $base)
            foreach ($p in ($t.GetProperties() | Sort-Object Name)) {
                if ($p.GetIndexParameters().Count -gt 0) { continue }
                [void]$sb.AppendLine("    " + (ShortName $p.PropertyType) + " " + $p.Name)
            }
        }
    }
}
New-Item -ItemType Directory -Force -Path (Split-Path $OutFile) | Out-Null
[System.IO.File]::WriteAllText($OutFile, $sb.ToString(), (New-Object System.Text.UTF8Encoding $false))
Write-Host ("geschrieben: " + $OutFile)
