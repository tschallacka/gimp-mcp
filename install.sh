#!/usr/bin/env bash
# GIMP MCP -- control GIMP from an MCP client.
#
# Copyright (C) 2025 Maor <maor80-opensource@yahoo.com>
# Copyright (C) 2025 Tomer Konforty <tomer.konforty@arkhivist.io>
# Copyright (C) 2026 tschallacka <tschallacka@outlook.com>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.
#
# GIMP MCP installer.
#
#   curl -fsSL https://raw.githubusercontent.com/tschallacka/gimp-mcp/main/install.sh | bash
#
# Finds every GIMP 3.x user config directory on this machine, installs the MCP
# plugin into it, and offers to start the server automatically with GIMP.
#
# Flags:
#   --autostart / --no-autostart   set the startup behaviour without being asked
#   --yes                          accept defaults, never prompt
#   --uninstall                    remove the plugin from every config dir found
#   --source DIR                   install from a local checkout instead of GitHub
#   --port N                       socket port (default 9877)

set -euo pipefail

# Where the installer fetches the plugin when it is not run from a
# checkout. Point it elsewhere with GIMP_MCP_REPO_RAW, e.g. at a branch:
#   GIMP_MCP_REPO_RAW=https://raw.githubusercontent.com/you/gimp-mcp/dev
REPO_RAW="${GIMP_MCP_REPO_RAW:-https://raw.githubusercontent.com/tschallacka/gimp-mcp/main}"
PLUGIN_FILE="gimp-mcp-plugin.py"
SERVER_FILE="gimp_mcp_server.py"
REGISTER_FILE="tools/register_mcp.py"
# The MCP server is a script an agent launches, so it needs a home that is not
# a git checkout the user might move or delete.
SERVER_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/gimp-mcp"
PLUGIN_DIR_NAME="gimp-mcp-plugin"
CONFIG_NAME="mcp-server.json"

AUTOSTART=""
REGISTER=""
ASSUME_YES=0
UNINSTALL=0
SOURCE_DIR=""
PORT=9877

die()  { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
    # Reading $0 fails when the script arrives on stdin via curl | bash.
    cat <<'USAGE'
GIMP MCP installer

  curl -fsSL https://raw.githubusercontent.com/tschallacka/gimp-mcp/main/install.sh | bash

Finds every GIMP 3.x user config directory on this machine, installs the MCP
plugin into each, and offers to start the MCP server automatically with GIMP.

  --autostart / --no-autostart   set startup behaviour without being asked
  --register / --no-register     add the MCP server to your coding agents
  --yes                          accept defaults, never prompt
  --uninstall                    remove the plugin from every config dir found
  --source DIR                   install from a local checkout instead of GitHub
  --port N                       socket port (default 9877)

  GIMP_MCP_PYTHON=/path/to/python3   force the plug-in interpreter
USAGE
}

say()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

# When run as `curl ... | bash`, stdin is the script itself, so prompts have to
# read the terminal directly. If there is no terminal, fall back to defaults.
ask_yes_no() {
    local prompt="$1" default="$2" reply
    if [ "$ASSUME_YES" = "1" ]; then
        echo "$default"; return
    fi
    if [ ! -r /dev/tty ]; then
        echo "$default"; return
    fi
    local hint="[y/N]"
    [ "$default" = "true" ] && hint="[Y/n]"
    printf '%s %s ' "$prompt" "$hint" > /dev/tty
    read -r reply < /dev/tty || { echo "$default"; return; }
    case "$reply" in
        [yY]|[yY][eE][sS]) echo true ;;
        [nN]|[nN][oO])     echo false ;;
        *)                 echo "$default" ;;
    esac
}

while [ $# -gt 0 ]; do
    case "$1" in
        --autostart)    AUTOSTART=true ;;
        --no-autostart) AUTOSTART=false ;;
        --register)     REGISTER=true ;;
        --no-register)  REGISTER=false ;;
        --yes|-y)       ASSUME_YES=1 ;;
        --uninstall)    UNINSTALL=1 ;;
        --source)
            [ $# -ge 2 ] || die "--source needs a directory"
            SOURCE_DIR="$2"; shift ;;
        --port)
            [ $# -ge 2 ] || die "--port needs a number"
            PORT="$2"
            case "$PORT" in
                ''|*[!0-9]*) die "--port must be a number, got: $PORT" ;;
            esac
            [ "$PORT" -ge 1 ] && [ "$PORT" -le 65535 ] \
                || die "--port must be between 1 and 65535, got: $PORT"
            shift ;;
        -h|--help)      usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

