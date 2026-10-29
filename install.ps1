# AniNest MCP server - one-click installer for Windows.
#
#   .\install.ps1                 install into %LOCALAPPDATA%\aninest-mcp\venv
#   .\install.ps1 -Upgrade        re-install / upgrade an existing install
#   .\install.ps1 -Mirror <url>   use a PyPI mirror (e.g. Tsinghua) for dependencies
#   .\install.ps1 -WriteClaudeConfig
#                                 also write the Claude Desktop config file (backup kept)
#   .\install.ps1 -MemoryDb <p>   pre-fill ANINEST_MEMORY_DB in the printed config
#
# Nothing is installed system-wide: the server lives in its own venv under your
# user profile, and the script only prints (or, with -WriteClaudeConfig, edits)
# client configuration. Re-running is safe.

[CmdletBinding()]
param(
    [switch]$Upgrade,
    [string]$Mirror = "",
    [switch]$WriteClaudeConfig,
    [string]$MemoryDb = "",
    [string]$ArenaUrl = "http://127.0.0.1:6191"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }
function Fail($text) { Write-Host "`n[x] $text" -ForegroundColor Red; exit 1 }

Say "== AniNest MCP server installer ==" "Cyan"
Say ""

# ---------------------------------------------------------------- 1. Python ---
$candidates = @(
    @{ Exe = "py";     Args = @("-3", "-c") },
    @{ Exe = "python"; Args = @("-c") },
    @{ Exe = "python3"; Args = @("-c") }
)

$python = $null
$pythonVersion = $null
foreach ($c in $candidates) {
    $exe = Get-Command $c.Exe -ErrorAction SilentlyContinue
    if (-not $exe) { continue }
    try {
        $raw = & $c.Exe @($c.Args) "import sys;print('%d.%d.%d' % sys.version_info[:3])" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $raw) { continue }
        $parts = "$raw".Trim().Split(".")
        if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 10)) { continue }
        $python = @{ Exe = $c.Exe; Args = $c.Args }
        $pythonVersion = "$raw".Trim()
        break
    } catch { continue }
}

if (-not $python) {
    Fail @"
Python 3.10 or newer was not found on PATH.

Install it from https://www.python.org/downloads/windows/ (tick
"Add python.exe to PATH" in the installer), then run this script again.
"@
}
Say "[ok] Python $pythonVersion  ($($python.Exe))" "Green"

# ------------------------------------------------------------- 2. Install ---
$root = Join-Path $env:LOCALAPPDATA "aninest-mcp"
$venv = Join-Path $root "venv"
$venvPython = Join-Path $venv "Scripts\python.exe"
$exe = Join-Path $venv "Scripts\aninest-mcp.exe"

if ((Test-Path $exe) -and -not $Upgrade) {
    Say "[ok] Already installed: $exe" "Green"
    Say "     Re-run with -Upgrade to refresh it."
} else {
    if (-not (Test-Path $venvPython)) {
        Say "[..] Creating isolated environment: $venv"
        # `py` needs its launcher flag; `python`/`python3` take none.
        $venvPrefix = @()
        if ($python.Exe -eq "py") { $venvPrefix = @("-3") }
        & $python.Exe @venvPrefix "-m" "venv" $venv
        if ($LASTEXITCODE -ne 0) { Fail "Could not create a virtual environment at $venv" }
    }

    $pipArgs = @("-m", "pip", "install", "--disable-pip-version-check", "--upgrade")
    $thisScript = $PSCommandPath
    $repoDir = Split-Path -Parent $thisScript
    if (Test-Path (Join-Path $repoDir "pyproject.toml")) {
        $source = $repoDir   # running from a clone: install that tree
        Say "[..] Installing from this folder: $source"
    } else {
        $source = "git+https://github.com/moriruruka/aninest-mcp.git"
        Say "[..] Installing from $source"
    }
    if ($Mirror) {
        Say "     using mirror $Mirror"
        $pipArgs += @("-i", $Mirror)
    }
    $pipArgs += $source

    & $venvPython @pipArgs
    if ($LASTEXITCODE -ne 0) {
        Fail @"
pip install failed.

Most common causes, in order:
  1. No network / a proxy is required  -> retry with  -Mirror https://pypi.tuna.tsinghua.edu.cn/simple
  2. git is missing                    -> install Git for Windows, or clone the repo and run this script inside it
  3. Behind a corporate proxy          -> set HTTPS_PROXY, then retry
"@
    }
    Say "[ok] Installed: $exe" "Green"
}

