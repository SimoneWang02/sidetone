# Starts the sidetone overlay window. The hub runs this with Windows PowerShell and
# talks to it over stdin/stdout (see Overlay.cs for the protocol). Nothing here uses the network.
$ErrorActionPreference = 'Stop'
try {
    $assemblies = 'PresentationFramework', 'PresentationCore', 'WindowsBase', 'System.Xaml', 'System.Web.Extensions',
                  'System.Windows.Forms', 'System.Drawing'
    Add-Type -AssemblyName $assemblies
    $source = Get-Content -Raw -Encoding UTF8 (Join-Path $PSScriptRoot 'Overlay.cs')
    Add-Type -TypeDefinition $source -ReferencedAssemblies $assemblies
    [ClaudeSpeaks.Overlay]::Run()
} catch {
    $message = (($_ | Out-String) -replace '\s+', ' ' -replace '["\\]', "'").Trim()
    [Console]::Out.WriteLine('{"type":"error","message":"' + $message + '"}')
    exit 1
}
