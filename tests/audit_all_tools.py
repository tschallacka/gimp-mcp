#!/usr/bin/env python3
"""Exercise every plugin command against a live GIMP and report what works.

This talks the socket protocol directly, so it covers the plugin -- where the
logic lives -- without needing an MCP client. It works on its own canvas,
addressed by handle, and closes what it opened.

    python3 tests/audit_all_tools.py            # run everything
    python3 tests/audit_all_tools.py --keep     # leave the canvas open
"""

import argparse
import json
import os
import re
import socket
import sys
import tempfile

HOST, PORT = "127.0.0.1", 9877
SESSION = "audit-session"
OUT = tempfile.mkdtemp(prefix="gimp-mcp-audit-")

PLUGIN = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gimp-mcp-plugin.py"
)


def send(command_type, params=None, timeout=60) -> dict:
    params = dict(params or {})
    params.setdefault("_session", SESSION)
    payload = {"type": command_type, "params": params}
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((HOST, PORT))
    except OSError as exc:
        return {"status": "error", "error": f"connect failed: {exc}"}
    try:
        sock.sendall(json.dumps(payload).encode() + b"\n")
        buf = b""
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
            try:
                return json.loads(buf.decode())
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
    except socket.timeout:
        return {"status": "error", "error": "timeout"}
    finally:
        sock.close()
    return {"status": "error", "error": "no parseable response"}


results = []


def check(name, response, note=""):
    ok = isinstance(response, dict) and response.get("status") == "success"
    err = ""
    if not ok:
        err = (response or {}).get("error", "no response")
        err = re.sub(r"\s+", " ", str(err))[:150]
    results.append((name, ok, err, note))
    mark = "\033[32mok  \033[0m" if ok else "\033[31mFAIL\033[0m"
    line = f"  {mark} {name}"
    if note:
        line += f"  ({note})"
    if err:
        line += f"\n         {err}"
    print(line, flush=True)
    return response if ok else None


