#!/usr/bin/env python3
# GIMP MCP -- control GIMP from an MCP client.
#
# Copyright (C) 2026 tschallacka <tschallacka@outlook.com>
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version. See <https://www.gnu.org/licenses/>.

"""Generate docs/CAPABILITIES.md from the MCP server's own source.

Hand-written tool references rot the moment a signature changes. This reads
gimp_mcp_server.py with ast, so the reference cannot disagree with the code.

    python3 tools/gen_capabilities.py           # write docs/CAPABILITIES.md
    python3 tools/gen_capabilities.py --check   # fail if it is out of date
"""

import argparse
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "gimp_mcp_server.py")
PLUGIN = os.path.join(ROOT, "gimp-mcp-plugin.py")
OUT = os.path.join(ROOT, "docs", "CAPABILITIES.md")

# Sections the source does not mark, keyed by tool name.
EXTRA_SECTIONS = [
    ("Creating and inspecting images", [
        "new_canvas", "get_state_snapshot", "get_image_bitmap",
        "get_image_metadata", "get_context_state", "get_gimp_info",
    ]),
    ("Sessions, identity and images", [
        "session_info", "set_session_name", "list_images", "set_active_image",
        "adopt_image", "close_my_images", "reseat_displays",
    ]),
    ("Administrator access", [
        "request_elevation", "elevation_status", "revoke_elevation",
        "get_notifications",
    ]),
    ("Checkpoints (undo does not exist in GIMP 3.x)", [
        "checkpoint", "restore_checkpoint", "undo", "redo",
    ]),
    ("Server and escape hatch", [
        "check_server", "restart_server", "call_api",
    ]),
]

BROKEN = {
    "undo": "Always fails. GIMP 3.x exposes no undo to plug-ins; use checkpoint().",
    "redo": "Always fails. GIMP 3.x exposes no redo to plug-ins; use checkpoint().",
}


def signature(node: ast.FunctionDef) -> str:
    """Render the call signature an agent sees, without ctx."""
    parts = []
    args = node.args
    defaults = [None] * (len(args.args) - len(args.defaults)) + list(args.defaults)
    for arg, default in zip(args.args, defaults):
        if arg.arg == "ctx":
            continue
        text = arg.arg
        if arg.annotation is not None:
            text += ": " + ast.unparse(arg.annotation)
        if default is not None:
            text += " = " + ast.unparse(default)
        parts.append(text)
    return f"{node.name}({', '.join(parts)})"


def summary(node: ast.FunctionDef) -> str:
    doc = ast.get_docstring(node) or ""
    first = doc.strip().split("\n\n")[0].replace("\n", " ").strip()
    return re.sub(r"\s+", " ", first)


def details(node: ast.FunctionDef) -> str:
    """Everything after the summary, minus the Returns block."""
    doc = ast.get_docstring(node) or ""
    blocks = doc.strip().split("\n\n")[1:]
    keep = [b for b in blocks if not b.strip().startswith(("Returns:", "Raises"))]
    return "\n\n".join(b.rstrip() for b in keep).strip()


def returns(node: ast.FunctionDef) -> str:
    doc = ast.get_docstring(node) or ""
    for block in doc.strip().split("\n\n"):
        if block.strip().startswith("Returns"):
            return re.sub(r"\s+", " ", block.strip())
    return ""


def collect_tools():
    src = open(SERVER).read()
    tree = ast.parse(src)
    lines = src.split("\n")

    # Section headings the source already carries: "# CATEGORY 3 — Resize"
    marks = []
    for i, line in enumerate(lines, start=1):
        m = re.match(r"#\s*CATEGORY\s*\d+\s*[—-]\s*(.+)$", line.strip())
        if m:
            marks.append((i, m.group(1).strip()))

    def section_for(lineno):
        name = None
        for at, title in marks:
            if at <= lineno:
                name = title
            else:
                break
        return name

    tools = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not any(
            isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "tool"
            for d in node.decorator_list
        ):
            continue
        tools.append({
            "name": node.name,
            "signature": signature(node),
            "summary": summary(node),
            "details": details(node),
            "returns": returns(node),
            "section": section_for(node.lineno),
        })
    return tools