# ---------------------------------------------------------------------------
# Locate GIMP config directories
#
# GIMP keeps a separate config dir per major.minor version and makes a new one
# on every minor upgrade, so 3.0 and 3.2 can both exist. Each packaging format
# puts that tree somewhere different.
# ---------------------------------------------------------------------------
find_gimp_dirs() {
    local bases=(
        "$HOME/.config/GIMP"
        "$HOME/snap/gimp/current/.config/GIMP"
        "$HOME/.var/app/org.gimp.GIMP/config/GIMP"
        "$HOME/Library/Application Support/GIMP"
    )
    [ -n "${APPDATA:-}" ] && bases+=("$APPDATA/GIMP")

    local base dir
    for base in "${bases[@]}"; do
        [ -d "$base" ] || continue
        for dir in "$base"/3.*; do
            [ -d "$dir" ] && printf '%s\n' "$dir"
        done
    done
}

mapfile -t GIMP_DIRS < <(find_gimp_dirs | sort -u)

if [ "${#GIMP_DIRS[@]}" -eq 0 ]; then
    die "No GIMP 3.x config directory found.

Looked in:
  ~/.config/GIMP/3.*                          (native)
  ~/snap/gimp/current/.config/GIMP/3.*        (Snap)
  ~/.var/app/org.gimp.GIMP/config/GIMP/3.*    (Flatpak)
  ~/Library/Application Support/GIMP/3.*      (macOS)
  \$APPDATA/GIMP/3.*                           (Windows)

Start GIMP once so it creates its config directory, then re-run this.
GIMP shows the exact path under Edit > Preferences > Folders > Plug-ins."
fi

