#!/usr/bin/env python3
# GIMP MCP -- control GIMP from an MCP client.
#
# Copyright (C) 2026 tschallacka <tschallacka@outlook.com>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. See <https://www.gnu.org/licenses/>.

"""Register the GIMP MCP server with whichever coding agents are installed.

Installing the GIMP plug-in only gets you half a working setup: the agent still
has to be told the MCP server exists, which otherwise means hand-editing a
different config file per agent. This finds the ones present and writes the
entry, backing up anything it touches and leaving other entries alone.

    python3 tools/register_mcp.py --list          # what would be written where
    python3 tools/register_mcp.py --server PATH   # write it
    python3 tools/register_mcp.py --remove        # take it back out
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

NAME = "gimp"
HOME = os.path.expanduser("~")


def config_home():
    return os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config")


def run_command(server_path):
    """How an agent should launch the server.

    uv resolves the dependencies per-run, so the user does not have to create a
    virtualenv or install anything globally. Without uv we fall back to plain
    python3 and say what is needed.
    """
    if shutil.which("uv"):
        return ["uv", "run", "--with", "mcp", "--with", "fastmcp",
                "python3", server_path]
    return [sys.executable or "python3", server_path]


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

def claude_desktop_paths():
    if sys.platform == "darwin":
        yield os.path.join(HOME, "Library", "Application Support", "Claude",
                           "claude_desktop_config.json")
    elif os.name == "nt" or os.environ.get("APPDATA"):
        appdata = os.environ.get("APPDATA")
        if appdata:
            yield os.path.join(appdata, "Claude", "claude_desktop_config.json")
    yield os.path.join(config_home(), "Claude", "claude_desktop_config.json")


def cline_paths():
    bases = [
        os.path.join(config_home(), "Code", "User", "globalStorage",
                     "saoudrizwan.claude-dev"),
        os.path.join(HOME, "Library", "Application Support", "Code", "User",
                     "globalStorage", "saoudrizwan.claude-dev"),
    ]
    for base in bases:
        yield os.path.join(base, "settings", "cline_mcp_settings.json")


def detect():
    """Agents present on this machine, with where their MCP config lives."""
    found = []

    if shutil.which("claude") or os.path.isdir(os.path.join(HOME, ".claude")):
        found.append({
            "name": "Claude Code",
            "kind": "claude-cli",
            "path": os.path.join(HOME, ".claude.json"),
        })

    for path in claude_desktop_paths():
        if os.path.isdir(os.path.dirname(path)):
            found.append({
                "name": "Claude Desktop",
                "kind": "json",
                "path": path,
                "key": ["mcpServers"],
            })
            break

    codex_dir = os.path.join(HOME, ".codex")
    if shutil.which("codex") or os.path.isdir(codex_dir):
        found.append({
            "name": "Codex",
            "kind": "toml",
            "path": os.path.join(codex_dir, "config.toml"),
        })

    opencode_dir = os.path.join(config_home(), "opencode")
    if shutil.which("opencode") or os.path.isdir(opencode_dir):
        found.append({
            "name": "opencode",
            "kind": "opencode",
            "path": os.path.join(opencode_dir, "opencode.json"),
            "key": ["mcp"],
        })

    for path in cline_paths():
        if os.path.isdir(os.path.dirname(os.path.dirname(path))):
            found.append({
                "name": "Cline",
                "kind": "json",
                "path": path,
                "key": ["mcpServers"],
            })
            break

    return found


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

def backup(path):
    if not os.path.exists(path):
        return None
    dest = f"{path}.bak-{time.strftime('%Y%m%d-%H%M%S')}"
    shutil.copy2(path, dest)
    return dest


def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            text = fh.read().strip()
        return json.loads(text) if text else {}
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{path} is not readable JSON ({exc}); "
                           f"not touching it") from exc


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")


def write_json_target(target, command, remove):
    data = load_json(target["path"])
    node = data
    for key in target["key"]:
        node = node.setdefault(key, {})
        if not isinstance(node, dict):
            raise RuntimeError(f"{target['path']}: '{key}' is not an object")

    if remove:
        if NAME not in node:
            return "not present"
        backup(target["path"])
        del node[NAME]
        save_json(target["path"], data)
        return "removed"

    entry = {"command": command[0], "args": command[1:]}
    if target["kind"] == "opencode":
        # opencode wants one list and an explicit enable flag.
        entry = {"type": "local", "command": command, "enabled": True}

    existed = NAME in node
    if existed and node[NAME] == entry:
        return "already correct"
    backup(target["path"])
    node[NAME] = entry
    save_json(target["path"], data)
    return "updated" if existed else "added"


def write_claude_cli(target, command, remove):
    """Prefer the CLI; it owns the file's schema and may change it."""
    if shutil.which("claude"):
        if remove:
            proc = subprocess.run(["claude", "mcp", "remove", NAME, "-s", "user"],
                                  capture_output=True, text=True)
            return "removed" if proc.returncode == 0 else "not present"
        subprocess.run(["claude", "mcp", "remove", NAME, "-s", "user"],
                       capture_output=True, text=True)
        proc = subprocess.run(
            ["claude", "mcp", "add", NAME, "-s", "user", "--"] + command,
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout).strip()[:200])
        return "added via claude mcp add"

    return write_json_target(
        {**target, "kind": "json", "key": ["mcpServers"]}, command, remove
    )