def group(tools):
    by_name = {t["name"]: t for t in tools}
    used = set()
    sections = []

    for title, names in EXTRA_SECTIONS:
        picked = [by_name[n] for n in names if n in by_name and n not in used]
        used.update(t["name"] for t in picked)
        if picked:
            sections.append((title, picked))

    rest = {}
    for tool in tools:
        if tool["name"] in used:
            continue
        rest.setdefault(tool["section"] or "Other", []).append(tool)
    for title in sorted(rest, key=lambda t: (t == "Other", t)):
        sections.append((title, sorted(rest[title], key=lambda t: t["name"])))
    return sections


def plugin_commands():
    src = open(PLUGIN).read()
    return sorted(set(re.findall(r'j\["type"\] == "([a-z_]+)"', src)))


def render(tools):
    sections = group(tools)
    out = []
    w = out.append

    w("# Capabilities")
    w("")
    w("Everything an agent can do through this MCP server, generated from")
    w("`gimp_mcp_server.py` so it cannot drift from the code.")
    w("")
    w("Regenerate after changing any tool:")
    w("")
    w("```bash")
    w("python3 tools/gen_capabilities.py")
    w("```")
    w("")
    w(f"**{len(tools)} tools** across {len(sections)} groups, "
      f"over {len(plugin_commands())} plugin commands.")
    w("")

    w("## Before anything else")
    w("")
    w("Three things decide whether an agent works smoothly here or fights the")
    w("tools. They are covered in full in the sections below, but in short:")
    w("")
    w("1. **Address images by handle, never by position.** `new_canvas` and")
    w("   `open_image` return a `handle`; pass it as `image=`. A file path or")
    w("   basename works too. Omit `image` to act on the image you touched last.")
    w("   The list of open images reorders whenever any session opens or closes")
    w("   one, which is why there is no positional index any more.")
    w("2. **One GIMP may be shared by several sessions.** You can only reach")
    w("   images you opened. Someone else's are refused, not silently retargeted.")
    w("3. **There is no undo.** GIMP 3.x exposes none to plug-ins. Take a")
    w("   `checkpoint()` before anything destructive.")
    w("")

    w("## Contents")
    w("")
    for title, items in sections:
        anchor = re.sub(r"[^a-z0-9 -]", "", title.lower()).replace(" ", "-")
        w(f"- [{title}](#{anchor}) — {len(items)} tools")
    w("")

    for title, items in sections:
        w(f"## {title}")
        w("")
        w("| Tool | What it does |")
        w("|---|---|")
        for tool in items:
            note = BROKEN.get(tool["name"])
            text = note if note else tool["summary"]
            w(f"| [`{tool['name']}`](#{tool['name']}) | {text} |")
        w("")
        for tool in items:
            w(f"### `{tool['name']}`")
            w("")
            w("```python")
            w(tool["signature"])
            w("```")
            w("")
            if tool["name"] in BROKEN:
                w(f"> **{BROKEN[tool['name']]}**")
                w("")
            w(tool["summary"])
            w("")
            if tool["details"]:
                w(tool["details"])
                w("")
            if tool["returns"]:
                w(tool["returns"])
                w("")
    return "\n".join(out).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero if the file is out of date")
    args = ap.parse_args()

    text = render(collect_tools())

    if args.check:
        current = open(OUT).read() if os.path.exists(OUT) else ""
        if current != text:
            print("docs/CAPABILITIES.md is out of date; run "
                  "python3 tools/gen_capabilities.py", file=sys.stderr)
            return 1
        print("docs/CAPABILITIES.md is up to date")
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w").write(text)
    print(f"wrote {os.path.relpath(OUT, ROOT)} "
          f"({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
