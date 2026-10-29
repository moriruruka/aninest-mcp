#!/usr/bin/env bash
# AniNest MCP server - installer for macOS / Linux.
#
#   ./install.sh                      install into ~/.local/share/aninest-mcp/venv
#   ./install.sh --upgrade            re-install / upgrade
#   ./install.sh --mirror <url>       use a PyPI mirror for dependencies
#   ./install.sh --write-claude       also write/merge the Claude Desktop config
#   ./install.sh --memory-db <path>   pre-fill ANINEST_MEMORY_DB in the printed config
#
# Nothing is installed system-wide: the server lives in its own venv under your
# home directory, and the script only prints (or, with --write-claude, edits)
# client configuration. Re-running is safe.

set -euo pipefail

UPGRADE=0
MIRROR=""
WRITE_CLAUDE=0
MEMORY_DB=""
ARENA_URL="${ANINEST_ARENA_URL:-http://127.0.0.1:6191}"

while [ $# -gt 0 ]; do
  case "$1" in
    --upgrade) UPGRADE=1; shift ;;
    --mirror) MIRROR="${2:-}"; shift 2 ;;
    --write-claude) WRITE_CLAUDE=1; shift ;;
    --memory-db) MEMORY_DB="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "[x] unknown option: $1" >&2; exit 1 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
ok()   { printf '\033[32m[ok] %s\033[0m\n' "$*"; }
step() { printf '[..] %s\n' "$*"; }
fail() { printf '\n\033[31m[x] %s\033[0m\n' "$*" >&2; exit 1; }

say "== AniNest MCP server installer =="
echo

# ---------------------------------------------------------------- 1. Python ---
PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)' 2>/dev/null; then
      PY="$candidate"
      break
    fi
  fi
done
[ -n "$PY" ] || fail "Python 3.10 or newer was not found on PATH.
Install it (macOS: 'brew install python', Debian/Ubuntu: 'sudo apt install python3 python3-venv'), then rerun."
ok "Python $("$PY" -c 'import sys;print("%d.%d.%d" % sys.version_info[:3])')  ($PY)"

# ------------------------------------------------------------- 2. Install ---
ROOT="${XDG_DATA_HOME:-$HOME/.local/share}/aninest-mcp"
VENV="$ROOT/venv"
VENV_PY="$VENV/bin/python"
EXE="$VENV/bin/aninest-mcp"

if [ -x "$EXE" ] && [ "$UPGRADE" -eq 0 ]; then
  ok "Already installed: $EXE"
  say "     Re-run with --upgrade to refresh it."
else
  if [ ! -x "$VENV_PY" ]; then
    step "Creating isolated environment: $VENV"
    "$PY" -m venv "$VENV" || fail "Could not create a virtual environment (Debian/Ubuntu need python3-venv)."
  fi

  HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  if [ -f "$HERE/pyproject.toml" ]; then
    SOURCE="$HERE"
    step "Installing from this folder: $SOURCE"
  else
    SOURCE="git+https://github.com/moriruruka/aninest-mcp.git"
    step "Installing from $SOURCE"
  fi

  PIP_ARGS=(-m pip install --disable-pip-version-check --upgrade)
  if [ -n "$MIRROR" ]; then
    step "using mirror $MIRROR"
    PIP_ARGS+=(-i "$MIRROR")
  fi
  "$VENV_PY" "${PIP_ARGS[@]}" "$SOURCE" || fail "pip install failed.
Most common causes: no network (use --mirror), git missing, or an HTTP(S)_PROXY requirement."
  ok "Installed: $EXE"
fi

# ------------------------------------------------------------ 3. Smoke test ---
step "Checking that the server starts and answers MCP handshake"
PROBE="$("$VENV_PY" - "$EXE" <<'PY'
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    p = StdioServerParameters(command=sys.argv[1], args=[])
    async with stdio_client(p) as (r, w):
        async with ClientSession(r, w) as s:
            init = await s.initialize()
            tools = (await s.list_tools()).tools
            print("%s %s protocol=%s tools=%d" % (
                init.serverInfo.name, init.serverInfo.version,
                init.protocolVersion, len(tools)))

asyncio.run(main())
PY
)"
ok "$PROBE"

# ------------------------------------------------------------- 4. Config ---
ENV_JSON="\"ANINEST_ARENA_URL\": \"$ARENA_URL\""
[ -n "$MEMORY_DB" ] && ENV_JSON="$ENV_JSON, \"ANINEST_MEMORY_DB\": \"$MEMORY_DB\""

say ""
say "== Done. Point your MCP client at this command =="
say "   $EXE"
echo
say "Claude Desktop ->"
if [ "$(uname)" = "Darwin" ]; then
  say "   ~/Library/Application Support/Claude/claude_desktop_config.json"
else
  say "   ~/.config/Claude/claude_desktop_config.json"
fi
say "{ \"mcpServers\": { \"aninest\": { \"command\": \"$EXE\", \"env\": { $ENV_JSON } } } }"
echo
say "DSH -> cordis.patch.yml, in the dsh-mcp-client entry:"
say "    - id: mcp-client
      config:
        servers:
          - serverName: aninest
            transport:
              type: stdio
              command: '$EXE'
              args: []"

if [ "$WRITE_CLAUDE" -eq 1 ]; then
  if [ "$(uname)" = "Darwin" ]; then
    CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
  else
    CFG="${XDG_CONFIG_HOME:-$HOME/.config}/Claude/claude_desktop_config.json"
  fi
  mkdir -p "$(dirname "$CFG")"
  [ -f "$CFG" ] && cp "$CFG" "$CFG.bak-$(date +%Y%m%d-%H%M%S)" && ok "Existing config backed up"
  "$VENV_PY" - "$CFG" "$EXE" "$ARENA_URL" "$MEMORY_DB" <<'PY'
import json, sys
from pathlib import Path

cfg, exe, arena, db = sys.argv[1:5]
path = Path(cfg)
data = {}
if path.exists():
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
servers = data.setdefault("mcpServers", {})
env = {"ANINEST_ARENA_URL": arena}
if db:
    env["ANINEST_MEMORY_DB"] = db
servers["aninest"] = {"command": exe, "env": env}
path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print("wrote", path)
PY
  ok "Claude Desktop config written: $CFG"
  say "     Restart Claude Desktop to pick it up."
else
  say ""
  say "Tip: add --write-claude to write that file for you (a backup is kept)."
fi