say ""
say "GIMP MCP installer"
say "=================="
say ""
say "Found ${#GIMP_DIRS[@]} GIMP config director$([ "${#GIMP_DIRS[@]}" -eq 1 ] && echo y || echo ies):"
for d in "${GIMP_DIRS[@]}"; do say "  $d"; done
say ""

# Uninstall runs before the download section, so it needs its own fetcher.
fetch_companion_early() {
    local rel="$1" dest="$2" src_dir=""
    if [ -n "${BASH_SOURCE[0]:-}" ] && [ -r "${BASH_SOURCE[0]}" ]; then
        src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi
    if [ -n "$src_dir" ] && [ -f "$src_dir/$rel" ]; then
        cp "$src_dir/$rel" "$dest"
        return 0
    fi
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$REPO_RAW/$rel" -o "$dest" 2>/dev/null
    else
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
if [ "$UNINSTALL" = "1" ]; then
    for d in "${GIMP_DIRS[@]}"; do
        target="$d/plug-ins/$PLUGIN_DIR_NAME"
        if [ -d "$target" ]; then
            rm -rf "$target"
            ok "removed $target"
        else
            warn "not installed in $d"
        fi
        if [ -f "$d/$CONFIG_NAME" ]; then
            rm -f "$d/$CONFIG_NAME"
            ok "removed $d/$CONFIG_NAME"
        fi
    done
    reg="$(mktemp)"
    if fetch_companion_early "$REGISTER_FILE" "$reg"; then
        say ""
        say "Removing it from coding agents:"
        python3 "$reg" --remove || true
    fi
    rm -f "$reg"
    rm -rf "$SERVER_DIR"
    say ""
    say "Done. Restart GIMP to unload the plugin."
    exit 0
fi

# ---------------------------------------------------------------------------
# Obtain the plugin source
# ---------------------------------------------------------------------------
TMPDIR_INST="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_INST"' EXIT
SRC="$TMPDIR_INST/$PLUGIN_FILE"

if [ -n "$SOURCE_DIR" ]; then
    [ -f "$SOURCE_DIR/$PLUGIN_FILE" ] || die "$SOURCE_DIR/$PLUGIN_FILE not found"
    cp "$SOURCE_DIR/$PLUGIN_FILE" "$SRC"
    ok "using local $SOURCE_DIR/$PLUGIN_FILE"
elif [ -n "${BASH_SOURCE[0]:-}" ] && [ -r "${BASH_SOURCE[0]}" ] \
     && [ -f "$(dirname "${BASH_SOURCE[0]}")/$PLUGIN_FILE" ]; then
    # Only when this script is a real file next to the plugin, i.e. run from a
    # checkout. Piped from curl there is no script file: $0 is "bash" and
    # BASH_SOURCE is unset, so `dirname "$0"` would resolve to the *current
    # directory* and quietly install whatever gimp-mcp-plugin.py happened to be
    # sitting there instead of the version just downloaded.
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp "$script_dir/$PLUGIN_FILE" "$SRC"
    ok "using $script_dir/$PLUGIN_FILE"
else
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$REPO_RAW/$PLUGIN_FILE" -o "$SRC" \
            || die "download failed: $REPO_RAW/$PLUGIN_FILE"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$SRC" "$REPO_RAW/$PLUGIN_FILE" \
            || die "download failed: $REPO_RAW/$PLUGIN_FILE"
    else
        die "need curl or wget to download the plugin"
    fi
    ok "downloaded $PLUGIN_FILE"
fi

python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" "$SRC" \
    || die "the plugin file is not valid Python; refusing to install it"

# Fetch a companion file from the same place the plugin came from.
fetch_companion() {
    local rel="$1" dest="$2" src_dir=""
    if [ -n "$SOURCE_DIR" ]; then
        src_dir="$SOURCE_DIR"
    elif [ -n "${BASH_SOURCE[0]:-}" ] && [ -r "${BASH_SOURCE[0]}" ]; then
        src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    fi

    if [ -n "$src_dir" ] && [ -f "$src_dir/$rel" ]; then
        cp "$src_dir/$rel" "$dest"
        return 0
    fi
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$REPO_RAW/$rel" -o "$dest" 2>/dev/null
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$dest" "$REPO_RAW/$rel" 2>/dev/null
    else
        return 1
    fi
}

# ---------------------------------------------------------------------------
# Pin the interpreter.
#
# GIMP runs a .py plug-in through its shebang, so `#!/usr/bin/env python3`
# resolves against whatever PATH GIMP inherited. A python3 without PyGObject
# earlier on PATH -- common with nix, pyenv, conda or a virtualenv -- makes the
# plugin die at `import gi` during GIMP's startup scan, and GIMP reports
# nothing beyond a traceback on stderr that nobody sees. Writing an absolute
# path to an interpreter that actually has gi removes the dependency on PATH.
#
# The Gimp typelib itself is supplied by GIMP at plug-in runtime, so `import
# gi` succeeding is the whole test; requiring the Gimp namespace here would
# wrongly reject every valid interpreter.
# ---------------------------------------------------------------------------
find_python_with_gi() {
    local candidates=() c
    candidates+=("/usr/bin/python3")
    [ -n "${GIMP_MCP_PYTHON:-}" ] && candidates=("$GIMP_MCP_PYTHON" "${candidates[@]}")
    # `type -aP` lists every python3 on PATH. `command -v -a` is not valid
    # bash -- it exits 2 and prints a usage error -- so the PATH candidates were
    # silently never probed, which skipped exactly the nix/pyenv/conda setups
    # this whole block exists for.
    while IFS= read -r c; do
        [ -n "$c" ] && candidates+=("$c")
    done < <(type -aP python3 2>/dev/null || true)
    candidates+=("/usr/local/bin/python3" "/opt/homebrew/bin/python3")

    for c in "${candidates[@]}"; do
        [ -x "$c" ] || continue
        if "$c" -c "import gi" >/dev/null 2>&1; then
            printf '%s\n' "$c"
            return 0
        fi
    done
    return 1
}

PYBIN="$(find_python_with_gi || true)"
if [ -n "$PYBIN" ]; then
    ok "plug-in interpreter: $PYBIN"
    tmp_pinned="$TMPDIR_INST/pinned.py"
    {
        printf '#!%s\n' "$PYBIN"
        tail -n +2 "$SRC"
    } > "$tmp_pinned"
    mv "$tmp_pinned" "$SRC"
else
    warn "no python3 with PyGObject (import gi) found; leaving the shebang as"
    warn "  #!/usr/bin/env python3. If GIMP does not show Tools > MCP, install"
    warn "  PyGObject (Debian/Ubuntu: apt install python3-gi) and re-run this."
    warn "  You can also point the installer at one: GIMP_MCP_PYTHON=/path/to/python3"
fi

# ---------------------------------------------------------------------------
# Autostart choice
# ---------------------------------------------------------------------------
say ""
if [ -z "$AUTOSTART" ]; then
    say "The MCP server can start by itself whenever GIMP starts, so you do not"
    say "have to pick Tools > MCP > Start MCP Server by hand each time."
    AUTOSTART="$(ask_yes_no "Start the MCP server automatically with GIMP?" true)"
fi

if [ -z "$REGISTER" ]; then
    say ""
    say "The MCP server can also be added to the coding agents on this machine"
    say "(Claude Code, Claude Desktop, Codex, opencode, Cline), so they can drive"
    say "GIMP without you editing each one's config by hand. Existing entries are"
    say "left alone and every file is backed up first."
    REGISTER="$(ask_yes_no "Add it to your coding agents?" true)"
fi
say ""

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------
installed=0
for d in "${GIMP_DIRS[@]}"; do
    target="$d/plug-ins/$PLUGIN_DIR_NAME"
    mkdir -p "$target"
    cp "$SRC" "$target/$PLUGIN_FILE"
    chmod +x "$target/$PLUGIN_FILE"
    ok "installed into $target"

    cat > "$d/$CONFIG_NAME" <<JSON
{
  "autostart": $AUTOSTART,
  "port": $PORT,
  "host": "localhost"
}
JSON
    ok "wrote $d/$CONFIG_NAME (autostart: $AUTOSTART)"
    installed=$((installed + 1))
done

say ""
say "Installed into $installed GIMP config director$([ "$installed" -eq 1 ] && echo y || echo ies)."

# ---------------------------------------------------------------------------
# The MCP server, and telling agents about it
# ---------------------------------------------------------------------------
SERVER_INSTALLED=""
if [ "$REGISTER" = "true" ]; then
    say ""
    mkdir -p "$SERVER_DIR"
    if fetch_companion "$SERVER_FILE" "$SERVER_DIR/$SERVER_FILE" \
        && python3 -c "import ast,sys; ast.parse(open(sys.argv[1]).read())" \
            "$SERVER_DIR/$SERVER_FILE" 2>/dev/null; then
        SERVER_INSTALLED="$SERVER_DIR/$SERVER_FILE"
        ok "MCP server at $SERVER_INSTALLED"
    else
        warn "could not fetch $SERVER_FILE; skipping agent registration"
    fi

    if [ -n "$SERVER_INSTALLED" ]; then
        reg="$TMPDIR_INST/register_mcp.py"
        if fetch_companion "$REGISTER_FILE" "$reg"; then
            say ""
            say "Registering with coding agents:"
            python3 "$reg" --server "$SERVER_INSTALLED" || \
                warn "registration reported problems; see above"
        else
            warn "could not fetch $REGISTER_FILE; register by hand with:"
            warn "  claude mcp add gimp -- uv run --with mcp --with fastmcp \\"
            warn "      python3 $SERVER_INSTALLED"
        fi
    fi
fi
say ""
if [ "$AUTOSTART" = "true" ]; then
    say "Next: restart GIMP. The MCP server will come up on port $PORT by itself."
else
    say "Next: restart GIMP, then Tools > MCP > Start MCP Server."
    say "To change your mind later: Tools > MCP > Toggle MCP Autostart."
fi
say ""
if [ -n "$SERVER_INSTALLED" ]; then
    say "Your agents have been told about the server. Restart them to pick it up."
else
    say "Then point your MCP client at the server, for example:"
    say ""
    say "  claude mcp add gimp -- uv run --with mcp --with fastmcp \\"
    say "      python3 /path/to/gimp_mcp_server.py"
fi
say ""
say "Verify with the check_server tool, or:"
say "  python3 -c \"import socket;s=socket.create_connection(('localhost',$PORT),3);print('MCP server is up')\""
say ""
