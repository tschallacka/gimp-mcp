# Capabilities

Everything an agent can do through this MCP server, generated from
`gimp_mcp_server.py` so it cannot drift from the code.

Regenerate after changing any tool:

```bash
python3 tools/gen_capabilities.py
```

**90 tools** across 15 groups, over 87 plugin commands.

## Before anything else

Three things decide whether an agent works smoothly here or fights the
tools. They are covered in full in the sections below, but in short:

1. **Address images by handle, never by position.** `new_canvas` and
   `open_image` return a `handle`; pass it as `image=`. A file path or
   basename works too. Omit `image` to act on the image you touched last.
   The list of open images reorders whenever any session opens or closes
   one, which is why there is no positional index any more.
2. **One GIMP may be shared by several sessions.** You can only reach
   images you opened. Someone else's are refused, not silently retargeted.
3. **There is no undo.** GIMP 3.x exposes none to plug-ins. Take a
   `checkpoint()` before anything destructive.

## Contents

- [Creating and inspecting images](#creating-and-inspecting-images) — 6 tools
- [Sessions, identity and images](#sessions-identity-and-images) — 7 tools
- [Administrator access](#administrator-access) — 4 tools
- [Checkpoints (undo does not exist in GIMP 3.x)](#checkpoints-undo-does-not-exist-in-gimp-3x) — 4 tools
- [Server and escape hatch](#server-and-escape-hatch) — 3 tools
- [Color & Paint](#color--paint) — 9 tools
- [Export Pipelines](#export-pipelines) — 6 tools
- [File Operations](#file-operations) — 4 tools
- [Filters & Effects](#filters--effects) — 6 tools
- [Image Adjustments](#image-adjustments) — 10 tools
- [Layer Operations](#layer-operations) — 9 tools
- [Resize & Transform](#resize--transform) — 7 tools
- [Selections](#selections) — 7 tools
- [Text](#text) — 3 tools
- [Utility](#utility) — 5 tools

## Creating and inspecting images

| Tool | What it does |
|---|---|
| [`new_canvas`](#new_canvas) | Create a new blank canvas in GIMP and open it in a display window. |
| [`get_state_snapshot`](#get_state_snapshot) | Return a live visual snapshot of the current image state — no file save needed. |
| [`get_image_bitmap`](#get_image_bitmap) | Get the current open image in GIMP as an Image object with optional scaling and region selection. |
| [`get_image_metadata`](#get_image_metadata) | Get metadata about the current open image in GIMP without the bitmap data. |
| [`get_context_state`](#get_context_state) | Get the current GIMP context state (colors, brush, settings). |
| [`get_gimp_info`](#get_gimp_info) | Get comprehensive information about the GIMP installation and environment. |

### `new_canvas`

```python
new_canvas(width: int, height: int, name: str = 'Untitled', color_mode: str = 'RGB', fill: str = 'white', resolution: int = 72)
```

Create a new blank canvas in GIMP and open it in a display window.

Parameters:
- width: Canvas width in pixels
- height: Canvas height in pixels
- name: Layer/image name (default: "Untitled")
- color_mode: "RGB" (default), "RGBA", "GRAY", "GRAYA"
- fill: Fill color for the background layer. Any CSS color name or
        hex string: "white" (default), "black", "transparent",
        "#FF5733", "rgb(100,200,50)", etc.
- resolution: DPI resolution (default: 72)

Examples:
- new_canvas(1024, 1024) — white 1024x1024 RGB canvas
- new_canvas(1920, 1080, name="Background", fill="black")
- new_canvas(512, 512, color_mode="RGBA", fill="transparent")

Returns: - handle: stable identifier to pass as `image` to other tools - image_id: internal GIMP image ID - label: the name you gave, also usable as a lookup key - width / height: confirmed dimensions - color_mode: confirmed mode - display_opened: whether a GIMP window was opened

### `get_state_snapshot`

```python
get_state_snapshot(image: str | int | None = None, max_size: int = 512, region: dict | None = None, label: str = '')
```

Return a live visual snapshot of the current image state — no file save needed.

AI agents call this to get immediate visual feedback after any edit operation,
letting them verify results and decide next steps without saving to disk.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- max_size: Maximum width/height of the returned preview in pixels (default: 512)
- region: Optional dict {x, y, width, height} to zoom into a specific area
          e.g. {"x": 200, "y": 300, "width": 100, "height": 80} for mouth area
- label: Optional annotation label (logged but not drawn — for agent bookkeeping)

Typical agent workflow:
    1. open_image / new_canvas
    2. <edit operations>
    3. get_state_snapshot()          ← see result, decide next step
    4. <more edits>
    5. get_state_snapshot(region={"x":200,"y":300,"width":100,"height":80})
    6. export_image when satisfied

Returns: - PNG image of the current GIMP canvas state (with alpha if present)

### `get_image_bitmap`

```python
get_image_bitmap(max_width: int | None = None, max_height: int | None = None, region: dict | None = None)
```

Get the current open image in GIMP as an Image object with optional scaling and region selection.

No size restrictions — pass any max_width/max_height you need.
For large images, omit max_width/max_height to get the full resolution.

Supports two main use cases:
1. Full image with optional scaling (pass max_width/max_height)
2. Region extraction with optional scaling (pass region dict)

Parameters:
- max_width, max_height: Target dimensions for scaling (aspect-ratio preserved).
  Omit for full resolution.
- region: Dictionary with keys:
    - origin_x, origin_y: Top-left corner of region to extract
    - width, height: Dimensions of region to extract
    - max_width, max_height: Optional scaling for the extracted region

Examples:
- Full image at full res: get_image_bitmap()
- Full image scaled: get_image_bitmap(max_width=2048, max_height=2048)
- Region: get_image_bitmap(region={"origin_x": 0, "origin_y": 0, "width": 512, "height": 512})

The returned Image object automatically handles base64 encoding and MIME types
according to the Model Context Protocol specification.

Returns: - Image object containing PNG data in MCP-compliant format - Includes width, height, and base64-encoded image data

### `get_image_metadata`

```python
get_image_metadata()
```

Get metadata about the current open image in GIMP without the bitmap data.

Returns detailed information about the currently active image including:
- Image dimensions (width, height)
- Color mode and base type
- Number of layers and channels
- File information if available
- Layer structure and properties

This is much faster than get_image_bitmap() since it doesn't export the actual image data.
Perfect for when you only need to know image properties for decision making.

Returns detailed information about the currently active image including: - Image dimensions (width, height) - Color mode and base type - Number of layers and channels - File information if available - Layer structure and properties

### `get_context_state`

```python
get_context_state()
```

Get the current GIMP context state (colors, brush, settings).

IMPORTANT: Context state can be changed by the user in GIMP UI at any time.
Check context state before operations that depend on specific settings.

Returns information about:
- Foreground and background colors (RGB/RGBA values)
- Current brush and its properties
- Opacity setting (0-100%)
- Paint/blend mode
- Feather state and radius
- Antialiasing state

Use cases:
- Verify colors before drawing operations
- Check if feathering is enabled (avoid unwanted blurry edges)
- Ensure correct opacity and blend mode
- Detect if user changed settings in GIMP UI

Returns information about: - Foreground and background colors (RGB/RGBA values) - Current brush and its properties - Opacity setting (0-100%) - Paint/blend mode - Feather state and radius - Antialiasing state

### `get_gimp_info`

```python
get_gimp_info()
```

Get comprehensive information about the GIMP installation and environment.

Returns detailed information about GIMP that AI assistants need to understand
the current environment, including:
- GIMP version and build information
- Installation paths and directories
- Available plugins and procedures
- System configuration
- Runtime environment details

This information helps AI assistants provide better support and troubleshooting
by understanding the specific GIMP setup they're working with.

Returns detailed information about GIMP that AI assistants need to understand the current environment, including: - GIMP version and build information - Installation paths and directories - Available plugins and procedures - System configuration - Runtime environment details

## Sessions, identity and images

| Tool | What it does |
|---|---|
| [`session_info`](#session_info) | Report what this session owns in GIMP and what it will act on next. |
| [`set_session_name`](#set_session_name) | Give this session a name a person will recognise. |
| [`list_images`](#list_images) | List images open in GIMP, marking which ones belong to this session. |
| [`set_active_image`](#set_active_image) | Raise a specific image to the front / make it active in GIMP. |
| [`adopt_image`](#adopt_image) | Claim an image that was opened by hand in GIMP, giving it a handle. |
| [`close_my_images`](#close_my_images) | Close every image this session opened, leaving other sessions' alone. |
| [`reseat_displays`](#reseat_displays) | Take ownership of every open image's window so they can all be closed. |

### `session_info`

```python
session_info()
```

Report what this session owns in GIMP and what it will act on next.

Use this to orient yourself at the start of a task, or whenever a tool
reports an ambiguous image. GIMP may be shared with other sessions; only
the images under `my_images` are yours to edit or close.

Returns: - session: this session's id - current: image_id used when a tool's `image` argument is omitted - my_images / my_count: images this session opened - other_images / other_count: images belonging to others, or untracked - total_open: images open in GIMP overall

### `set_session_name`

```python
set_session_name(name: str)
```

Give this session a name a person will recognise.

Nothing in the MCP handshake tells the GIMP plugin who is connected, so by
default a session shows up as its id plus the working directory. Set a name
and it appears wherever the session does: in list_images, in session_info,
and -- the reason it matters -- in the dialog asking the user to approve
administrator access. A user who cannot tell which agent is asking cannot
reasonably approve it.

Worth calling once at the start of a task. Keep it short and specific:
"icon export for acme-web" beats "Claude".

Parameters:
- name: How to describe this session to the user

Returns: {session, name, cwd, host, pid}

### `list_images`

```python
list_images(mine_only: bool = False)
```

List images open in GIMP, marking which ones belong to this session.

One GIMP can be shared by several sessions at once, so this reports
ownership rather than a bare list. Address images by `handle`, never by
position: the list reorders as images open and close.

Parameters:
- mine_only: If True, list only images this session opened (default False)

Returns: - images: list of {handle, image_id, label, name, width, height, color_mode, num_layers, file_path, is_dirty, session, origin, mine, tracked} - count: images returned - total_open: images open in GIMP overall - session: this session's id - current: image_id this session will act on when you omit `image`

### `set_active_image`

```python
set_active_image(image: str | int)
```

Raise a specific image to the front / make it active in GIMP.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `adopt_image`

```python
adopt_image(image: str | int, label: str | None = None)
```

Claim an image that was opened by hand in GIMP, giving it a handle.

An image opened through GIMP's own File > Open has no handle and belongs to
nobody. Adopting it assigns a handle and marks it as this session's, so the
rest of the tools can address it and close_my_images will clean it up.

Parameters:
- image: The image to claim, by image_id, file path or GIMP name
  (see list_images for what is open)
- label: Optional friendly name; defaults to the file's base name

Returns the adopted image's summary, including its new handle.

Returns the adopted image's summary, including its new handle.

### `close_my_images`

```python
close_my_images(force: bool = False)
```

Close every image this session opened, leaving other sessions' alone.

The right way to clean up at the end of a task. Images opened by another
session, or by hand in the GIMP window, are never touched.

Parameters:
- force: Also close images whose window this server did not create. This
  reseats every open image onto a fresh window first: nothing is lost, but
  window position and zoom are reset for all of them.

Returns: {session, closed, closed_count, failed, failed_count, remaining_open}

### `reseat_displays`

```python
reseat_displays()
```

Take ownership of every open image's window so they can all be closed.

GIMP offers no way to look up which window shows which image, so this
server can only close windows it opened itself. This recreates one window
per open image and records it, making every image closable.

No image is lost -- each gets its new window before any old one is removed
-- but window position and zoom are reset for all of them, so only run it
when you actually need to close an image this server did not open.

Returns: {tracked_before, tracked_after, images}

## Administrator access

| Tool | What it does |
|---|---|
| [`request_elevation`](#request_elevation) | Ask the user, in GIMP, to grant this session administrator access. |
| [`elevation_status`](#elevation_status) | Report whether this session currently holds administrator access. |
| [`revoke_elevation`](#revoke_elevation) | Give up this session's administrator access. |
| [`get_notifications`](#get_notifications) | Collect messages left for this session by other sessions or the user. |

### `request_elevation`

```python
request_elevation(reason: str)
```

Ask the user, in GIMP, to grant this session administrator access.

By default a session can only touch images it opened itself; naming another
session's image is refused. Administrator access lifts that, letting this
session edit and close images belonging to every other MCP session sharing
this GIMP.

This puts a dialog on the user's screen in GIMP and blocks until they
answer, so only call it when you actually need another session's images,
and say plainly why. If they deny it, work within your own images rather
than asking again.

Parameters:
- reason: Why you need it. Shown verbatim in the approval dialog, so write
  it for the user, e.g. "clean up 6 stale canvases left by a crashed run".

Returns {elevated, already, session, reason} on success.
Raises if the user denies it, does not answer, or the dialog cannot open.

Returns {elevated, already, session, reason} on success. Raises if the user denies it, does not answer, or the dialog cannot open.

### `elevation_status`

```python
elevation_status()
```

Report whether this session currently holds administrator access.

Returns: {session, elevated, granted_at, reason, admin_sessions}

### `revoke_elevation`

```python
revoke_elevation()
```

Give up this session's administrator access.

Do this as soon as the task that needed it is finished, so a later mistake
cannot reach another session's images.

Returns: {session, was_elevated, elevated}

### `get_notifications`

```python
get_notifications()
```

Collect messages left for this session by other sessions or the user.

The main case is an administrator closing an image of yours: you get a
notification naming the image and the reason they gave. Notifications also
ride along on other tool results, so you usually see them without asking;
call this to check explicitly, for instance if an image you expected has
vanished. Collecting them clears the queue.

Returns: {notifications, count}

## Checkpoints (undo does not exist in GIMP 3.x)

| Tool | What it does |
|---|---|
| [`checkpoint`](#checkpoint) | Save a snapshot of an image that restore_checkpoint can roll back to. |
| [`restore_checkpoint`](#restore_checkpoint) | Roll an image back to a saved checkpoint. |
| [`undo`](#undo) | Always fails. GIMP 3.x exposes no undo to plug-ins; use checkpoint(). |
| [`redo`](#redo) | Always fails. GIMP 3.x exposes no redo to plug-ins; use checkpoint(). |

### `checkpoint`

```python
checkpoint(image: str | int | None = None, label: str = 'checkpoint', file_path: str | None = None)
```

Save a snapshot of an image that restore_checkpoint can roll back to.

GIMP 3.x exposes no undo to plug-ins at all, so this is how you make a
risky edit reversible. Take one before a destructive step (flatten, scale
down, colour-mode change) and you can get the earlier state back.

Parameters:
- image: Which image to snapshot (handle, image_id, path, or label).
  Omit for this session's current image.
- label: Short name for the checkpoint, used in the filename
- file_path: Where to write the .xcf; defaults to a temp file

Returns: {checkpoint, handle, image_id, label, bytes}

### `restore_checkpoint`

```python
restore_checkpoint(checkpoint: str, image: str | int | None = None)
```

Roll an image back to a saved checkpoint.

The current image is closed and the checkpoint loaded in its place, keeping
the same handle, so references you already hold keep working. The image_id
changes; the handle does not.

Parameters:
- checkpoint: Path returned by checkpoint()
- image: Which image to replace (handle, image_id, path, or label).
  Omit for this session's current image.

Returns: {restored_from, handle, image_id, note}

### `undo`

```python
undo(steps: int = 1, image: str | int | None = None)
```

> **Always fails. GIMP 3.x exposes no undo to plug-ins; use checkpoint().**

Not available: GIMP 3.x exposes no undo to plug-ins.

The PDB has no gimp-image-undo procedure and Gimp.Image offers only undo
*groups*, so this cannot be implemented. Use checkpoint() before a risky
edit and restore_checkpoint() to go back, or close the image without
saving. Calling this always fails; it is kept so the reason is discoverable
rather than looking like a missing feature.

Parameters:
- steps: Number of undo steps (default 1)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {steps_undone}

### `redo`

```python
redo(steps: int = 1, image: str | int | None = None)
```

> **Always fails. GIMP 3.x exposes no redo to plug-ins; use checkpoint().**

Not available: GIMP 3.x exposes no redo to plug-ins.

The PDB has no gimp-image-redo procedure and Gimp.Image offers only undo
*groups*, so this cannot be implemented. Use checkpoint() before a risky
edit and restore_checkpoint() to go back, or close the image without
saving. Calling this always fails; it is kept so the reason is discoverable
rather than looking like a missing feature.

Parameters:
- steps: Number of redo steps (default 1)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {steps_redone}

## Server and escape hatch

| Tool | What it does |
|---|---|
| [`check_server`](#check_server) | Check whether the GIMP MCP plugin socket is reachable and responding. |
| [`restart_server`](#restart_server) | Drop and re-establish the connection to the GIMP MCP plugin. |
| [`call_api`](#call_api) | Call GIMP 3.2 API methods through PyGObject console. |

### `check_server`

```python
check_server()
```

Check whether the GIMP MCP plugin socket is reachable and responding.

Returns a status dict:
- connected: bool
- host / port: where it tried
- gimp_version: if connected successfully
- error: description if not connected

Use this before any other operation to verify the GIMP plugin is running.
If not connected, open GIMP and run Tools > Start MCP Server.

Returns a status dict: - connected: bool - host / port: where it tried - gimp_version: if connected successfully - error: description if not connected

### `restart_server`

```python
restart_server()
```

Drop and re-establish the connection to the GIMP MCP plugin.

Use this when:
- GIMP was restarted after Claude Code was already running
- The socket connection dropped mid-session
- check_server() shows not connected but GIMP is open

Returns the new connection status (same format as check_server).

Returns the new connection status (same format as check_server).

### `call_api`

```python
call_api(api_path: str, args: list = [], kwargs: dict = {})
```

Call GIMP 3.2 API methods through PyGObject console.

GIMP MCP Protocol:
- Use api_path="exec" to execute Python code in GIMP
- args[0] should be "pyGObject-console" for executing commands
- args[1] should be array of Python code strings to execute
- Commands execute in persistent context - imports and variables persist
- Always call Gimp.displays_flush() after drawing operations

For image operations, use get_image_bitmap()
which return proper MCP Image objects that Claude can process directly.

GUIDANCE PROMPTS:
- For common operations and best practices, invoke the 'gimp_best_practices' prompt
- For complex multi-element drawings with layers, invoke the 'gimp_iterative_workflow' prompt

Optional Initialization Pattern:
["images = Gimp.get_images()", "image1 = images[0]",
 "layers = image1.get_layers()", "layer1 = layers[0]", "drawable1 = layer1"]

Common Operations:
- Draw line: ["Gimp.pencil(drawable1, [0, 0, 200, 200])", "Gimp.displays_flush()"]
- Set color: ["from gi.repository import Gegl", "red_color = Gegl.Color.new('red')", 
              "Gimp.context_set_foreground(red_color)"]
- Draw ellipse: ["Gimp.Image.select_ellipse(image1, Gimp.ChannelOps.REPLACE, 100, 100, 30, 20)",
                 "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.FOREGROUND)",
                 "Gimp.Selection.none(image1)", "Gimp.displays_flush()"]
- Paint curve: ["Gimp.paintbrush_default(drawable1, [50.0, 50.0, 150.0, 200.0, 250.0, 50.0, 350.0, 200.0])", 
                "Gimp.displays_flush()"]
- Draw bezier curve: ["path = Gimp.Path.new(image1, 'my_bezier_path')", 
                      "image1.insert_path(path, None, 0)",
                      "stroke_id = path.bezier_stroke_new_moveto(100, 100)",
                      "path.bezier_stroke_cubicto(stroke_id, 150, 50, 250, 150, 300, 100)",
                      "Gimp.Drawable.edit_stroke_item(drawable1, path)",
                      "Gimp.Selection.none(image1)", "Gimp.displays_flush()"]
- Get open filenames: ["print([x.get_file().get_path() for x in Gimp.get_images()])"]
- Copy layer between images: ["image1 = Gimp.get_images()[0]", "image2 = Gimp.get_images()[1]",
                              "width = image1.get_width()", "height = image1.get_height()",
                              "image1.select_rectangle(Gimp.ChannelOps.REPLACE, 0, 0, width, height)",
                              "image1_layers = image1.get_selected_layers()", "drawable = image1_layers[0]",
                              "Gimp.edit_copy([drawable])", "image2_layers = image2.get_layers()",
                              "target_drawable = image2_layers[0]", "floating_sel = Gimp.edit_paste(target_drawable, True)[0]",
                              "Gimp.floating_sel_anchor(floating_sel)", "Gimp.displays_flush()"]
- New image: ["image1 = Gimp.Image.new(350, 800, Gimp.ImageBaseType.RGB)",
              "layer1 = Gimp.Layer.new(image1, 'Background', 350, 800, Gimp.ImageType.RGB_IMAGE, 100, Gimp.LayerMode.NORMAL)",
              "image1.insert_layer(layer1, None, 0)", "drawable1 = layer1",
              "white_color = Gegl.Color.new('white')", "Gimp.context_set_background(white_color)",
              "Gimp.Drawable.edit_fill(drawable1, Gimp.FillType.BACKGROUND)", "Gimp.Display.new(image1)"]

Important Tips:
- When filling layers with color, ensure layer has alpha channel using Gimp.Layer.add_alpha()
- Use Gimp.Drawable.fill() for reliable full-layer fills
- Specify colors precisely with rgb(R, G, B) or rgba(R, G, B, A) to avoid transparency issues
- After drawing operations, always call Gimp.displays_flush()
- After selection operations for drawing, unselect with Gimp.Selection.none(image1)

GIMP 3.2 API Changes:
- Use Gimp.get_images() instead of deprecated Gimp.list_images()
- Use image.get_layers() instead of Gimp.get_active_layer()
- gimpfu module not available in GIMP 3.2
- Colors created with Gegl.Color.new('color_name')
- Full API documentation: https://developer.gimp.org/api/3.0/libgimp/

Parameters:
- api_path: Use "exec" for Python execution
- args: ["pyGObject-console", ["python_code_array"]] or ["pyGObject-eval", ["expression"]]
- kwargs: Dictionary of keyword arguments (rarely used)

Returns: - JSON string of the result or error message

## Color & Paint

| Tool | What it does |
|---|---|
| [`draw_ellipse`](#draw_ellipse) | Draw an ellipse outline (stroke only) on a layer. |
| [`draw_line`](#draw_line) | Draw a straight line on a layer. |
| [`draw_rectangle`](#draw_rectangle) | Draw a rectangle outline (stroke only) on a layer. |
| [`fill_ellipse`](#fill_ellipse) | Fill an elliptical region with a solid color. |
| [`fill_layer`](#fill_layer) | Fill an entire layer with a solid color. |
| [`fill_rectangle`](#fill_rectangle) | Fill a rectangular region with a solid color. |
| [`fill_selection`](#fill_selection) | Fill the current selection with a color or fill type. |
| [`gradient_fill`](#gradient_fill) | Fill a layer or selection with a gradient. |
| [`set_colors`](#set_colors) | Set the GIMP foreground and/or background color. |

### `draw_ellipse`

```python
draw_ellipse(x: int, y: int, width: int, height: int, color: str | None = None, line_width: float = 2.0, layer_name: str | None = None, image: str | int | None = None)
```

Draw an ellipse outline (stroke only) on a layer.

Parameters:
- x, y: Top-left corner of the bounding box
- width, height: Bounding box dimensions
- color: Stroke color; uses current foreground if omitted
- line_width: Stroke width in pixels (default 2.0)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `draw_line`

```python
draw_line(x1: float, y1: float, x2: float, y2: float, color: str | None = None, width: float = 2.0, tool: str = 'pencil', layer_name: str | None = None, image: str | int | None = None)
```

Draw a straight line on a layer.

Parameters:
- x1, y1: Start point
- x2, y2: End point
- color: Stroke color (CSS / hex / rgb); uses current foreground if omitted
- width: Stroke width in pixels (default 2.0)
- tool: "pencil" (default, hard edge) or "paintbrush" (soft edge)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `draw_rectangle`

```python
draw_rectangle(x: int, y: int, width: int, height: int, color: str | None = None, line_width: float = 2.0, layer_name: str | None = None, image: str | int | None = None)
```

Draw a rectangle outline (stroke only) on a layer.

Parameters:
- x, y: Top-left corner
- width, height: Rectangle dimensions
- color: Stroke color; uses current foreground if omitted
- line_width: Stroke width in pixels (default 2.0)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `fill_ellipse`

```python
fill_ellipse(x: int, y: int, width: int, height: int, color: str, layer_name: str | None = None, image: str | int | None = None)
```

Fill an elliptical region with a solid color.

Parameters:
- x, y: Top-left corner of the bounding box
- width, height: Bounding box dimensions
- color: Fill color (CSS name, hex, or rgb() string)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `fill_layer`

```python
fill_layer(color: str, layer_name: str | None = None, image: str | int | None = None)
```

Fill an entire layer with a solid color.

Parameters:
- color: Fill color as CSS name, hex, or rgb() string
- layer_name: Layer to fill; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `fill_rectangle`

```python
fill_rectangle(x: int, y: int, width: int, height: int, color: str, layer_name: str | None = None, image: str | int | None = None)
```

Fill a rectangular region with a solid color.

Parameters:
- x, y: Top-left corner
- width, height: Rectangle dimensions
- color: Fill color (CSS name, hex, or rgb() string)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `fill_selection`

```python
fill_selection(color: str | None = None, fill_type: str | None = None, image: str | int | None = None, layer_name: str | None = None)
```

Fill the current selection with a color or fill type.

Parameters:
- color: Fill color as CSS name, hex, or rgb() string (used when fill_type is omitted)
- fill_type: Fill type override: "foreground", "background", or "transparent"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Target layer; defaults to active layer

Returns status dict.

Returns status dict.

### `gradient_fill`

```python
gradient_fill(color1: str = 'black', color2: str = 'white', x1: float = 0, y1: float = 0, x2: float | None = None, y2: float | None = None, gradient_type: str = 'linear', layer_name: str | None = None, image: str | int | None = None)
```

Fill a layer or selection with a gradient.

Parameters:
- color1: Start color (default "black")
- color2: End color (default "white")
- x1, y1: Gradient start point (default top-left 0,0)
- x2, y2: Gradient end point (defaults to bottom-right of image)
- gradient_type: "linear" (default) or "radial"
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `set_colors`

```python
set_colors(foreground: str | None = None, background: str | None = None)
```

Set the GIMP foreground and/or background color.

Parameters:
- foreground: New foreground color (CSS name, hex, rgb()); omit to leave unchanged
- background: New background color; omit to leave unchanged

Returns: {foreground, background} confirmation dict.

## Export Pipelines

| Tool | What it does |
|---|---|
| [`batch_resize`](#batch_resize) | Resize every image this session has open, to a common target size. |
| [`export_icon_sizes`](#export_icon_sizes) | Export an image as a complete icon set for Android or iOS. |
| [`export_social_media_kit`](#export_social_media_kit) | Export an image resized for multiple social media platforms. |
| [`export_sprite_sheet`](#export_sprite_sheet) | Combine multiple frames into a sprite sheet PNG. |
| [`export_web_optimized`](#export_web_optimized) | Export an image as both JPEG and PNG, choosing the smaller format. |
| [`warp_region`](#warp_region) | Warp / liquify a region of the image by pushing pixels in a direction. |

### `batch_resize`

```python
batch_resize(width: int | None = None, height: int | None = None, scale_factor: float | None = None, maintain_aspect: bool = True, all_images: bool = False)
```

Resize every image this session has open, to a common target size.

Scoped to your own images by default. One GIMP can be shared by several
sessions, and resizing another session's work is not recoverable.

Parameters:
- width / height: Target dimensions in pixels (provide one or both)
- scale_factor: Proportional scale (e.g. 0.5 = 50%); overrides width/height if set
- maintain_aspect: Preserve aspect ratio when only one dimension is given (default True)
- all_images: Also resize images belonging to other sessions and images
  opened by hand in GIMP. Rarely what you want; check list_images() first.

Returns: {results: [{image_id, old_width, old_height, new_width, new_height}], count}

### `export_icon_sizes`

```python
export_icon_sizes(output_dir: str, platform: str = 'android', source_image: str | int | None = None, format: str = 'png')
```

Export an image as a complete icon set for Android or iOS.

Android sizes: 48 (mdpi), 72 (hdpi), 96 (xhdpi), 144 (xxhdpi),
               192 (xxxhdpi), 512 (Play Store)
iOS sizes: 20x1/2/3, 29x1/2/3, 40x2/3, 60x2/3, 76x1/2, 83.5x2, 1024x1

Parameters:
- output_dir: Directory to write icon files into
- platform: "android" (default) or "ios"
- source_image: Source image handle, image_id, file path or label
  (default: this session's current image)
- format: Output format — "png" (default)

Returns: {exported: [{size, file_path}], count, platform}

### `export_social_media_kit`

```python
export_social_media_kit(output_dir: str, platforms: list | None = None, image: str | int | None = None)
```

Export an image resized for multiple social media platforms.

Platform sizes (all in pixels):
- instagram_square: 1080x1080
- instagram_story: 1080x1920
- twitter_header: 1500x500
- facebook_cover: 820x312
- youtube_thumbnail: 1280x720

Parameters:
- output_dir: Directory to write output files
- platforms: List of platform names to export (omit for all five)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {exported: [{platform, file_path, width, height}], count}

### `export_sprite_sheet`

```python
export_sprite_sheet(output_path: str, columns: int | None = None, padding: int = 0, source: str = 'layers', image: str | int | None = None, all_images: bool = False)
```

Combine multiple frames into a sprite sheet PNG.

Parameters:
- output_path: Absolute path for the output PNG file
- columns: Number of columns in the grid (defaults to square root of frame count)
- padding: Pixel gap between frames (default 0)
- source: "layers" (each layer is a frame; default) or "images", which uses
  this session's open images as frames
- all_images: With source="images", also include images belonging to other
  sessions. Rarely what you want in a shared GIMP.
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {file_path, columns, rows, frame_width, frame_height, count}

### `export_web_optimized`

```python
export_web_optimized(output_dir: str, jpeg_quality: int = 85, png_compression: int = 9, max_width: int | None = None, max_height: int | None = None, image: str | int | None = None)
```

Export an image as both JPEG and PNG, choosing the smaller format.

Parameters:
- output_dir: Directory to write output files
- jpeg_quality: JPEG quality 1-100 (default 85)
- png_compression: PNG compression level 0-9 (default 9)
- max_width / max_height: Optional scaling before export
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {jpeg_path, jpeg_size, png_path, png_size, recommendation}

### `warp_region`

```python
warp_region(vectors: list, image: str | int | None = None, layer_name: str | None = None)
```

Warp / liquify a region of the image by pushing pixels in a direction.

Uses GEGL warp (GIMP 3 native) with plug-in-iwarp fallback. Ideal for
subtle facial expression edits — e.g. turning a neutral mouth into a smile
by pushing the mouth corners upward.

Parameters:
- vectors: List of warp stroke dicts, each with:
    - x, y      : center of the warp influence (pixels)
    - dx, dy    : push direction — negative dy = push upward
    - radius    : influence radius in pixels (default: 40)
    - amount    : deform strength 0–1 (default: 0.3)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Target layer; omit to use the active/top layer

Examples — make a character smile:
    warp_region(vectors=[
        {"x": 215, "y": 355, "dx":  5, "dy": -8, "radius": 18, "amount": 0.45},
        {"x": 295, "y": 355, "dx": -5, "dy": -8, "radius": 18, "amount": 0.45},
        {"x": 255, "y": 370, "dx":  0, "dy": -4, "radius": 22, "amount": 0.30},
    ])

Returns: {"warped_vectors": N}

## File Operations

| Tool | What it does |
|---|---|
| [`batch_export`](#batch_export) | Export all open images (or a specific one) to a directory. |
| [`export_image`](#export_image) | Export the current image to a raster file (PNG, JPEG, WEBP, TIFF). |
| [`open_image`](#open_image) | Open an image file in GIMP and create a display window. |
| [`save_xcf`](#save_xcf) | Save the current image as a GIMP XCF file (preserves all layers and metadata). |

### `batch_export`

```python
batch_export(output_dir: str, format: str = 'png', quality: int = 90, name_pattern: str = '{name}', image: str | int | None = None, mine_only: bool = False)
```

Export all open images (or a specific one) to a directory.

Parameters:
- output_dir: Directory to write exported files into
- format: "png", "jpeg", "webp", "tiff" (default "png")
- quality: JPEG/WEBP quality (default 90)
- name_pattern: Filename template — use {name} for image name, {index} for position
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: - exported: list of {file_path, name, width, height} - count: number of files written - errors: list of any export errors

### `export_image`

```python
export_image(file_path: str, format: str = 'png', quality: int = 90, flatten: bool = True, image: str | int | None = None)
```

Export the current image to a raster file (PNG, JPEG, WEBP, TIFF).

Parameters:
- file_path: Absolute path for the output file
- format: Output format — "png" (default), "jpeg", "webp", "tiff"
- quality: JPEG/WEBP quality 1-100 (default 90; ignored for PNG/TIFF)
- flatten: Flatten all layers before export (default True)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: - status, file_path, format, file_size_bytes

### `open_image`

```python
open_image(file_path: str, label: str | None = None)
```

Open an image file in GIMP and create a display window.

The returned `handle` is the stable way to refer to this image afterwards;
the file path and its base name work too. Do not address images by
position -- the list reorders whenever an image opens or closes.

Parameters:
- file_path: Absolute path to the image file to open (PNG, JPEG, TIFF, etc.)
- label: Optional friendly name; defaults to the file's base name

Returns: - handle: stable identifier to pass as `image` to other tools - image_id: internal GIMP image ID - label / file_path: what this image can also be looked up by - width / height: image dimensions in pixels - color_mode: RGB / Grayscale / Indexed - num_layers: number of layers in the image - display_opened: whether a GIMP display window was created

### `save_xcf`

```python
save_xcf(file_path: str, image: str | int | None = None)
```

Save the current image as a GIMP XCF file (preserves all layers and metadata).

Parameters:
- file_path: Absolute path for the output .xcf file
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: - status: "success" or "error" - file_path: confirmed output path

## Filters & Effects

| Tool | What it does |
|---|---|
| [`apply_drop_shadow`](#apply_drop_shadow) | Apply a drop shadow effect to a layer. |
| [`apply_emboss`](#apply_emboss) | Apply an emboss (bas-relief) effect to a layer. |
| [`apply_gaussian_blur`](#apply_gaussian_blur) | Apply Gaussian blur as a destructive filter operation. |
| [`apply_noise`](#apply_noise) | Add noise/grain to a layer. |
| [`apply_pixelate`](#apply_pixelate) | Pixelate a layer using a mosaic/block effect. |
| [`apply_vignette`](#apply_vignette) | Apply a vignette darkening effect around the edges of a layer. |

### `apply_drop_shadow`

```python
apply_drop_shadow(offset_x: int = 5, offset_y: int = 5, blur_radius: float = 10, color: str = 'black', opacity: float = 60, layer_name: str | None = None, image: str | int | None = None)
```

Apply a drop shadow effect to a layer.

Parameters:
- offset_x, offset_y: Shadow offset in pixels (default 5, 5)
- blur_radius: Shadow softness radius (default 10)
- color: Shadow color (default "black")
- opacity: Shadow opacity 0-100 (default 60)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `apply_emboss`

```python
apply_emboss(azimuth: float = 315, elevation: float = 45, depth: float = 2, layer_name: str | None = None, image: str | int | None = None)
```

Apply an emboss (bas-relief) effect to a layer.

Parameters:
- azimuth: Light direction in degrees 0-360 (default 315 = top-left)
- elevation: Light elevation angle 0-90 (default 45)
- depth: Effect depth/intensity (default 2)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `apply_gaussian_blur`

```python
apply_gaussian_blur(radius: float = 5.0, layer_name: str | None = None, image: str | int | None = None)
```

Apply Gaussian blur as a destructive filter operation.

Parameters:
- radius: Blur radius in pixels (default 5.0)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `apply_noise`

```python
apply_noise(amount: float = 0.2, layer_name: str | None = None, image: str | int | None = None)
```

Add noise/grain to a layer.

Parameters:
- amount: Noise intensity 0.0-1.0 (default 0.2)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `apply_pixelate`

```python
apply_pixelate(block_size: int = 10, layer_name: str | None = None, image: str | int | None = None)
```

Pixelate a layer using a mosaic/block effect.

Parameters:
- block_size: Size of each mosaic block in pixels (default 10)
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `apply_vignette`

```python
apply_vignette(softness: float = 3.0, shape: float = 1.0, layer_name: str | None = None, image: str | int | None = None)
```

Apply a vignette darkening effect around the edges of a layer.

Parameters:
- softness: Edge softness / fade width (default 3.0)
- shape: Shape factor — 1.0 = elliptical (default), values >1 = more rectangular
- layer_name: Target layer; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

## Image Adjustments

| Tool | What it does |
|---|---|
| [`adjust_brightness_contrast`](#adjust_brightness_contrast) | Adjust brightness and contrast of a layer. |
| [`adjust_color_balance`](#adjust_color_balance) | Adjust color balance (shadows / midtones / highlights) of a layer. |
| [`adjust_curves`](#adjust_curves) | Adjust tonal curves for a layer. |
| [`adjust_hue_saturation`](#adjust_hue_saturation) | Adjust hue, saturation, and lightness of a layer. |
| [`auto_levels`](#auto_levels) | Automatically stretch the tonal range of an image (auto levels / auto stretch contrast). |
| [`blur`](#blur) | Apply Gaussian blur to a layer. |
| [`denoise`](#denoise) | Reduce noise in a layer using GEGL noise-reduction. |
| [`desaturate`](#desaturate) | Convert a layer to grayscale (desaturate). |
| [`invert_colors`](#invert_colors) | Invert all colors in a layer (create a negative). |
| [`sharpen`](#sharpen) | Sharpen a layer using unsharp mask. |

### `adjust_brightness_contrast`

```python
adjust_brightness_contrast(brightness: int = 0, contrast: int = 0, image: str | int | None = None, layer_name: str | None = None)
```

Adjust brightness and contrast of a layer.

Parameters:
- brightness: -127 to +127 (default 0)
- contrast: -127 to +127 (default 0)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to adjust; defaults to active layer

Returns status dict.

Returns status dict.

### `adjust_color_balance`

```python
adjust_color_balance(cyan_red: float = 0, magenta_green: float = 0, yellow_blue: float = 0, range: str = 'midtones', image: str | int | None = None, layer_name: str | None = None)
```

Adjust color balance (shadows / midtones / highlights) of a layer.

Parameters:
- cyan_red: -100 to +100 (negative = cyan, positive = red; default 0)
- magenta_green: -100 to +100 (default 0)
- yellow_blue: -100 to +100 (default 0)
- range: "shadows", "midtones" (default), "highlights"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to adjust; defaults to active layer

Returns status dict.

Returns status dict.

### `adjust_curves`

```python
adjust_curves(preset: str = 's_curve', points: list | None = None, channel: str = 'value', image: str | int | None = None, layer_name: str | None = None)
```

Adjust tonal curves for a layer.

Parameters:
- preset: Built-in curve shape — "s_curve" (default), "lighten", "darken", "contrast"
- points: Custom control points as [[input, output], ...] override (overrides preset)
- channel: "value" (all), "red", "green", "blue", "alpha"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to adjust; defaults to active layer

Returns status dict.

Returns status dict.

### `adjust_hue_saturation`

```python
adjust_hue_saturation(hue: float = 0, saturation: float = 0, lightness: float = 0, color_range: str = 'all', image: str | int | None = None, layer_name: str | None = None)
```

Adjust hue, saturation, and lightness of a layer.

Parameters:
- hue: Hue rotation -180 to +180 (default 0)
- saturation: Saturation shift -100 to +100 (default 0)
- lightness: Lightness shift -100 to +100 (default 0)
- color_range: "all", "red", "yellow", "green", "cyan", "blue", "magenta" (default "all")
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to adjust; defaults to active layer

Returns status dict.

Returns status dict.

### `auto_levels`

```python
auto_levels(image: str | int | None = None, layer_name: str | None = None)
```

Automatically stretch the tonal range of an image (auto levels / auto stretch contrast).

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Name of the layer to adjust; defaults to active layer

Returns status dict.

Returns status dict.

### `blur`

```python
blur(radius_x: float = 5.0, radius_y: float = 5.0, image: str | int | None = None, layer_name: str | None = None)
```

Apply Gaussian blur to a layer.

Parameters:
- radius_x: Horizontal blur radius in pixels (default 5.0)
- radius_y: Vertical blur radius in pixels (default 5.0)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to blur; defaults to active layer

Returns status dict.

Returns status dict.

### `denoise`

```python
denoise(strength: int = 50, image: str | int | None = None, layer_name: str | None = None)
```

Reduce noise in a layer using GEGL noise-reduction.

Parameters:
- strength: Noise reduction strength 0-100 (default 50)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to denoise; defaults to active layer

Returns status dict.

Returns status dict.

### `desaturate`

```python
desaturate(mode: str = 'luminosity', image: str | int | None = None, layer_name: str | None = None)
```

Convert a layer to grayscale (desaturate).

Parameters:
- mode: Desaturation algorithm — "luminosity" (default), "luma", "average", "lightness"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to desaturate; defaults to active layer

Returns status dict.

Returns status dict.

### `invert_colors`

```python
invert_colors(image: str | int | None = None, layer_name: str | None = None)
```

Invert all colors in a layer (create a negative).

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to invert; defaults to active layer

Returns status dict.

Returns status dict.

### `sharpen`

```python
sharpen(amount: float = 50.0, radius: float = 3.0, threshold: int = 0, image: str | int | None = None, layer_name: str | None = None)
```

Sharpen a layer using unsharp mask.

Parameters:
- amount: Sharpening strength 0-500 (default 50.0)
- radius: Blur radius for the mask in pixels (default 3.0)
- threshold: Minimum difference before sharpening is applied (default 0)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to sharpen; defaults to active layer

Returns status dict.

Returns status dict.

## Layer Operations

| Tool | What it does |
|---|---|
| [`create_layer`](#create_layer) | Create and insert a new layer into an image. |
| [`delete_layer`](#delete_layer) | Delete a layer from an image. |
| [`duplicate_layer`](#duplicate_layer) | Duplicate a layer and insert the copy above it. |
| [`flatten_image`](#flatten_image) | Flatten all layers into a single background layer. |
| [`list_layers`](#list_layers) | List all layers in an image with their properties. |
| [`merge_visible_layers`](#merge_visible_layers) | Merge all visible layers into a single layer. |
| [`rename_layer`](#rename_layer) | Rename a layer. |
| [`reorder_layer`](#reorder_layer) | Move a layer to a new stack position. |
| [`set_layer_properties`](#set_layer_properties) | Set properties on an existing layer. |

### `create_layer`

```python
create_layer(name: str = 'New Layer', width: int | None = None, height: int | None = None, fill: str = 'transparent', opacity: float = 100, blend_mode: str = 'NORMAL', position: int = -1, image: str | int | None = None)
```

Create and insert a new layer into an image.

Parameters:
- name: Layer name (default "New Layer")
- width, height: Layer dimensions; defaults to image dimensions
- fill: Initial fill — "transparent" (default), "white", "black", or any CSS color
- opacity: Layer opacity 0-100 (default 100)
- blend_mode: GIMP layer mode name — "NORMAL" (default), "MULTIPLY", "SCREEN", etc.
- position: Stack position — -1 = top (default), 0 = bottom
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {layer_name, layer_id, width, height, position}

### `delete_layer`

```python
delete_layer(layer_name: str | None = None, layer_index: int | None = None, image: str | int | None = None)
```

Delete a layer from an image.

Parameters:
- layer_name: Name of the layer to delete
- layer_index: Position index of the layer (alternative to layer_name)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Provide either layer_name or layer_index. Defaults to active layer if neither given.

Returns status dict.

Returns status dict.

### `duplicate_layer`

```python
duplicate_layer(layer_name: str | None = None, image: str | int | None = None)
```

Duplicate a layer and insert the copy above it.

Parameters:
- layer_name: Name of the layer to duplicate; defaults to active layer
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {layer_name, layer_id}

### `flatten_image`

```python
flatten_image(image: str | int | None = None)
```

Flatten all layers into a single background layer.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `list_layers`

```python
list_layers(image: str | int | None = None)
```

List all layers in an image with their properties.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {layers: [{name, id, visible, opacity, blend_mode, width, height, has_alpha}], count}

### `merge_visible_layers`

```python
merge_visible_layers(image: str | int | None = None)
```

Merge all visible layers into a single layer.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {layer_name, layer_id}

### `rename_layer`

```python
rename_layer(new_name: str, old_name: str | None = None, layer_index: int | None = None, image: str | int | None = None)
```

Rename a layer.

Parameters:
- new_name: New name for the layer
- old_name: Current name of the layer to rename
- layer_index: Position index alternative to old_name
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {old_name, new_name}

### `reorder_layer`

```python
reorder_layer(new_position: int, layer_name: str | None = None, layer_index: int | None = None, image: str | int | None = None)
```

Move a layer to a new stack position.

Parameters:
- new_position: Target stack index (0 = bottom)
- layer_name / layer_index: Identify the layer (defaults to active layer)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `set_layer_properties`

```python
set_layer_properties(layer_name: str | None = None, layer_index: int | None = None, opacity: float | None = None, blend_mode: str | None = None, visible: bool | None = None, image: str | int | None = None)
```

Set properties on an existing layer.

Parameters:
- layer_name / layer_index: Identify the layer (defaults to active layer)
- opacity: New opacity 0-100 (omit to leave unchanged)
- blend_mode: New GIMP layer mode name (omit to leave unchanged)
- visible: True/False visibility (omit to leave unchanged)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

## Resize & Transform

| Tool | What it does |
|---|---|
| [`crop_to_rect`](#crop_to_rect) | Crop the image canvas to an explicit rectangle. |
| [`crop_to_selection`](#crop_to_selection) | Crop the image canvas to the current selection bounds. |
| [`flip_image`](#flip_image) | Flip the entire image horizontally or vertically. |
| [`resize_canvas`](#resize_canvas) | Resize the image canvas without scaling the content. |
| [`rotate_image`](#rotate_image) | Rotate the entire image. |
| [`scale_image`](#scale_image) | Scale an image to exact pixel dimensions. |
| [`scale_to_fit`](#scale_to_fit) | Scale an image to fit within a bounding box, preserving aspect ratio. |

### `crop_to_rect`

```python
crop_to_rect(x: int, y: int, width: int, height: int, image: str | int | None = None)
```

Crop the image canvas to an explicit rectangle.

Parameters:
- x, y: Top-left corner of the crop rectangle
- width, height: Dimensions of the crop rectangle
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {status, x, y, width, height}

### `crop_to_selection`

```python
crop_to_selection(autocrop: bool = False, image: str | int | None = None)
```

Crop the image canvas to the current selection bounds.

Parameters:
- autocrop: If True, auto-detect crop bounds instead of using selection (default False)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {status, x, y, width, height} — crop region applied

### `flip_image`

```python
flip_image(direction: str = 'horizontal', image: str | int | None = None)
```

Flip the entire image horizontally or vertically.

Parameters:
- direction: "horizontal" (default) or "vertical"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `resize_canvas`

```python
resize_canvas(width: int, height: int, anchor: str = 'center', fill: str = 'transparent', image: str | int | None = None)
```

Resize the image canvas without scaling the content.

Parameters:
- width, height: New canvas dimensions in pixels
- anchor: Position of existing content — "center" (default), "top-left", "top",
          "top-right", "left", "right", "bottom-left", "bottom", "bottom-right"
- fill: Color for new canvas areas — CSS color or "transparent"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {status, width, height, offset_x, offset_y}

### `rotate_image`

```python
rotate_image(angle: float, image: str | int | None = None)
```

Rotate the entire image.

Parameters:
- angle: Rotation in degrees — 90, 180, 270 use lossless GIMP rotation;
         other values rotate all layers with interpolation and flatten
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `scale_image`

```python
scale_image(width: int, height: int, interpolation: str = 'cubic', image: str | int | None = None)
```

Scale an image to exact pixel dimensions.

Parameters:
- width: Target width in pixels
- height: Target height in pixels
- interpolation: "cubic" (default), "linear", "none"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {status, width, height}

### `scale_to_fit`

```python
scale_to_fit(max_width: int, max_height: int, interpolation: str = 'cubic', image: str | int | None = None)
```

Scale an image to fit within a bounding box, preserving aspect ratio.

Parameters:
- max_width: Maximum allowed width in pixels
- max_height: Maximum allowed height in pixels
- interpolation: "cubic" (default), "linear", "none"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {status, width, height} — final dimensions after scaling

## Selections

| Tool | What it does |
|---|---|
| [`invert_selection`](#invert_selection) | Invert the current selection (select what is not selected). |
| [`modify_selection`](#modify_selection) | Grow, shrink, feather, border, or sharpen the current selection. |
| [`select_all`](#select_all) | Select the entire image canvas. |
| [`select_by_color`](#select_by_color) | Select regions by color similarity. |
| [`select_ellipse`](#select_ellipse) | Create an elliptical selection. |
| [`select_none`](#select_none) | Remove / deselect all selections. |
| [`select_rectangle`](#select_rectangle) | Create a rectangular selection. |

### `invert_selection`

```python
invert_selection(image: str | int | None = None)
```

Invert the current selection (select what is not selected).

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `modify_selection`

```python
modify_selection(operation: str, amount: float, image: str | int | None = None)
```

Grow, shrink, feather, border, or sharpen the current selection.

Parameters:
- operation: "grow", "shrink", "feather", "border", "sharpen"
- amount: Pixel radius for grow/shrink/feather/border; ignored for sharpen
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `select_all`

```python
select_all(image: str | int | None = None)
```

Select the entire image canvas.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `select_by_color`

```python
select_by_color(color: str, threshold: int = 15, operation: str = 'replace', image: str | int | None = None, layer_name: str | None = None)
```

Select regions by color similarity.

Parameters:
- color: Target color as CSS name, hex (#rrggbb), or rgb() string
- threshold: Color similarity tolerance 0-255 (default 15)
- operation: "replace" (default), "add", "subtract", "intersect"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to sample from; defaults to active layer

Returns status dict.

Returns status dict.

### `select_ellipse`

```python
select_ellipse(x: int, y: int, width: int, height: int, operation: str = 'replace', feather: float = 0, image: str | int | None = None)
```

Create an elliptical selection.

Parameters:
- x, y: Top-left corner of the bounding box
- width, height: Bounding box dimensions
- operation: "replace" (default), "add", "subtract", "intersect"
- feather: Feather radius in pixels (default 0)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `select_none`

```python
select_none(image: str | int | None = None)
```

Remove / deselect all selections.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `select_rectangle`

```python
select_rectangle(x: int, y: int, width: int, height: int, operation: str = 'replace', feather: float = 0, image: str | int | None = None)
```

Create a rectangular selection.

Parameters:
- x, y: Top-left corner of the selection
- width, height: Dimensions of the selection
- operation: "replace" (default), "add", "subtract", "intersect"
- feather: Feather radius in pixels (default 0 = no feather)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

## Text

| Tool | What it does |
|---|---|
| [`add_text`](#add_text) | Add a text layer to an image. |
| [`edit_text`](#edit_text) | Edit an existing text layer's content or formatting. |
| [`list_fonts`](#list_fonts) | List available fonts installed in GIMP. |

### `add_text`

```python
add_text(text: str, x: int = 0, y: int = 0, font: str = 'Sans', size: int = 24, color: str = 'black', image: str | int | None = None)
```

Add a text layer to an image.

Parameters:
- text: The text string to render
- x, y: Position of the text layer's top-left corner (default 0, 0)
- font: Font family name — "Sans" (default), "Serif", etc.
- size: Font size in pixels (default 24)
- color: Text color (CSS name, hex, or rgb() string; default "black")
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {layer_name, layer_id, text_width, text_height, position}

### `edit_text`

```python
edit_text(layer_name: str, text: str | None = None, font: str | None = None, size: float | None = None, color: str | None = None, image: str | int | None = None)
```

Edit an existing text layer's content or formatting.

Parameters:
- layer_name: Name of the text layer to edit
- text: New text content (omit to leave unchanged)
- font: New font family (omit to leave unchanged)
- size: New font size in pixels (omit to leave unchanged)
- color: New text color (omit to leave unchanged)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `list_fonts`

```python
list_fonts(filter: str | None = None)
```

List available fonts installed in GIMP.

Parameters:
- filter: Optional string to filter font names (case-insensitive substring match)

Returns: {fonts: [font_name, ...], count}

## Utility

| Tool | What it does |
|---|---|
| [`close_image`](#close_image) | Close an image, optionally saving as XCF first. |
| [`convert_color_mode`](#convert_color_mode) | Convert an image to a different color mode. |
| [`get_histogram`](#get_histogram) | Get histogram statistics for a channel of the active layer. |
| [`get_pixel_color`](#get_pixel_color) | Get the color of a single pixel. |
| [`get_selection_bounds`](#get_selection_bounds) | Get the bounding rectangle of the current selection. |

### `close_image`

```python
close_image(image: str | int | None = None, save_first: bool = False, force: bool = False, reason: str | None = None)
```

Close an image, optionally saving as XCF first.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- save_first: If True, save as XCF before closing (default False)
- force: Only needed for an image this server did not open. Reseats every
  open image onto a fresh window first so the target can be closed. No
  image is lost, but window position and zoom are reset for all of them.
- reason: Required only when closing an image owned by another session,
  which needs administrator access. The text is delivered to that session
  as the explanation for the closure, so make it specific.

Returns: {closed, handle, image_id, method, saved_to, remaining_open, as_administrator, owner_notified, owner}

### `convert_color_mode`

```python
convert_color_mode(mode: str, num_colors: int = 256, image: str | int | None = None)
```

Convert an image to a different color mode.

Parameters:
- mode: "RGB", "GRAY", or "INDEXED"
- num_colors: Number of colors for INDEXED mode (default 256)
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns status dict.

Returns status dict.

### `get_histogram`

```python
get_histogram(channel: str = 'value', image: str | int | None = None)
```

Get histogram statistics for a channel of the active layer.

Parameters:
- channel: "value" (all; default), "red", "green", "blue", "alpha"
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {mean, median, std_dev, min, max, pixels, count}

### `get_pixel_color`

```python
get_pixel_color(x: int, y: int, image: str | int | None = None, layer_name: str | None = None)
```

Get the color of a single pixel.

Parameters:
- x, y: Pixel coordinates
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).
- layer_name: Layer to sample from; defaults to active layer

Returns: {color_hex, color_rgb: [r, g, b], alpha}

### `get_selection_bounds`

```python
get_selection_bounds(image: str | int | None = None)
```

Get the bounding rectangle of the current selection.

Parameters:
- image: Which image to act on. Accepts the handle returned by new_canvas/open_image,
      a GIMP image_id, a file path, or a label. Omit it to use this session's
      current image (the last one you touched).

Returns: {has_selection, x, y, width, height}