def commands_in_plugin():
    src = open(PLUGIN).read()
    return sorted(set(re.findall(r'j\["type"\] == "([a-z_]+)"', src)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="leave the canvas open")
    args = ap.parse_args()

    probe = send("get_gimp_info")
    if probe.get("status") != "success":
        print("Cannot reach the GIMP MCP plugin on "
              f"{HOST}:{PORT}: {probe.get('error')}")
        print("Start GIMP with the plugin installed (autostart, or "
              "Tools > MCP > Start MCP Server).")
        return 2

    print(f"\nAuditing against live GIMP. Scratch dir: {OUT}\n")

    # ---- session and image lifecycle ------------------------------------
    print("session & lifecycle")
    check("session_info", send("session_info"))

    made = check(
        "new_canvas",
        send("new_canvas", {"width": 320, "height": 240,
                            "name": "audit", "fill": "white"}),
    )
    if not made:
        print("\nCannot continue without a canvas.")
        return 1
    handle = made["results"]["handle"]
    print(f"         handle = {handle!r}")

    # the name must survive: it used to be silently dropped
    check(
        "new_canvas keeps its name",
        {"status": "success"} if made["results"].get("label") == "audit"
        else {"status": "error", "error": f"label was {made['results'].get('label')!r}"},
    )

    listing = check("list_images", send("list_images"))
    if listing:
        mine = [i for i in listing["results"]["images"] if i.get("mine")]
        check(
            "list_images marks ownership",
            {"status": "success"} if any(i["handle"] == handle for i in mine)
            else {"status": "error", "error": "our canvas is not marked mine"},
        )

    # a second canvas renumbers the first: the bug that motivated handles
    second = check(
        "new_canvas (second)",
        send("new_canvas", {"width": 100, "height": 100, "name": "audit-decoy"}),
    )
    if second:
        meta = check(
            "handle still resolves after reorder",
            send("get_image_metadata", {"image": handle}),
        )
        if meta:
            dims = meta["results"]
            got = (dims.get("width"), dims.get("height"))
            check(
                "resolved the right image",
                {"status": "success"} if got == (320, 240)
                else {"status": "error", "error": f"got {got}, wanted (320, 240)"},
            )
        check(
            "close_image (decoy)",
            send("close_image", {"image": second["results"]["handle"]}),
        )

    check("set_active_image", send("set_active_image", {"image": handle}))
    check("adopt_image (already mine)", send("adopt_image", {"image": handle}))

    img = {"image": handle}

    # ---- introspection ---------------------------------------------------
    print("\nintrospection")
    for name, params in [
        ("get_gimp_info", {}),
        ("get_image_metadata", img),
        ("get_context_state", {}),
        ("get_image_bitmap", {**img, "max_width": 64}),
        ("get_selection_bounds", img),
        ("get_pixel_color", {**img, "x": 10, "y": 10}),
        ("get_histogram", img),
        ("list_layers", img),
        ("list_fonts", {}),
        ("check_server", {}),
    ]:
        check(name, send(name, params))

    # ---- layers ----------------------------------------------------------
    print("\nlayers")
    check("create_layer", send("create_layer", {**img, "name": "work",
                                                "fill": "transparent"}))
    check("duplicate_layer", send("duplicate_layer", {**img, "layer_name": "work"}))
    check("rename_layer", send("rename_layer", {**img, "layer_name": "work",
                                                "new_name": "painted"}))
    check("set_layer_properties", send("set_layer_properties",
                                       {**img, "layer_name": "painted",
                                        "opacity": 80, "visible": True}))
    check("reorder_layer", send("reorder_layer", {**img, "layer_name": "painted",
                                                  "position": 0}))

    # ---- selection -------------------------------------------------------
    print("\nselection")
    check("select_all", send("select_all", img))
    check("select_none", send("select_none", img))
    check("select_rectangle", send("select_rectangle",
                                   {**img, "x": 10, "y": 10,
                                    "width": 100, "height": 80}))
    check("modify_selection", send("modify_selection", {**img, "operation": "grow",
                                                        "amount": 5}))
    check("invert_selection", send("invert_selection", img))
    check("select_ellipse", send("select_ellipse", {**img, "x": 20, "y": 20,
                                                    "width": 60, "height": 60}))
    check("crop_to_selection", send("crop_to_selection", img))
    check("select_all", send("select_all", img), note="re-select after crop")
    check("select_by_color", send("select_by_color", {**img, "color": "white",
                                                      "threshold": 20}))
    check("select_none", send("select_none", img), note="clear")

    # ---- paint and draw --------------------------------------------------
    print("\npaint & draw")
    check("set_colors", send("set_colors", {"foreground": "red",
                                            "background": "blue"}))
    check("fill_layer", send("fill_layer", {**img, "layer_name": "painted",
                                            "color": "#204060"}))
    check("draw_line", send("draw_line", {**img, "layer_name": "painted",
                                          "points": [5, 5, 90, 60],
                                          "color": "red", "width": 3}))
    check("draw_rectangle", send("draw_rectangle", {**img, "layer_name": "painted",
                                                    "x": 5, "y": 5, "width": 40,
                                                    "height": 30, "color": "lime"}))
    check("draw_ellipse", send("draw_ellipse", {**img, "layer_name": "painted",
                                                "x": 10, "y": 10, "width": 40,
                                                "height": 25, "color": "yellow"}))
    check("fill_rectangle", send("fill_rectangle", {**img, "layer_name": "painted",
                                                    "x": 12, "y": 12, "width": 20,
                                                    "height": 15, "color": "white"}))
    check("fill_ellipse", send("fill_ellipse", {**img, "layer_name": "painted",
                                                "x": 30, "y": 20, "width": 25,
                                                "height": 20, "color": "cyan"}))
    check("gradient_fill", send("gradient_fill", {**img, "layer_name": "painted",
                                                  "start_color": "black",
                                                  "end_color": "white",
                                                  "x1": 0, "y1": 0,
                                                  "x2": 100, "y2": 100}))
    check("fill_selection", send("fill_selection", {**img, "layer_name": "painted",
                                                    "color": "magenta"}),
          note="no selection active")

    # ---- text ------------------------------------------------------------
    print("\ntext")
    added = check("add_text", send("add_text", {**img, "text": "Hello",
                                                "x": 10, "y": 10, "size": 14,
                                                "color": "black"}))
    if added:
        layer = added["results"].get("layer_name") or "Hello"
        check("edit_text", send("edit_text", {**img, "layer_name": layer,
                                              "text": "Edited"}))

    # ---- adjustments and filters ----------------------------------------
    print("\nadjustments & filters")
    for name, params in [
        ("auto_levels", img),
        ("adjust_brightness_contrast", {**img, "brightness": 5, "contrast": 5}),
        ("adjust_hue_saturation", {**img, "hue": 5, "saturation": 5}),
        ("adjust_color_balance", {**img, "cyan_red": 5}),
        ("adjust_curves", {**img, "channel": "value",
                           "points": [0.0, 0.0, 0.5, 0.55, 1.0, 1.0]}),
        ("sharpen", {**img, "amount": 0.5}),
        ("blur", {**img, "radius": 2}),
        ("denoise", {**img, "strength": 2}),
        ("desaturate", img),
        ("invert_colors", img),
        ("apply_gaussian_blur", {**img, "radius": 3}),
        ("apply_pixelate", {**img, "block_size": 4}),
        ("apply_emboss", {**img, "azimuth": 30, "elevation": 45, "depth": 2}),
        ("apply_vignette", {**img, "strength": 0.5}),
        ("apply_noise", {**img, "amount": 0.1}),
        ("apply_drop_shadow", {**img, "offset_x": 3, "offset_y": 3, "blur": 3}),
    ]:
        check(name, send(name, params))

    # ---- geometry --------------------------------------------------------
    print("\ngeometry")
    check("scale_image", send("scale_image", {**img, "width": 300, "height": 220}))
    check("scale_to_fit", send("scale_to_fit", {**img, "max_width": 200,
                                                "max_height": 200}))
    check("crop_to_rect", send("crop_to_rect", {**img, "x": 0, "y": 0,
                                                "width": 150, "height": 120}))
    check("rotate_image", send("rotate_image", {**img, "degrees": 90}))
    check("flip_image", send("flip_image", {**img, "direction": "horizontal"}))
    check("resize_canvas", send("resize_canvas", {**img, "width": 200,
                                                  "height": 200,
                                                  "offset_x": 0, "offset_y": 0}))
    check("convert_color_mode", send("convert_color_mode", {**img, "mode": "RGB"}))
    check("warp_region", send("warp_region",
                              {**img, "vectors": [{"x": 50, "y": 50, "dx": 5,
                                                   "dy": 0, "radius": 20,
                                                   "amount": 0.3}]}))

    # ---- history ---------------------------------------------------------
    print("\nhistory")
    check("undo", send("undo", {**img, "steps": 1}))
    check("redo", send("redo", {**img, "steps": 1}))

    # ---- flatten / merge -------------------------------------------------
    print("\nflatten & merge")
    check("merge_visible_layers", send("merge_visible_layers", img))
    check("flatten_image", send("flatten_image", img))
    check("delete_layer", send("delete_layer", {**img, "layer_name": "painted"}),
          note="may already be merged away")

    # ---- export ----------------------------------------------------------
    print("\nexport")
    check("export_image", send("export_image",
                               {**img, "file_path": os.path.join(OUT, "out.png"),
                                "format": "png"}))
    check("save_xcf", send("save_xcf",
                           {**img, "file_path": os.path.join(OUT, "out.xcf")}))
    check("export_web_optimized", send("export_web_optimized",
                                       {**img, "output_dir": OUT,
                                        "base_name": "web"}))
    check("export_icon_sizes", send("export_icon_sizes",
                                    {"source_image": handle, "output_dir": OUT,
                                     "platform": "android"}))
    check("batch_resize", send("batch_resize",
                               {**img, "output_dir": OUT,
                                "sizes": [{"width": 64, "height": 64}]}))
    check("export_sprite_sheet", send("export_sprite_sheet",
                                      {**img, "output_dir": OUT,
                                       "columns": 1, "source": "layers"}))
    check("export_social_media_kit", send("export_social_media_kit",
                                          {**img, "output_dir": OUT,
                                           "platforms": ["twitter"]}))
    check("batch_export", send("batch_export",
                               {"output_dir": OUT, "format": "png",
                                "mine_only": True}))

    # ---- error handling --------------------------------------------------
    print("\nerror handling (these should FAIL cleanly)")
    bad = send("get_image_metadata", {"image": "no-such-handle"})
    check(
        "unknown handle is refused",
        {"status": "success"} if bad.get("status") == "error"
        else {"status": "error", "error": "a bogus handle was accepted"},
    )
    check(
        "refusal names what is open",
        {"status": "success"} if handle in str(bad.get("error", ""))
        else {"status": "error",
              "error": f"unhelpful message: {bad.get('error')!r}"},
    )

    # ---- cleanup ---------------------------------------------------------
    print("\ncleanup")
    if args.keep:
        print("  -- kept open on request")
    else:
        closed = check("close_my_images", send("close_my_images"))
        if closed:
            check(
                "our canvas is gone",
                {"status": "success"} if closed["results"]["closed_count"] >= 1
                else {"status": "error", "error": "nothing was closed"},
            )
        after = send("list_images", {"mine_only": True})
        if after.get("status") == "success":
            left = after["results"]["images"]
            check(
                "session owns nothing afterwards",
                {"status": "success"} if not left
                else {"status": "error",
                      "error": f"{len(left)} image(s) left: "
                               f"{[i['handle'] for i in left]}"},
            )

    # ---- coverage --------------------------------------------------------
    exercised = {n.split()[0] for n, _, _, _ in results}
    known = set(commands_in_plugin())
    missed = sorted(known - exercised)

    passed = sum(1 for _, ok, _, _ in results if ok)
    failed = [(n, e) for n, ok, e, _ in results if not ok]

    print("\n" + "=" * 66)
    print(f"{passed}/{len(results)} checks passed")
    print(f"commands exercised: {len(known & exercised)}/{len(known)}")
    if missed:
        print(f"not exercised: {', '.join(missed)}")
    if failed:
        print(f"\n{len(failed)} FAILING:")
        for name, err in failed:
            print(f"  {name}: {err}")
    print("=" * 66)
    print(f"artifacts in {OUT}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
