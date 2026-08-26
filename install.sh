#!/usr/bin/env bash
#
# GIMP MCP installer.
#
#   curl -fsSL https://raw.githubusercontent.com/maorcc/gimp-mcp/main/install.sh | bash
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

REPO_RAW="https://raw.githubusercontent.com/maorcc/gimp-mcp/main"
PLUGIN_FILE="gimp-mcp-plugin.py"
PLUGIN_DIR_NAME="gimp-mcp-plugin"
CONFIG_NAME="mcp-server.json"

AUTOSTART=""
ASSUME_YES=0
UNINSTALL=0
SOURCE_DIR=""
PORT=9877

while [ $# -gt 0 ]; do
    case "$1" in
        --autostart)    AUTOSTART=true ;;
        --no-autostart) AUTOSTART=false ;;
        --yes|-y)       ASSUME_YES=1 ;;
        --uninstall)    UNINSTALL=1 ;;
        --source)       SOURCE_DIR="${2:-}"; shift ;;
        --port)         PORT="${2:-9877}"; shift ;;
        -h|--help)      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done

say()  { printf '%s\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

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
    done
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
elif [ -f "$(dirname "$0")/$PLUGIN_FILE" ]; then
    cp "$(dirname "$0")/$PLUGIN_FILE" "$SRC"
    ok "using $(dirname "$0")/$PLUGIN_FILE"
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

# ---------------------------------------------------------------------------
# Autostart choice
# ---------------------------------------------------------------------------
say ""
if [ -z "$AUTOSTART" ]; then
    say "The MCP server can start by itself whenever GIMP starts, so you do not"
    say "have to pick Tools > MCP > Start MCP Server by hand each time."
    AUTOSTART="$(ask_yes_no "Start the MCP server automatically with GIMP?" true)"
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
say ""
if [ "$AUTOSTART" = "true" ]; then
    say "Next: restart GIMP. The MCP server will come up on port $PORT by itself."
else
    say "Next: restart GIMP, then Tools > MCP > Start MCP Server."
    say "To change your mind later: Tools > MCP > Toggle MCP Autostart."
fi
say ""
say "Then point your MCP client at the server, for example:"
say ""
say "  claude mcp add gimp -- uv run --directory /path/to/gimp-mcp gimp_mcp_server.py"
say ""
say "Verify with the check_server tool, or:"
say "  python3 -c \"import socket;s=socket.create_connection(('localhost',$PORT),3);print('MCP server is up')\""
say ""