# ------------------------------------------------------------ 3. Smoke test ---
Say "[..] Checking that the server starts and answers MCP handshake"
# The server logs to stderr; with $ErrorActionPreference=Stop Windows PowerShell
# would treat those lines as fatal, so relax it just for this call and keep the exit code.
$previousEap = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$probeRaw = & $venvPython -c @"
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    p = StdioServerParameters(command=sys.argv[1], args=[])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            tools = (await s.list_tools()).tools
            print('%s %s protocol=%s tools=%d' % (
                init.serverInfo.name, init.serverInfo.version,
                init.protocolVersion, len(tools)))

asyncio.run(main())
"@ $exe 2>&1
$probeExit = $LASTEXITCODE
$ErrorActionPreference = $previousEap
$probe = ($probeRaw | Where-Object { "$_" -match 'protocol=' }) -join ''
if ($probeExit -ne 0 -or -not $probe) {
    Fail "The server did not answer the MCP handshake:`n$($probeRaw -join "`n")"
}
Say "[ok] $("$probe".Trim())" "Green"

# ------------------------------------------------------------- 4. Config ---
$envBlock = [ordered]@{ ANINEST_ARENA_URL = $ArenaUrl }
if ($MemoryDb) { $envBlock["ANINEST_MEMORY_DB"] = $MemoryDb }

$claudeConfig = [ordered]@{
    mcpServers = [ordered]@{
        aninest = [ordered]@{
            command = $exe
            env     = $envBlock
        }
    }
}
$claudeJson = $claudeConfig | ConvertTo-Json -Depth 6

Say ""
Say "== Done. Point your MCP client at this command ==" "Cyan"
Say "   $exe"
Say ""
Say "Claude Desktop -> %APPDATA%\Claude\claude_desktop_config.json" "Cyan"
Say $claudeJson
Say ""
Say "DSH -> cordis.patch.yml, in the dsh-mcp-client entry:" "Cyan"
Say @"
    - id: mcp-client
      config:
        servers:
          - serverName: aninest
            transport:
              type: stdio
              command: '$exe'
              args: []
"@

if ($WriteClaudeConfig) {
    $configPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    $dir = Split-Path -Parent $configPath
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    if (Test-Path $configPath) {
        $backup = "$configPath.bak-$(Get-Date -Format yyyyMMdd-HHmmss)"
        Copy-Item -LiteralPath $configPath -Destination $backup
        Say "`n[ok] Existing config backed up to $backup" "Green"
        $existing = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $existing.mcpServers) {
            $existing | Add-Member -NotePropertyName mcpServers -NotePropertyValue ([pscustomobject]@{}) -Force
        }
        $existing.mcpServers | Add-Member -NotePropertyName aninest -NotePropertyValue $claudeConfig.mcpServers.aninest -Force
        $merged = $existing | ConvertTo-Json -Depth 8
    } else {
        $merged = $claudeJson
    }
    [System.IO.File]::WriteAllText($configPath, $merged, (New-Object System.Text.UTF8Encoding($false)))
    Say "[ok] Claude Desktop config written: $configPath" "Green"
    Say "     Restart Claude Desktop to pick it up."
} else {
    Say "`nTip: add -WriteClaudeConfig to write that file for you (a backup is kept)."
}
