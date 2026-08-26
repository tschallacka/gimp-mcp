# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a GIMP MCP (Model Context Protocol) integration that enables external control of GIMP 3.2 through Claude Desktop and other MCP clients. The system consists of two main components:

1. **GIMP Plugin** (`gimp-mcp-plugin.py`): A GIMP 3.2 plugin that starts a socket server inside GIMP
2. **MCP Server** (`gimp_mcp_server.py`): An MCP server that connects to the GIMP plugin and exposes GIMP functionality

## Architecture

The system uses a client-server architecture:
- GIMP Plugin creates a socket server (localhost:9877) that accepts commands
- MCP Server exposes 90 tools and translates each into a JSON command over that socket
- Commands execute in GIMP's Python-Fu environment with access to the full GIMP 3.2 API
- Every command carries a `_session` id, minted once per MCP server process, plus the
  client's name, cwd, host and pid so a human can tell which agent is asking

## Installation & Setup

One command finds every GIMP 3.x config directory, installs the plugin into each, and
offers to start the server automatically with GIMP:

```bash
./install.sh --source .     # from a clone
# or, for end users:
curl -fsSL https://raw.githubusercontent.com/maorcc/gimp-mcp/main/install.sh | bash
```

Flags: `--autostart` / `--no-autostart`, `--yes`, `--uninstall`, `--source DIR`, `--port N`.

The installer pins the interpreter: it finds a `python3` that can `import gi` and writes
it into the plugin's shebang as an absolute path. GIMP launches a `.py` plug-in through
that shebang, so a bare `#!/usr/bin/env python3` resolves against whatever `PATH` GIMP
inherited, and a nix/pyenv/conda/virtualenv interpreter earlier on it kills the plugin at
`import gi` during GIMP's startup scan — visible only as a traceback on stderr. Override
with `$GIMP_MCP_PYTHON`.

Autostart is driven by `<gimp-config-dir>/mcp-server.json`
(`{"autostart": bool, "port": int, "host": str}`), which the plugin reads from a
persistent procedure GIMP launches at startup. Users can flip it from
**Tools > MCP > Toggle MCP Autostart**. Without autostart, the server is started from
**Tools > MCP > Start MCP Server**.

Restart GIMP after installing — the plugin is loaded at GIMP startup.

