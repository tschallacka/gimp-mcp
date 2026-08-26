# GIMP MCP

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Works with Claude Desktop](https://img.shields.io/badge/Works%20with-Claude%20Desktop-7B2CBF.svg)](https://claude.ai/desktop)
[![GIMP 3.2](https://img.shields.io/badge/GIMP-3.2-orange.svg)](https://gimp.org)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io)
[![CodeRabbit](https://img.shields.io/badge/CodeRabbit-AI%20Review-171717?logo=coderabbit)](https://coderabbit.ai)

## Demo

![GIMP MCP in action — AI agent driving GIMP through natural language](docs/mcpInAction.gif)

Full demo (with audio): https://github.com/tschallacka/gimp-mcp/raw/main/docs/demo.mp4

*AI agent using GIMP MCP to remove a background, edit a character's expression, and verify results — all through natural language via Claude*

---

## Overview

GIMP MCP bridges GIMP's professional image editing capabilities with AI assistants through the [Model Context Protocol](https://modelcontextprotocol.io). It lets you edit images by describing what you want — and gives the AI a live visual feedback channel to verify each change before moving on.

**What makes it different from other GIMP integrations:**

- The AI can *see* the image at any point in the workflow without saving to disk (`get_state_snapshot`)
- Supports fully autonomous multi-step pipelines: open → edit → verify → refine → export
- 90 dedicated tool commands covering every major GIMP operation
- Images are addressed by stable **handles**, not by position, so an agent never edits the wrong file
- A session can only reach images it opened; touching another session's work needs the
  user's explicit approval, asked for in a GIMP dialog
- Checkpoints make destructive edits reversible, which GIMP 3.x otherwise does not allow
- Fully compatible with GIMP 3.2.x (all breaking API changes resolved)

## Key Features

| | |
|---|---|
| **Live visual feedback** | `get_state_snapshot` returns a PNG preview mid-workflow so the AI verifies each step |
| **90 GIMP tools** | Adjustments, transforms, selections, layers, drawing, text, filters — all via MCP |
| **Stable image handles** | Every image gets a handle that survives other images opening and closing |
| **Enforced isolation** | A session cannot reach another session's images without approval |
| **Approval in GIMP** | `request_elevation` puts a real dialog on the user's screen and waits |
| **Checkpoints** | Snapshot before a risky edit and roll back — GIMP 3.x exposes no undo |
| **One-line install** | A single command finds GIMP, installs the plugin, and enables autostart |
| **Iterative workflows** | AI loops until a goal is met — e.g. keeps removing BG until no pixels remain |
| **Region snapshots** | Zoom into any area for detail verification (face, mouth, corner, etc.) |
| **Universal MCP** | Works with Claude Desktop, Claude Code, Gemini CLI, PydanticAI, and more |

## What Can It Do?

### Background Removal with Iterative Verification
The AI removes the background, takes a snapshot to inspect the result, detects remaining pixels, and loops until the image is clean:

```
"Remove the background from this image and keep looping until only the character remains"
```

### Expression Editing
```
"Make the character smile — paint a smile arc with teeth over her mouth"
```

### Complex Multi-Step Pipelines
```
"Open navi_portrait.png, remove the background, verify it's clean,
 then make her smile and export the final result as a PNG"
```

### Color & Tone Work
```
"Boost the contrast, shift the hue 15 degrees warmer, then show me a before/after zoom of the face"
```

### Text & Compositing
```
"Add a bold title at the top in white with a subtle drop shadow, then export for web"
```

---

## Prerequisites

- **GIMP 3.2+** — tested on GIMP 3.2.2 (Windows, macOS, Linux)
- **Python 3.8+** — for the MCP server
- **uv** — Python package manager (`pip install uv`)
- **MCP-compatible AI client** — Claude Desktop, Claude Code, Gemini CLI, PydanticAI, etc.

---

## Quick Start

### 1. Install the GIMP plugin

Launch GIMP once so it creates its config folder, quit it, then run:

```bash
curl -fsSL https://raw.githubusercontent.com/tschallacka/gimp-mcp/main/install.sh | bash
```

The installer finds every GIMP 3.x user config directory on the machine — native,
Snap, Flatpak, macOS and Windows — installs the plugin into each, and asks whether
the MCP server should start automatically whenever GIMP starts. Say yes and you
never have to touch the Tools menu again.

Restart GIMP when it finishes.

The installer also pins the interpreter. GIMP runs a `.py` plug-in through its
shebang, so a plain `#!/usr/bin/env python3` resolves against whatever `PATH` GIMP
inherited — and a nix, pyenv, conda or virtualenv `python3` earlier on that path makes
the plugin die at `import gi` during GIMP's startup scan, with nothing visible but a
traceback on stderr. The installer finds a `python3` that can actually `import gi` and
writes it into the shebang as an absolute path. Override the choice with
`$GIMP_MCP_PYTHON`.

**Installer options**

| Flag | Effect |
|---|---|
| `--autostart` / `--no-autostart` | Set the startup behaviour without being asked |
| `--register` / `--no-register` | Add the MCP server to the coding agents on this machine |
| `--yes` | Accept defaults, never prompt (for scripts and CI) |
| `--uninstall` | Remove the plugin, its config, the server, and every agent entry |
| `--source DIR` | Install from a local checkout instead of GitHub |
| `--port N` | Use a different socket port (default 9877) |

From a clone, install the working copy rather than the published one:

```bash
git clone https://github.com/tschallacka/gimp-mcp.git
cd gimp-mcp
./install.sh --source .
```

<details>
<summary>Manual install (if you would rather not run a script)</summary>

GIMP names its per-user folder after its **major.minor** version (`3.0`, `3.2`, `3.4`, …)
and creates a fresh one on each minor upgrade, so the folder *moves* when you upgrade.
Check the active path under **Edit > Preferences > Folders > Plug-ins**.

```bash
# Pick the base directory for your platform:
BASE="$HOME/.config/GIMP"                          # Linux (native)
# BASE="$HOME/snap/gimp/current/.config/GIMP"      # Linux (Snap)
# BASE="$HOME/.var/app/org.gimp.GIMP/config/GIMP"  # Linux (Flatpak)
# BASE="$HOME/Library/Application Support/GIMP"    # macOS
# On Windows: %APPDATA%\GIMP\<VERSION>\plug-ins\

GIMP_DIR="$(ls -d "$BASE"/3.* 2>/dev/null | sort -V | tail -1)"
mkdir -p "$GIMP_DIR/plug-ins/gimp-mcp-plugin"
cp gimp-mcp-plugin.py "$GIMP_DIR/plug-ins/gimp-mcp-plugin/"
chmod +x "$GIMP_DIR/plug-ins/gimp-mcp-plugin/gimp-mcp-plugin.py"
```

To enable autostart by hand, write `$GIMP_DIR/mcp-server.json`:

```json
{ "autostart": true, "port": 9877, "host": "localhost" }
```

</details>

### 2. Start the server

If you enabled autostart, the server comes up on `localhost:9877` by itself the next
time GIMP starts — no image needs to be open.

Otherwise, start it from **Tools > MCP > Start MCP Server**.

To change your mind later, use **Tools > MCP > Toggle MCP Autostart**, or edit
`autostart` in `<gimp-config-dir>/mcp-server.json`.

### 3. Install the server dependencies

```bash
git clone https://github.com/tschallacka/gimp-mcp.git
cd gimp-mcp
uv sync
```

### 4. Configure your MCP client

#### Claude Code
```bash
cd /path/to/gimp-mcp
claude  # .mcp.json is auto-detected
```

Or manually:
```bash
claude mcp add gimp-mcp -- uv run --directory /full/path/to/gimp-mcp gimp_mcp_server.py
```

#### Claude Desktop
`~/.config/Claude/claude_desktop_config.json` (Linux/macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "gimp": {
      "command": "uv",
      "args": ["run", "--directory", "/full/path/to/gimp-mcp", "gimp_mcp_server.py"]
    }
  }
}
```

#### Gemini CLI
`~/.config/gemini/.gemini_config.json`:
```json
{
  "mcpServers": {
    "gimp": {
      "command": "uv",
      "args": ["run", "--directory", "/full/path/to/gimp-mcp", "gimp_mcp_server.py"]
    }
  }
}
```

#### PydanticAI
```python
from pydantic_ai import Agent
from pydantic_ai.mcp import MCPServerStdio

server = MCPServerStdio('uv', args=['run', '--directory', '/path/to/gimp-mcp', 'gimp_mcp_server.py'])
agent = Agent('openai:gpt-4o', mcp_servers=[server])
```

---

## Images, Handles and Sessions

This is the part that matters most for getting reliable results out of an agent.

### Address images by handle, never by position

`new_canvas` and `open_image` both return a **handle** — a short, readable, stable
name such as `logo` or `portrait-2`. Pass it as the `image` argument to any tool.

```python
canvas = new_canvas(1024, 1024, name="logo")   # -> handle "logo"
fill_layer(color="#202020", image="logo")
add_text("Hello", x=40, y=60, image="logo")
export_image("/tmp/logo.png", image="logo")
```

`image` also accepts a GIMP `image_id`, a **file path**, or the file's base name, so an
image opened from disk can always be found again by the path it came from:

```python
open_image("/photos/cat.png")          # -> handle "cat"
sharpen(image="/photos/cat.png")       # by full path
sharpen(image="cat.png")               # by base name
sharpen(image="cat")                   # by handle
```

Omit `image` entirely and the tool acts on the session's **current image** — the last
one that session touched:

```python
open_image("/photos/cat.png")
auto_levels()                          # applies to cat.png
export_image("/tmp/out.png")
```

Handles exist because position does not survive. GIMP's image list reorders as images
open and close: create a second canvas and the first one silently moves from index 0 to
index 1. Any agent holding onto a position then edits the wrong file, with no error. The
old `image_index` parameter has been removed from every tool for exactly this reason.

### One GIMP, several sessions

A single running GIMP can be driven by several agent sessions at once. Each MCP server
process mints its own session id, and every image it opens is tagged with it, so:

- `list_images()` marks each image `mine: true` or `false`
- naming another session's image by handle, id or path is **refused**, not guessed at
- `close_my_images()` closes only what this session opened

This is accident prevention, not security. It stops an agent editing the wrong file; it
does not stop a determined one. `call_api` runs arbitrary Python against GIMP with no
ownership check at all, and the session id is an unauthenticated field that any client
could copy from `list_images`. Every session is already running with your privileges —
the problem being solved is a confused agent, not a hostile one.

If the MCP client restarts it gets a new session id, so images the old one opened would
be orphaned. A session unseen for five minutes is treated as gone and its images become
reachable again, which is what makes a restart recoverable.

```python
session_info()          # what do I own, what will I act on
list_images(mine_only=True)
```

An image someone opened by hand in the GIMP window belongs to nobody, and stays
reachable by any session — it is usually one the user wants worked on. Call
`adopt_image(image=...)` to claim it and give it a handle.

### Say who you are

Nothing in the MCP handshake tells GIMP which agent is connected, so a session shows up
as an id and a working directory until you name it:

```python
set_session_name("icon export for acme-web")
```

Worth doing once at the start of a task. The name appears in `list_images`,
`session_info` and — the reason it matters — in the dialog asking the user to approve
administrator access. A user who cannot tell which agent is asking cannot reasonably
approve it. It can also be set from `$GIMP_MCP_SESSION_NAME`.

### Administrator access

If you genuinely need another session's images — cleaning up after a crashed run, say —
ask for it:

```python
request_elevation(reason="clean up 6 stale canvases left by a crashed run")
```

This puts a dialog on the user's screen **inside GIMP** and blocks until they answer, up
to 180 seconds. The `reason` is required and is shown to them verbatim, so write it for
a person. On approval the session may see, edit and close every session's images.

```python
elevation_status()     # {session, elevated, granted_at, reason, admin_sessions, described_as}
revoke_elevation()     # give it up again
```

Revoke as soon as the task that needed it is done, so a later mistake cannot reach
someone else's work. The user can revoke every grant at any time from
**Tools > MCP > Revoke MCP Admin Access**.

If the user denies the request, work within your own images rather than asking again.

### Closing someone else's image

Closing an image owned by another session needs administrator access *and* a reason:

```python
close_image(image="stale-canvas", reason="left over from a crashed export run")
```

Without `reason` the call is refused. The owning session is told what happened:

```json
{"type": "image_closed_by_administrator", "message": "...", "handle": "stale-canvas",
 "image_id": 7, "label": "stale canvas", "closed_by": "...", "reason": "...",
 "saved_to": null, "at": 1730000000.0}
```

### Notifications

The socket protocol has no way for the plugin to push to a session, so messages ride
along on that session's **next** response, under a `notifications` key in the result.
You will usually see them without asking. To check explicitly — for instance when an
image you expected has vanished:

```python
get_notifications()    # {notifications, count}; collecting them clears the queue
```

Each notification is delivered once. Queues for sessions quiet for more than an hour are
dropped.

### Checkpoints instead of undo

GIMP 3.x exposes no undo to plug-ins: the PDB has no `gimp-image-undo` procedure, and
`Gimp.Image` offers only undo *groups*. The `undo` and `redo` tools therefore always
fail, with an error saying so. Use checkpoints instead:

```python
cp = checkpoint(image=handle, label="before-flatten")["checkpoint"]
flatten_image(image=handle)
# not what you wanted:
restore_checkpoint(cp, image=handle)
```

`checkpoint` writes an XCF snapshot (to a temp file unless you pass `file_path`).
`restore_checkpoint` closes the current image and loads the snapshot in its place,
**keeping the same handle** — references you already hold keep working, though the
underlying `image_id` changes.

Take one before any destructive step: flatten, scale down, colour-mode change.

### Clean up when you are done

```python
close_my_images()
```

Left-open images accumulate and clutter the workspace for every other session. Closing
an image this server did not open needs `force=True`, which first gives every open image
a fresh window so the target can be released — nothing is lost, but window position and
zoom are reset for all of them.

### Recommended agent workflow

```python
set_session_name("retouch cat.png")               # 1. say who you are
session_info()                                    # 2. orient
handle = open_image("/photos/cat.png")["handle"]  # 3. open, keep the handle

checkpoint(image=handle, label="original")        # 4. before anything destructive
adjust_brightness_contrast(contrast=15, image=handle)
get_state_snapshot(image=handle)                  # 5. look at the result

export_image("/tmp/cat_out.png", image=handle)    # 6. export
close_my_images()                                 # 7. clean up
```

---

## Available MCP Tools

### Visual Feedback

#### `get_state_snapshot(image, max_size, region, label)`
Returns a live PNG of the image state — the AI's primary feedback mechanism. Call this
between any edits to verify the result without saving to disk.

```python
# Full image snapshot of the current image
snapshot = get_state_snapshot(max_size=512)

# A specific image, zoomed into a face region
snapshot = get_state_snapshot(
    image="portrait",
    region={"x": 140, "y": 80, "width": 240, "height": 300},
    max_size=512,
    label="face-check"
)
```

This enables iterative agentic workflows: **edit → snapshot → assess → refine → repeat**.

#### `get_image_bitmap(max_width, max_height, region)`
Lower-level bitmap fetch with region extraction and scaling. Returns PNG data.

> Note: `get_image_bitmap` and `get_image_metadata` take no `image` argument — they act
> on the session's current image. To read a specific image, make it current with
> `set_active_image(image=...)`, or use `get_state_snapshot(image=...)`, which takes a
> handle directly. `get_context_state` reports GIMP's global brush and colour state and
> is not tied to an image at all.

### Sessions & Image Management
| Tool | Description |
|---|---|
| `session_info` | What this session owns and what it will act on |
| `list_images(mine_only)` | Open images with handle, label, owner and `mine` flag |
| `new_canvas` | Create a blank canvas; returns a handle |
| `open_image(file_path, label)` | Open a file; returns a handle |
| `set_active_image(image)` | Raise an image's window and make it current |
| `adopt_image(image, label)` | Claim an image opened by hand in GIMP |
| `close_image(image, save_first, force, reason)` | Close one image |
| `close_my_images(force)` | Close everything this session opened |
| `reseat_displays` | Take ownership of windows this server did not open |

### Identity, Approval & Messages
| Tool | Description |
|---|---|
| `set_session_name(name)` | Name this session so a person can recognise it |
| `request_elevation(reason)` | Ask the user, in a GIMP dialog, for administrator access |
| `elevation_status()` | Whether this session currently holds it |
| `revoke_elevation()` | Give it up again |
| `get_notifications()` | Collect messages left by other sessions |

### Checkpoints
| Tool | Description |
|---|---|
| `checkpoint(image, label, file_path)` | Save an XCF snapshot to roll back to |
| `restore_checkpoint(checkpoint, image)` | Roll back, keeping the same handle |

### Adjustments
| Tool | Description |
|---|---|
| `adjust_brightness_contrast` | Brightness and contrast |
| `adjust_curves` | Curves by channel (RGB/R/G/B/A) |
| `adjust_hue_saturation` | Hue, saturation, lightness |
| `adjust_color_balance` | Shadows/midtones/highlights color balance |
| `auto_levels` | Auto-stretch levels |
| `desaturate` | Convert to grayscale (keep RGB mode) |
| `invert_colors` | Invert all channels |
| `sharpen` | Unsharp mask sharpening |
| `blur` | Gaussian blur |
| `denoise` | Noise reduction |

### Transforms
| Tool | Description |
|---|---|
| `scale_image` | Scale to exact dimensions |
| `scale_to_fit` | Scale within bounding box (aspect-safe) |
| `crop_to_rect` | Crop to rectangle |
| `crop_to_selection` | Crop to the current selection |
| `rotate_image` | Rotate by an angle |
| `flip_image` | Flip horizontal or vertical |
| `resize_canvas` | Resize canvas without scaling content |
| `convert_color_mode` | RGB / GRAY / INDEXED |

### Selections
| Tool | Description |
|---|---|
| `select_rectangle` | Rectangular marquee |
| `select_ellipse` | Elliptical marquee |
| `select_by_color` | Select by color (global) |
| `select_all` / `select_none` | Select all / deselect |
| `invert_selection` | Invert selection |
| `modify_selection` | Grow, shrink, feather, or border |
| `get_selection_bounds` | Current selection bounds |

### Layers
| Tool | Description |
|---|---|
| `create_layer` | New empty layer |
| `duplicate_layer` | Duplicate a layer |
| `delete_layer` | Delete named layer |
| `rename_layer` | Rename layer |
| `set_layer_properties` | Opacity, blend mode, visibility |
| `reorder_layer` | Move layer in stack |
| `merge_visible_layers` | Flatten visible to one layer |
| `flatten_image` | Flatten all layers |
| `list_layers` | List all layers with properties |

### Drawing & Fill
| Tool | Description |
|---|---|
| `fill_layer` | Fill entire layer with color |
| `fill_selection` | Fill selection (foreground/background/transparent) |
| `fill_rectangle` | Fill a rectangle region |
| `fill_ellipse` | Fill an ellipse region |
| `draw_line` | Draw a line (pencil or paintbrush) |
| `draw_rectangle` | Draw a rectangle outline |
| `draw_ellipse` | Draw an ellipse outline |
| `gradient_fill` | Apply linear or radial gradient |
| `set_colors` | Set foreground/background colors |

### Text
| Tool | Description |
|---|---|
| `add_text` | Add a text layer |
| `edit_text` | Edit existing text layer |
| `list_fonts` | List available fonts |

### Filters & Effects
| Tool | Description |
|---|---|
| `apply_gaussian_blur` | Gaussian blur filter |
| `apply_pixelate` | Pixelate/mosaic effect |
| `apply_emboss` | Emboss effect |
| `apply_vignette` | Vignette darkening |
| `apply_noise` | Add noise/grain |
| `apply_drop_shadow` | Drop shadow effect |
| `warp_region` | Warp / liquify a region |

### Export
| Tool | Description |
|---|---|
| `export_image` | Export to PNG, JPEG, BMP, TIFF |
| `save_xcf` | Save as XCF, preserving layers |
| `batch_export(image, mine_only)` | Export several open images at once |
| `export_icon_sizes(source_image)` | Android / iOS icon size sets |
| `export_web_optimized` | Web-optimised JPEG and PNG |
| `export_sprite_sheet` | Sprite sheet from layers or images |
| `export_social_media_kit` | Per-platform social crops |
| `batch_resize` | Resize this session's open images |

> `batch_resize` and `export_sprite_sheet(source="images")` act on this session's images
> only, which in a shared GIMP is what you want.

### History
| Tool | Description |
|---|---|
| `checkpoint(image, label)` | Save a snapshot you can roll back to |
| `restore_checkpoint(checkpoint, image)` | Roll back, keeping the same handle |
| `undo` / `redo` | Always fail; see below |

> GIMP 3.x exposes no undo to plug-ins: there is no `gimp-image-undo`
> procedure, and `Gimp.Image` offers only undo *groups*. `undo`/`redo` are kept
> only so the reason is discoverable instead of looking like a missing feature.
> Take a `checkpoint()` before a destructive step and `restore_checkpoint()` to
> go back.

### Info & Context
| Tool | Description |
|---|---|
| `get_image_metadata` | Image size, mode, layers, filename |
| `get_gimp_info` | GIMP version, platform, capabilities |
| `get_context_state` | Current colors, brush, opacity, mode |
| `get_pixel_color` | Color value at a specific pixel |
| `get_histogram` | Histogram data for a channel |
| `check_server` / `restart_server` | Connection health |
| `call_api` | Run arbitrary Python-Fu in GIMP |

---

## AI Agent Feedback Loop

The `get_state_snapshot` tool enables a pattern where the AI loops until a goal is visually confirmed:

```text
┌─────────────┐
│  Apply edit │
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│ get_state_      │  ← AI sees live PNG, no disk save needed
│ snapshot()      │
└──────┬──────────┘
       │
       ▼
┌─────────────────┐     ┌──────────────────┐
│ Goal achieved?  │─ No─▶ Adjust & retry   │
└──────┬──────────┘     └──────────────────┘
       │ Yes
       ▼
┌─────────────┐
│   Export    │
└─────────────┘
```

### Example: Iterative Background Removal

See [`bg_remove_iterative.py`](bg_remove_iterative.py) for a complete example. The AI:

1. Removes the background using edge-seeded contiguous select
2. Takes a snapshot to check the result
3. Scans for remaining background-colored pixels
4. Runs targeted removal passes with progressively finer grids (25px → 1px)
5. Runs a final despeckle pass for isolated pixels
6. Loops until no background pixels remain

---

## Example Scripts

| Script | Description |
|---|---|
| [`tests/test_image_registry.py`](tests/test_image_registry.py) | 46 unit tests for handles, sessions and closing (no GIMP needed) |
| [`tests/audit_all_tools.py`](tests/audit_all_tools.py) | 111 checks across 85 of 87 commands (needs a live GIMP) |
| [`run_tests.py`](run_tests.py) | 60 end-to-end checks (needs a live GIMP) |
| [`tests/test_admin_flow_live.py`](tests/test_admin_flow_live.py) | Elevation end to end (needs a live GIMP **and** a human to click Grant) |
| [`bg_remove_iterative.py`](bg_remove_iterative.py) | Iterative BG removal with snapshot checkpoints |
| [`bg_remove.py`](bg_remove.py) | Simple single-pass background removal |
| [`agent_edit_demo.py`](agent_edit_demo.py) | Full pipeline: open → remove BG → edit expression → export |

```bash
python3 tests/test_image_registry.py    # 46 unit tests, no GIMP required
python3 tests/audit_all_tools.py        # 111 checks, needs GIMP + the server running
python3 run_tests.py                    # 60 checks, needs GIMP + the server running
python3 tests/test_admin_flow_live.py   # needs GIMP and a human to approve the dialog
```

---

## Technical Architecture

### Plugin ↔ Server Communication
```text
AI Client (Claude, etc.)
      │  MCP (stdio)
      ▼
gimp_mcp_server.py          ← MCP tool definitions, mints the session id
      │  TCP JSON  :9877
      ▼
gimp-mcp-plugin.py          ← Runs inside GIMP process, owns the image registry
      │  PyGObject
      ▼
GIMP 3.2 (gi.repository.Gimp)
```

- The MCP server translates tool calls into JSON commands sent to the plugin over TCP
- Every command carries a `_session` id, minted once per server process
- The plugin executes operations directly in the GIMP process via PyGObject
- Two message formats: `{"type": "...", "params": {...}}` for named tools, `{"cmds": ["python..."]}` for arbitrary exec

### How identity is stored

Each image the plugin opens gets a GIMP **parasite** named `gimp-mcp` holding
`{handle, session, label, origin, created}`. Parasites travel with the image and survive
a plugin restart, so handles keep working even if the socket server is restarted
underneath a running GIMP.

Display windows are tracked separately, in memory: GIMP offers `Gimp.Display.new()`,
`get_by_id()` and `delete()`, but no way to ask which image a display is showing. The
plugin therefore records the display id at the moment it creates the window, which is
what makes closing an image possible at all.

### Autostart

The plugin registers a persistent procedure — `Gimp.PDBProcType.PERSISTENT`, called
`EXTENSION` in GIMP 3.0 — which GIMP launches by itself at startup. It reads
`<gimp-config-dir>/mcp-server.json` and starts the socket server if `autostart` is true.

```json
{ "autostart": true, "port": 9877, "host": "localhost" }
```

### GIMP 3.2 Compatibility Notes

GIMP 3.x introduced breaking API changes from GIMP 2.x. Key fixes included in this release:

| Issue | Fix |
|---|---|
| `Gimp.get_displays()` does not exist | Track display ids from `Gimp.Display.new()`, close via `Gimp.Display.get_by_id(id).delete()` |
| `layer.copy(False)` → error | `layer.copy()` takes no args in GIMP 3.2 |
| `Gimp.text_fontname()` removed | Use PDB `gimp-text-fontname` |
| `gimp-blend` removed | Use GEGL `gegl:linear-gradient` / `gegl:radial-gradient` |
| `GimpDoubleArray` TypeError in curves | Use `drawable.curves_spline()` directly |
| `Gimp.fonts_get_list()` returns `Font` objects | Convert via `.get_name()` before JSON serialization |
| `image.select_none()` removed | Use PDB `gimp-selection-none` |
| `layer.get_pixel()` returns `Gegl.Color` | Use `.get_rgba()` to extract float components |
| `PDBProcType.EXTENSION` renamed | `PDBProcType.PERSISTENT` in 3.2; the plugin accepts either |

---

## Troubleshooting

### "Could not connect to GIMP"
- Confirm GIMP is running
- If autostart is off, start the server: **Tools > MCP > Start MCP Server**
- Check port 9877 is not blocked by a firewall
- `check_server()` reports the connection state and GIMP version

### The server does not start with GIMP
- Confirm `autostart` is `true` in `<gimp-config-dir>/mcp-server.json`
- Toggle it from **Tools > MCP > Toggle MCP Autostart** and restart GIMP
- Check **Filters > Script-Fu > Console** or GIMP's Error Console for startup messages

### Plugin Not Visible in GIMP
- Look under **Tools > MCP** (the plugin adds an `MCP` submenu, not a top-level entry)
- **Upgraded GIMP recently?** A minor upgrade (e.g. 3.0 → 3.2) moves the per-user config
  folder to a new version directory. Re-run the installer; it finds every version folder
  and installs into all of them.
- On Linux/macOS: ensure the file has execute permission (`chmod +x`)
- Restart GIMP after installation

### "No open image matches ..."
The handle, path or id you passed is not open. Call `list_images()` to see what is —
the error message also lists the open images and who owns them.

### "belongs to another MCP session ... not an administrator"
Working as intended. Another agent session opened that image. Either work within your
own images, or ask the user for access with
`request_elevation(reason="why you need it")`. Name your session first with
`set_session_name` so the approval dialog identifies you.

### The plugin dies at `import gi` when GIMP starts
GIMP ran the plug-in through its shebang and got a `python3` without PyGObject — a nix,
pyenv, conda or virtualenv interpreter earlier on GIMP's `PATH`. Re-run the installer,
which pins an absolute interpreter that can `import gi`, or point it at one:
`GIMP_MCP_PYTHON=/usr/bin/python3 ./install.sh --source .`

### GIMP hangs on startup with autostart enabled, and no image will open
A persistent procedure must call `procedure.persistent_ready()` once its socket is up
and *before* entering the GLib main loop. Without it GIMP never finishes starting: the
GUI's image managers are never built, and every `Gimp.Display.new()` fails with
"constructor returned NULL". If you have modified the plugin's startup path, check that
call is still there.

### "This session has no image open, and N images belong to other sessions"
Another agent session is using this GIMP. Pass `image=<handle>` explicitly, or open your
own image. This is a guard, not a failure: the server refuses to guess which of someone
else's images you meant.

### close_image says the window is not ours
The image was opened by hand in GIMP, or by a different server process, so no display id
was recorded for it. Either close it in the GIMP window, or retry with `force=True`,
which reseats every open image onto a fresh window first.

### Debug Mode
```bash
GIMP_MCP_DEBUG=1 uv run --directory /path/to/gimp-mcp gimp_mcp_server.py
```

---

## Example Output

<img src="gimp-screenshot1.png" alt="GIMP MCP Example" width="400">

*"Draw me a face and a sheep" — generated entirely through natural language via GIMP MCP*

---

## Future Enhancements

- **Recipe collection**: reusable workflow templates (portrait cleanup, product photo, etc.)
- **Dynamic discovery**: auto-generate MCP tools from GIMP's full PDB procedure database
- **Security**: sandboxed execution for untrusted command inputs
- **Performance**: optimized bitmap transfer for large images
- **Remote access**: network-accessible GIMP instances

---

## Contributing

Contributions are welcome — bug fixes, new tools, documentation, or example scripts. Open a PR or issue on GitHub.

### Development Setup

Install dev dependencies and activate the pre-commit hook so `ruff` runs on every commit:

```bash
uv sync
uv run pre-commit install
```

After this, `ruff` checks staged files on each `git commit` (with `--fix` applied automatically). The same check runs in CI, so the hook is just a fast local safety net.

To bump the pinned hook versions later:

```bash
uv run pre-commit autoupdate
```

## Telling your agent about the server

Installing the GIMP plug-in is only half the job: the agent still has to know
the MCP server exists. The installer offers to do that for whichever of these
it finds on the machine:

| Agent | Config it writes |
|---|---|
| Claude Code | `claude mcp add`, or `~/.claude.json` if the CLI is absent |
| Claude Desktop | `claude_desktop_config.json` |
| Codex | `~/.codex/config.toml` |
| opencode | `~/.config/opencode/opencode.json` |
| Cline | `cline_mcp_settings.json` |

The server itself is installed to `~/.local/share/gimp-mcp/`, outside any git
checkout, so moving or deleting the repository does not break the agents.

Existing entries are left alone and every file is backed up before it is
touched; a config that is not valid JSON is reported and skipped rather than
overwritten. Running it again is a no-op when the entry is already correct.

Do it separately, or check first what would be written:

```bash
python3 tools/register_mcp.py --list                 # what was detected
python3 tools/register_mcp.py --server ~/.local/share/gimp-mcp/gimp_mcp_server.py
python3 tools/register_mcp.py --remove               # take it back out
```

Where `uv` is available the entry runs the server with `uv run --with mcp
--with fastmcp`, so the dependencies resolve per-run and nothing has to be
installed globally. Without `uv` it uses plain `python3` and tells you to
`pip install mcp fastmcp`.

Restart the agent afterwards; none of them re-read their MCP config live.

## Full tool reference

[docs/CAPABILITIES.md](docs/CAPABILITIES.md) documents all 90 tools — signature,
purpose, parameters and return shape — grouped by what they are for. It is
generated from the server source by `tools/gen_capabilities.py`, and a
pre-commit hook fails if it drifts, so it cannot disagree with the code.

Point an agent at that file if it needs the whole surface; the sections above
cover the parts that change how you should work rather than what is available.

## License and copyright

GNU General Public License v3.0 or later. The full text is in [LICENSE](LICENSE),
kept verbatim as the GPL requires.

    Copyright (C) 2025 Maor <maor80-opensource@yahoo.com>
    Copyright (C) 2025 Tomer Konforty <tomer.konforty@arkhivist.io>
    Copyright (C) 2026 tschallacka <tschallacka@outlook.com>

Everyone who has contributed is listed in [AUTHORS](AUTHORS). This project began
as a fork of https://github.com/maorcc/gimp-mcp and now continues independently.
