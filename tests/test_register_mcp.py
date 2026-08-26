#!/usr/bin/env python3
"""Exercise register_mcp.py against a throwaway HOME.

Checks it adds entries, preserves what was already there, is idempotent, and
removes cleanly -- without going near the real config files.
"""
import json
import os

import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(REPO, "tools", "register_mcp.py")

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail else ""))


home = tempfile.mkdtemp(prefix="regtest-home-")
env = dict(os.environ)
env["HOME"] = home
env["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
# Keep the real `claude` CLI out of it: it would write the real config.
env["PATH"] = "/usr/bin:/bin"

# Pre-existing configs with entries that must survive.
paths = {
    "desktop": os.path.join(home, ".config", "Claude",
                            "claude_desktop_config.json"),
    "opencode": os.path.join(home, ".config", "opencode", "opencode.json"),
    "codex": os.path.join(home, ".codex", "config.toml"),
}
for p in paths.values():
    os.makedirs(os.path.dirname(p), exist_ok=True)

json.dump({"mcpServers": {"other": {"command": "keepme"}}, "theme": "dark"},
          open(paths["desktop"], "w"), indent=2)
json.dump({"mcp": {"other": {"type": "local", "command": ["keepme"]}},
           "model": "x"}, open(paths["opencode"], "w"), indent=2)
open(paths["codex"], "w").write(
    'model = "gpt-5"\n\n[mcp_servers.other]\ncommand = "keepme"\n'
)

server = os.path.join(home, "gimp_mcp_server.py")
open(server, "w").write("# stub\n")


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, env=env)


print("\n=== register_mcp.py against a throwaway HOME ===\n")

r = run("--list")
check("detects the seeded agents", "Claude Desktop" in r.stdout
      and "Codex" in r.stdout and "opencode" in r.stdout, r.stdout.strip()[:60])

r = run("--server", server)
check("writes without error", r.returncode == 0, r.stderr.strip()[:80])

desktop = json.load(open(paths["desktop"]))
check("claude desktop got gimp", "gimp" in desktop["mcpServers"])
check("claude desktop kept its other server", "other" in desktop["mcpServers"])
check("claude desktop kept unrelated keys", desktop.get("theme") == "dark")

oc = json.load(open(paths["opencode"]))
check("opencode got gimp", "gimp" in oc["mcp"])
check("opencode entry has the right shape",
      oc["mcp"]["gimp"].get("type") == "local"
      and isinstance(oc["mcp"]["gimp"].get("command"), list),
      json.dumps(oc["mcp"]["gimp"])[:70])
check("opencode kept its other server", "other" in oc["mcp"])
check("opencode kept unrelated keys", oc.get("model") == "x")

codex = open(paths["codex"]).read()
check("codex got a gimp block", "[mcp_servers.gimp]" in codex)
check("codex kept its other block", "[mcp_servers.other]" in codex)
check("codex kept unrelated keys", 'model = "gpt-5"' in codex)

# tomllib proves we produced valid TOML, not just plausible text.
try:
    import tomllib
    parsed = tomllib.loads(codex)
    check("codex file is valid TOML",
          "gimp" in parsed.get("mcp_servers", {})
          and "other" in parsed.get("mcp_servers", {}))
except ImportError:
    check("codex file is valid TOML (skipped, no tomllib)", True)

r = run("--server", server)
check("second run is idempotent", "already correct" in r.stdout, r.stdout.strip()[-70:])

before = open(paths["codex"]).read()
run("--server", server)
check("codex unchanged on a repeat run", open(paths["codex"]).read() == before)

r = run("--remove")
check("remove exits cleanly", r.returncode == 0, r.stderr.strip()[:80])
desktop = json.load(open(paths["desktop"]))
oc = json.load(open(paths["opencode"]))
codex = open(paths["codex"]).read()
check("gimp gone from claude desktop", "gimp" not in desktop["mcpServers"])
check("gimp gone from opencode", "gimp" not in oc["mcp"])
check("gimp gone from codex", "[mcp_servers.gimp]" not in codex)
check("other survived the removal everywhere",
      "other" in desktop["mcpServers"] and "other" in oc["mcp"]
      and "[mcp_servers.other]" in codex)

backups = [f for f in os.listdir(os.path.dirname(paths["desktop"]))
           if ".bak-" in f]
check("backups were written", len(backups) >= 1, f"{len(backups)} found")

# A corrupt config must be refused, not overwritten.
open(paths["desktop"], "w").write("{ not json")
r = run("--server", server)
check("refuses to clobber unreadable JSON",
      "not readable JSON" in (r.stdout + r.stderr))
check("corrupt file left untouched",
      open(paths["desktop"]).read() == "{ not json")

shutil.rmtree(home, ignore_errors=True)

passed = sum(1 for _, ok in results if ok)
print(f"\n=== {passed}/{len(results)} checks passed ===")
sys.exit(0 if passed == len(results) else 1)