### MCP Server Configuration
Add to Claude Desktop config (`~/.config/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "gimp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/gimp-mcp", "gimp_mcp_server.py"]
    }
  }
}
```

## Development Commands

```bash
python3 tests/test_image_registry.py    # 46 unit tests; stubs GIMP, no GIMP needed
python3 tests/audit_all_tools.py        # 111 checks over 85/87 commands; needs a live GIMP
python3 run_tests.py                    # 60 end-to-end checks; needs a live GIMP
python3 tests/test_admin_flow_live.py   # elevation end to end; needs GIMP AND a human to click Grant
uv run pre-commit run --all-files       # ruff
```

## Addressing Images: handles, not indexes

**There is no `image_index` parameter.** It was removed from every tool. GIMP's image
list reorders as images open and close — creating a second canvas moves the first from
index 0 to index 1 — so a positional index silently retargets an agent's edits onto the
wrong file with no error.

Every tool that acts on an image takes `image`, which accepts:

| Form | Example |
|---|---|
| handle (returned by `new_canvas` / `open_image`) | `image="logo"` |
| GIMP image_id, int or numeric string | `image=3` |
| full file path | `image="/photos/cat.png"` |
| file base name | `image="cat.png"` |
| label | `image="cat"` |

Omit `image` and the tool acts on the session's **current image** — the last one this
session touched.

```python
handle = open_image("/photos/cat.png")["handle"]
adjust_brightness_contrast(contrast=15, image=handle)
export_image("/tmp/out.png", image=handle)
close_my_images()
```

`get_image_bitmap` and `get_image_metadata` take no `image` argument; they resolve the
session's current image. To read a specific one, make it current with `set_active_image`
or use `get_state_snapshot(image=...)`. `get_context_state` reports GIMP's global brush
and colour state and is not tied to an image. `batch_resize` and
`export_sprite_sheet(source="images")` act on this session's images only.

## Sessions

One running GIMP can be shared by several agent sessions. Each MCP server process mints
a `SESSION_ID`; the plugin tags every image it opens with a `gimp-mcp` GIMP parasite
holding `{handle, session, label, origin, created}`. Parasites live with the image and
survive a plugin restart.

Consequences to respect when writing code or driving the tools:

- `list_images()` marks each image `mine: true/false`; `list_images(mine_only=True)` filters
- `_guard_owner` refuses any attempt to resolve another session's image by handle, id
  or path. Treat this as **accident prevention, not a security boundary** — see below.
- A session that has gone quiet for `SESSION_ORPHAN_AFTER` (300s), or that this plugin
  process has never seen, is treated as gone and its images become reachable again.
  Without that, restarting the MCP client — which mints a new session id — would strand
  every image the old one opened, with no way back.
- Untracked images — opened by hand in GIMP — belong to nobody and stay reachable by
  every session. That is deliberate: they are usually what the user wants worked on.
- `close_my_images()` closes only what this session opened — use it to clean up
- `adopt_image(image=...)` claims an untracked image for this session

### The ownership gate is advisory

It stops an agent reaching the wrong image by mistake. It does not stop a determined
caller, and nothing in this design tries to:

- `call_api` executes arbitrary Python against the full `Gimp` binding in a context
  shared by every session. It goes through no resolver and no guard.
- `_session` is a plain field in the request JSON with no authentication, and session
  ids are published in `list_images` and `session_info`. Any client can replay another
  session's id and inherit its identity, including its elevation.

So: do not describe this as enforcement in user-facing text, and do not build anything
on it that would be a problem if bypassed. The threat model is a confused agent, not a
hostile one — every session here is already running with the user's own privileges.

### Identity

`set_session_name(name)` names the session for humans; `$GIMP_MCP_SESSION_NAME` sets a
default; otherwise it is a generic "MCP client". The name surfaces in `list_images`,
`session_info` and `elevation_status` as `described_as`, and in the elevation dialog.
Recommend calling it at the start of a task — an approval prompt that cannot say which
agent is asking is not a meaningful prompt.

### Administrator elevation

`request_elevation(reason)` puts a real GTK dialog in GIMP and blocks until the user
answers, timing out after 180 seconds. `reason` is required and shown verbatim. On
approval the session may see, edit and close every session's images.
`elevation_status()` and `revoke_elevation()` round it out; the user can revoke all
grants from **Tools > MCP > Revoke MCP Admin Access**.

Advise revoking as soon as the task needing it is done.

### Cross-session notifications

Closing another session's image requires `reason=...` on `close_image` and is refused
without it. The owner is sent `{type: "image_closed_by_administrator", message, handle,
image_id, label, closed_by, reason, saved_to, at}`.

The wire protocol has no server push, so notifications ride along on that session's next
response under a `notifications` key, and `get_notifications()` collects them
explicitly. Each is delivered once; queues for sessions quiet more than an hour are
dropped.

### Checkpoints, not undo

GIMP 3.x exposes no undo to plug-ins: the PDB has no `gimp-image-undo` and `Gimp.Image`
offers only undo *groups*. The `undo`/`redo` tools are deliberate tombstones that always
return that explanation. `checkpoint(image, label, file_path)` writes an XCF snapshot and
`restore_checkpoint(checkpoint, image)` rolls back, **keeping the same handle** (the
`image_id` changes, the handle does not). Recommend a checkpoint before any destructive
step: flatten, scale down, colour-mode change.

## Closing images

`close_image` works by deleting the image's display window; GIMP drops an image when its
last display goes. Because GIMP offers no way to ask which image a display shows, the
plugin records the display id at the moment it calls `Gimp.Display.new()`.

An image with no recorded display (opened by hand, or by a previous server process)
cannot be closed directly. `close_image(..., force=True)` and `reseat_displays()` handle
that by giving every open image a fresh window first — nothing is lost, but window
position and zoom are reset for all of them.

`Gimp.get_displays()` does not exist in GIMP 3.x. Do not reintroduce it; it was the
cause of the original broken `close_image` and `set_active_image`.

## GIMP 3.2 API Key Points

- Use `Gimp.get_images()` instead of deprecated `Gimp.list_images()`
- Access layers via `image.get_layers()` instead of `Gimp.get_active_layer()`
- Colors are created with `Gegl.Color.new('color_name')`
  or with color RGB values, e.g. `Gegl.Color.new("rgb(1.0, 0.647, 0.0)")`. Notice, each RGB value is in the range 0-1
- Always call `Gimp.displays_flush()` after drawing operations
- `Gimp.PDBProcType.EXTENSION` was renamed `PERSISTENT` in 3.2; the plugin accepts either
- Custom per-image metadata goes in a parasite (`attach_parasite` / `get_parasite`)
- Empty `file_path` / `output_dir` / `output_path` are rejected by the plugin before they
  reach GIMP. Handing GIMP an empty path raises a modal dialog inside the user's GIMP
  that the caller never sees, which looks like a hang. Keep that validation.

### Autostart: persistent_ready() is not optional

A persistent procedure **must** call `procedure.persistent_ready()` once its socket is
listening and *before* it enters the GLib main loop.

Without it GIMP blocks the rest of its own startup forever. The symptom is not an error:
the GUI's image managers are never constructed, so every `Gimp.Display.new()` afterwards
fails with "constructor returned NULL" and no image can ever be shown. This is expensive
to diagnose from the symptom, so do not remove or reorder that call.

### Essential Initialization Pattern
Most raw Python-Fu operations should start with this initialization:
```python
images = Gimp.get_images()
image = images[0]  # or image1 = images[0]
layers = image.get_layers()
layer = layers[0]  # or layer1 = layers[0]
drawable = layer   # or drawable1 = layer
```

Note this is the raw-API pattern for `call_api`. Prefer the dedicated tools with
`image=<handle>` whenever one exists — `images[0]` has the same drift problem that
`image_index` had.

### Common Operations

**Drawing a line:**
```python
Gimp.pencil(drawable, [x1, y1, x2, y2])
Gimp.displays_flush()
```

**Setting colors:**
```python
red_color = Gegl.Color.new("red")
Gimp.context_set_foreground(red_color)
```

**Creating shapes:**
```python
Gimp.Image.select_ellipse(image, Gimp.ChannelOps.REPLACE, x, y, width, height)
Gimp.Drawable.edit_fill(drawable, Gimp.FillType.FOREGROUND)
Gimp.Selection.none(image)
Gimp.displays_flush()
```

## API Usage

### Raw execution
The `call_api` tool runs arbitrary Python-Fu:
- `api_path`: "exec"
- `args`: Array containing procedure name and code/expressions

```json
{
  "api_path": "exec",
  "args": ["pyGObject-console", ["print('hello world')"]]
}
```

## Important Notes

- Commands execute in a persistent Python context - imports and variables persist between calls
- GIMP 3.2 API differs significantly from 2.x - consult https://developer.gimp.org/api/3.0/libgimp/
- Always verify API calls work before building complex operations
- The `gimpfu` module is not available in GIMP 3.2
- Use proper error handling as socket connections can fail
- When adding a tool that acts on an image, give it `image: str | int | None = None` and
  forward it as `"image"` in the params; the plugin resolves it via `_resolve_image(params)`

## File Structure

- `install.sh`: one-line installer; finds GIMP config dirs, installs plugin, sets autostart
- `gimp-mcp-plugin.py`: GIMP plugin with socket server, image registry and command execution
- `gimp_mcp_server.py`: MCP server that bridges socket to MCP protocol
- `tests/test_image_registry.py`: unit tests for identity, resolution, sessions and closing
- `run_tests.py`: end-to-end suite against a live GIMP
- `docs/best_practices.md`: Best practices, common recipes, self-critique checklist, and guidelines exposed via MCP prompts
- `docs/iterative_workflow.md`: Professional iterative workflow guidance for building complex images with layer management and validation
- `GIMP_MCP_PROTOCOL.md`: Detailed API documentation and examples
- `README.md`: Installation and setup instructions
