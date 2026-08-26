#!/usr/bin/env python3
"""End-to-end check of the administrator flow against a live GIMP.

Needs a human: a dialog appears in GIMP and someone must click
"Grant admin access".
"""
import json
import socket
import sys
import time

HOST, PORT = "127.0.0.1", 9877
VICTIM = "victim-session"
ADMIN = "admin-session"


def send(t, params=None, session=None, timeout=200) -> dict:
    params = dict(params or {})
    if session:
        params["_session"] = session
    s = socket.socket()
    s.settimeout(timeout)
    s.connect((HOST, PORT))
    s.sendall(json.dumps({"type": t, "params": params}).encode() + b"\n")
    buf = b""
    while True:
        c = s.recv(65536)
        if not c:
            break
        buf += c
        try:
            return json.loads(buf.decode())
        except Exception:
            continue
    return {"status": "error", "error": "no response"}


results = []


def step(name, ok, detail=""):
    results.append((name, ok))
    print(f"  {'ok  ' if ok else 'FAIL'} {name}" + (f"  {detail}" if detail else ""),
          flush=True)


print("\n=== administrator flow, end to end ===\n", flush=True)

# The victim session opens an image and is seen recently.
made = send("new_canvas", {"width": 200, "height": 150, "name": "victims-work"},
            session=VICTIM)
step("victim opens an image", made.get("status") == "success")
if made.get("status") != "success":
    print(made)
    sys.exit(1)
handle = made["results"]["handle"]
print(f"       victim's handle: {handle}", flush=True)

# Admin cannot touch it yet.
blocked = send("get_image_metadata", {"image": handle}, session=ADMIN)
step("admin is blocked before elevation", blocked.get("status") == "error")

print("\n  >>> LOOK AT GIMP: click 'Grant admin access' in the dialog <<<\n",
      flush=True)

start = time.time()
granted = send("request_elevation", {"reason":
               "end-to-end test of the administrator flow"}, session=ADMIN)
waited = round(time.time() - start)
step("user granted elevation", granted.get("status") == "success",
     f"(waited {waited}s)")
if granted.get("status") != "success":
    print("      ", granted.get("error"), flush=True)
    send("close_my_images", {}, session=VICTIM)
    sys.exit(1)

# Now the admin can see it.
seen = send("get_image_metadata", {"image": handle}, session=ADMIN)
step("admin can now read the victim's image", seen.get("status") == "success")

listed = send("list_images", {}, session=ADMIN)
step("admin sees it in list_images",
     any(i.get("handle") == handle for i in listed["results"]["images"]))

# Closing without a reason must still be refused.
no_reason = send("close_image", {"image": handle}, session=ADMIN)
step("close without a reason is refused", no_reason.get("status") == "error")

# Close with a reason.
REASON = "reclaiming a canvas left open by a finished job"
closed = send("close_image", {"image": handle, "reason": REASON}, session=ADMIN)
ok = closed.get("status") == "success"
step("admin closes the victim's image", ok)
if ok:
    r = closed["results"]
    step("marked as an administrator action", r.get("as_administrator") is True)
    step("owner was notified", r.get("owner_notified") is True)

# The victim's next request carries the notification.
nxt = send("list_images", {}, session=VICTIM)
notes = nxt.get("notifications") or []
step("victim's next call carries the ping", len(notes) == 1,
     f"({len(notes)} notification(s))")
if notes:
    n = notes[0]
    step("ping says an administrator closed it",
         n.get("type") == "image_closed_by_administrator")
    step("ping carries the admin's reason", n.get("reason") == REASON)
    step("ping names the image", n.get("handle") == handle)
    print(f"\n       ping: {n.get('message')}", flush=True)
    print(f"       reason: {n.get('reason')}", flush=True)
    print(f"       closed_by: {n.get('closed_by')}\n", flush=True)

# Delivered once only.
again = send("get_notifications", {}, session=VICTIM)
step("ping is not delivered twice", again["results"]["count"] == 0)

# Clean up.
send("revoke_elevation", {}, session=ADMIN)
after = send("elevation_status", {}, session=ADMIN)
step("elevation revoked", after["results"]["elevated"] is False)
send("close_my_images", {}, session=VICTIM)
send("close_my_images", {}, session=ADMIN)

passed = sum(1 for _, ok in results if ok)
print(f"\n=== {passed}/{len(results)} checks passed ===", flush=True)
sys.exit(0 if passed == len(results) else 1)