def write_toml_target(target, command, remove):
    """Codex uses TOML and Python ships no writer, so edit the block textually."""
    path = target["path"]
    text = open(path).read() if os.path.exists(path) else ""
    header = f"[mcp_servers.{NAME}]"

    # Only meaningful when adding; on --remove `command` is empty.
    block = "" if remove else (
        f"{header}\n"
        f"command = {json.dumps(command[0])}\n"
        f"args = {json.dumps(command[1:])}\n"
    )

    pattern = re.compile(
        r"^\[mcp_servers\.%s\]\n(?:(?!^\[).*\n?)*" % re.escape(NAME),
        re.MULTILINE,
    )
    match = pattern.search(text)
    present = match is not None

    if remove:
        if not present:
            return "not present"
        backup(path)
        open(path, "w").write(pattern.sub("", text).lstrip("\n"))
        return "removed"

    if match is not None:
        if match.group(0).strip() == block.strip():
            return "already correct"
        backup(path)
        new = pattern.sub(block, text)
    else:
        backup(path)
        new = text.rstrip("\n")
        new = (new + "\n\n" if new else "") + block

    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write(new)
    return "updated" if present else "added"


WRITERS = {
    "claude-cli": write_claude_cli,
    "json": write_json_target,
    "opencode": write_json_target,
    "toml": write_toml_target,
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", help="path to gimp_mcp_server.py")
    ap.add_argument("--list", action="store_true",
                    help="show detected agents and do nothing")
    ap.add_argument("--remove", action="store_true",
                    help="remove the entry instead of adding it")
    args = ap.parse_args()

    targets = detect()
    if not targets:
        print("  no supported coding agents found "
              "(looked for Claude Code, Claude Desktop, Codex, opencode, Cline)")
        return 0

    if args.list:
        print(f"  {len(targets)} agent(s) detected:")
        for t in targets:
            print(f"    {t['name']:<16} {t['path']}")
        return 0

    if not args.remove:
        if not args.server:
            print("  --server is required unless --remove", file=sys.stderr)
            return 2
        server = os.path.abspath(os.path.expanduser(args.server))
        if not os.path.exists(server):
            print(f"  no server script at {server}", file=sys.stderr)
            return 2
        command = run_command(server)
    else:
        command = []

    failures = 0
    for target in targets:
        try:
            outcome = WRITERS[target["kind"]](target, command, args.remove)
            print(f"    {target['name']:<16} {outcome}")
        except Exception as exc:
            failures += 1
            print(f"    {target['name']:<16} FAILED: {exc}", file=sys.stderr)

    if not args.remove and not shutil.which("uv"):
        print("  note: uv is not installed, so the entry runs the server with")
        print("        plain python3. Install the deps with:")
        print("          python3 -m pip install mcp fastmcp")

    if not args.remove:
        print("  restart your agent for it to pick up the new server")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
