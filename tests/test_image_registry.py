#!/usr/bin/env python3
"""Unit tests for session-scoped image identity and resolution.

The plugin only ever runs inside GIMP, so the GIMP API is stubbed here. These
tests pin the behaviour that positional image_index got wrong: an image must
keep its identity when the image list reorders, and one session must not be
able to touch or close another session's images.

Run: python3 tests/test_image_registry.py
"""

import json
import os
import sys
import threading
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Minimal GIMP stubs
# ---------------------------------------------------------------------------

class FakeParasite:
    def __init__(self, name, flags, data):
        self.name, self.flags, self._data = name, flags, data

    def get_data(self):
        return self._data

    @staticmethod
    def new(name, flags, data):
        return FakeParasite(name, flags, data)


class FakeFile:
    def __init__(self, path):
        self._path = path

    def get_path(self):
        return self._path


class FakeImage:
    _next_id = 1

    def __init__(self, name="Untitled", path=None, width=10, height=10):
        self.id = FakeImage._next_id
        FakeImage._next_id += 1
        self._name = name
        self._file = FakeFile(path) if path else None
        self._parasites = {}
        self._w, self._h = width, height
        self.deleted = False

    def get_id(self):
        return self.id

    def get_name(self):
        return self._name

    def get_file(self):
        return self._file

    def get_width(self):
        return self._w

    def get_height(self):
        return self._h

    def get_base_type(self):
        return "RGB"

    def scale(self, w, h):
        self._w, self._h = w, h

    def get_layers(self):
        return []

    def is_dirty(self):
        return False

    def attach_parasite(self, parasite):
        self._parasites[parasite.name] = parasite

    def get_parasite(self, name):
        return self._parasites.get(name)

    def delete(self):
        self.deleted = True
        FakeGimp.images = [i for i in FakeGimp.images if i is not self]


class FakeDisplay:
    def __init__(self, display_id, image):
        self.id, self.image, self.presented = display_id, image, False

    def get_id(self):
        return self.id

    def present(self):
        self.presented = True

    def delete(self):
        FakeGimp.displays.pop(self.id, None)
        # GIMP drops an image when its last display goes.
        if not any(d.image is self.image for d in FakeGimp.displays.values()):
            FakeGimp.images = [i for i in FakeGimp.images if i is not self.image]

    @staticmethod
    def new(image):
        display = FakeDisplay(FakeGimp.next_display_id, image)
        FakeGimp.next_display_id += 1
        FakeGimp.displays[display.id] = display
        return display

    @staticmethod
    def get_by_id(display_id):
        return FakeGimp.displays.get(display_id)

    @staticmethod
    def id_is_valid(display_id):
        return display_id in FakeGimp.displays


class FakeGimp:
    images = []
    displays = {}
    next_display_id = 1

    Display = FakeDisplay
    Parasite = FakeParasite
    ImageBaseType = types.SimpleNamespace(RGB="RGB", GRAY="GRAY", INDEXED="INDEXED")
    PDBProcType = types.SimpleNamespace(PLUGIN="PLUGIN", PERSISTENT="PERSISTENT")
    RunMode = types.SimpleNamespace(INTERACTIVE=0)
    PDBStatusType = types.SimpleNamespace(SUCCESS=0)

    class PlugIn:
        # GObject stamps this on real subclasses; Gimp.main() reads it.
        __gtype__ = "MCPPluginStub"

        def __init__(self, *a, **k):
            pass

    @staticmethod
    def get_images():
        return list(FakeGimp.images)

    @staticmethod
    def displays_flush():
        pass

    @staticmethod
    def directory():
        return "/tmp/fake-gimp"

    @staticmethod
    def message(_m):
        pass

    file_load_result = None

    @staticmethod
    def get_pdb():
        return None

    @staticmethod
    def file_load(_run_mode, _gio_file):
        return FakeGimp.file_load_result

    @staticmethod
    def main(*_a, **_k):
        # The plugin calls this at module scope to hand control to GIMP.
        return 0

    @staticmethod
    def Procedure():
        pass

    @staticmethod
    def register_file_handler_mime(*a, **k):
        pass

    @staticmethod
    def reset():
        FakeGimp.images = []
        FakeGimp.displays = {}
        FakeGimp.next_display_id = 1
        FakeImage._next_id = 1


def install_stubs():
    """Put fake gi/Gimp modules in place so the plugin file can be imported."""
    gi = types.ModuleType("gi")
    repository = types.ModuleType("gi.repository")
    setattr(gi, "require_version", lambda *a, **k: None)
    setattr(gi, "repository", repository)
    setattr(repository, "Gimp", FakeGimp)
    setattr(repository, "GLib", types.SimpleNamespace(
        dgettext=lambda _d, m: m, MainLoop=lambda: None, Error=lambda: None
    ))
    setattr(repository, "GObject", types.SimpleNamespace(
        ParamFlags=types.SimpleNamespace(READWRITE=0)
    ))
    setattr(repository, "Gegl", types.SimpleNamespace())
    setattr(repository, "Gio", types.SimpleNamespace())
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository


def load_plugin_module():
    install_stubs()
    import importlib.util

    path = os.path.join(ROOT, "gimp-mcp-plugin.py")
    spec = importlib.util.spec_from_file_location("gimp_mcp_plugin_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_plugin_module()


def new_plugin():
    """A plugin instance with the state __init__ sets, minus the GIMP wiring."""
    plugin = MODULE.MCPPlugin.__new__(MODULE.MCPPlugin)
    plugin._displays = {}
    plugin._current = {}
    plugin._elevated = {}
    plugin._notifications = {}
    plugin._last_seen = {}
    plugin._session_meta = {}
    plugin._admin_lock = threading.Lock()
    return plugin


def open_canvas(plugin, session, label, path=None):
    """Mimic what _new_canvas/_open_image do: make an image, display, identity.

    Also marks the session as just-seen, which _handle_client does for every
    real request. Without it the owner looks like a session that has gone away
    and its images become adoptable.
    """
    image = FakeImage(name=label, path=path)
    FakeGimp.images.append(image)
    display = FakeDisplay.new(image)
    identity = plugin._register_image(image, display, session, "new_canvas", label)
    plugin._last_seen[session] = MODULE.time.time()
    return image, identity


class RegistryTest(unittest.TestCase):
    def setUp(self):
        FakeGimp.reset()
        self.plugin = new_plugin()


class TestIdentity(RegistryTest):
    def test_identity_round_trips_through_parasite(self):
        image, identity = open_canvas(self.plugin, "s1", "logo")
        stored = self.plugin._read_identity(image)
        self.assertEqual(stored["handle"], identity["handle"])
        self.assertEqual(stored["session"], "s1")
        self.assertEqual(stored["label"], "logo")

    def test_handles_are_unique_and_readable(self):
        _, a = open_canvas(self.plugin, "s1", "logo")
        _, b = open_canvas(self.plugin, "s1", "logo")
        _, c = open_canvas(self.plugin, "s1", "logo")
        self.assertEqual([a["handle"], b["handle"], c["handle"]],
                         ["logo", "logo-2", "logo-3"])

    def test_handle_slugifies_awkward_labels(self):
        _, identity = open_canvas(self.plugin, "s1", "My Logo (Final)!")
        self.assertEqual(identity["handle"], "my-logo-final")

    def test_untracked_image_has_no_identity(self):
        image = FakeImage(name="opened-by-hand")
        FakeGimp.images.append(image)
        self.assertEqual(self.plugin._read_identity(image), {})


class TestResolution(RegistryTest):
    def test_handle_survives_list_reordering(self):
        """The regression that motivated all of this."""
        first, first_id = open_canvas(self.plugin, "s1", "first")
        # A second image arrives and GIMP puts it at the front.
        second, _ = open_canvas(self.plugin, "s1", "second")
        FakeGimp.images.reverse()
        self.assertIsNot(FakeGimp.get_images()[0], first)

        resolved = self.plugin._resolve_image(
            {"image": first_id["handle"], "_session": "s1"}
        )
        self.assertIs(resolved, first)

    def test_resolves_by_image_id_int_and_string(self):
        image, _ = open_canvas(self.plugin, "s1", "a")
        self.assertIs(
            self.plugin._resolve_image({"image": image.get_id(), "_session": "s1"}),
            image,
        )
        self.assertIs(
            self.plugin._resolve_image({"image": str(image.get_id()), "_session": "s1"}),
            image,
        )

    def test_resolves_by_full_path_and_basename(self):
        image, _ = open_canvas(self.plugin, "s1", "shot", path="/tmp/pics/shot.png")
        self.assertIs(
            self.plugin._resolve_image({"image": "/tmp/pics/shot.png", "_session": "s1"}),
            image,
        )
        self.assertIs(
            self.plugin._resolve_image({"image": "shot.png", "_session": "s1"}),
            image,
        )

    def test_resolves_by_label(self):
        image, _ = open_canvas(self.plugin, "s1", "banner")
        self.assertIs(
            self.plugin._resolve_image({"image": "banner", "_session": "s1"}), image
        )

    def test_omitted_image_uses_session_current(self):
        first, _ = open_canvas(self.plugin, "s1", "first")
        second, _ = open_canvas(self.plugin, "s1", "second")
        # _register_image made `second` current.
        self.assertIs(self.plugin._resolve_image({"_session": "s1"}), second)
        # Touching `first` moves the cursor.
        self.plugin._resolve_image({"image": "first", "_session": "s1"})
        self.assertIs(self.plugin._resolve_image({"_session": "s1"}), first)

    def test_unknown_spec_names_what_is_open(self):
        open_canvas(self.plugin, "s1", "logo")
        with self.assertRaises(RuntimeError) as caught:
            self.plugin._resolve_image({"image": "nope", "_session": "s1"})
        self.assertIn("logo", str(caught.exception))

    def test_no_images_open_is_actionable(self):
        with self.assertRaises(RuntimeError) as caught:
            self.plugin._resolve_image({"_session": "s1"})
        self.assertIn("new_canvas", str(caught.exception))


class TestSessionIsolation(RegistryTest):
    def test_other_sessions_images_are_never_guessed(self):
        open_canvas(self.plugin, "other", "theirs-a")
        open_canvas(self.plugin, "other", "theirs-b")
        with self.assertRaises(RuntimeError) as caught:
            self.plugin._resolve_image({"_session": "mine"})
        self.assertIn("other sessions", str(caught.exception))

    def test_ambiguity_within_a_session_is_refused(self):
        open_canvas(self.plugin, "s1", "a")
        open_canvas(self.plugin, "s1", "b")
        self.plugin._current.clear()
        with self.assertRaises(RuntimeError) as caught:
            self.plugin._resolve_image({"_session": "s1"})
        self.assertIn("pass image=", str(caught.exception))

    def test_lone_image_is_used_even_if_untracked(self):
        image = FakeImage(name="only-one")
        FakeGimp.images.append(image)
        self.assertIs(self.plugin._resolve_image({"_session": "s1"}), image)

    def test_duplicate_handle_prefers_the_callers_own(self):
        theirs, _ = open_canvas(self.plugin, "other", "shared")
        # Force a colliding handle, as a plugin restart could.
        mine = FakeImage(name="shared")
        FakeGimp.images.append(mine)
        self.plugin._write_identity(
            mine, {"handle": "shared", "session": "mine", "label": "shared"}
        )
        resolved = self.plugin._resolve_image({"image": "shared", "_session": "mine"})
        self.assertIs(resolved, mine)

    def test_list_marks_ownership(self):
        open_canvas(self.plugin, "mine", "a")
        open_canvas(self.plugin, "other", "b")
        result = self.plugin._list_images({"_session": "mine"})["results"]
        owned = {i["handle"]: i["mine"] for i in result["images"]}
        self.assertEqual(owned, {"a": True, "b": False})
        self.assertEqual(result["total_open"], 2)

    def test_list_mine_only_filters(self):
        open_canvas(self.plugin, "mine", "a")
        open_canvas(self.plugin, "other", "b")
        result = self.plugin._list_images(
            {"_session": "mine", "mine_only": True}
        )["results"]
        self.assertEqual([i["handle"] for i in result["images"]], ["a"])
        self.assertEqual(result["total_open"], 2)


class TestClosing(RegistryTest):
    def test_close_removes_the_image(self):
        image, identity = open_canvas(self.plugin, "s1", "doomed")
        result = self.plugin._close_image(
            {"image": identity["handle"], "_session": "s1"}
        )
        self.assertEqual(result["status"], "success", result)
        self.assertTrue(result["results"]["closed"])
        self.assertEqual(result["results"]["method"], "display_deleted")
        self.assertEqual(FakeGimp.get_images(), [])

    def test_close_leaves_other_images_alone(self):
        keep, _ = open_canvas(self.plugin, "s1", "keep")
        _, doomed = open_canvas(self.plugin, "s1", "doomed")
        self.plugin._close_image({"image": doomed["handle"], "_session": "s1"})
        self.assertEqual(FakeGimp.get_images(), [keep])

    def test_untracked_image_refuses_without_force(self):
        image = FakeImage(name="by-hand")
        FakeGimp.images.append(image)
        FakeDisplay.new(image)  # a window we did not create
        result = self.plugin._close_image({"_session": "s1"})
        self.assertEqual(result["status"], "error")
        self.assertIn("force=true", result["error"])
        self.assertIn(image, FakeGimp.get_images())

    def test_force_closes_untracked_and_spares_the_rest(self):
        keep, _ = open_canvas(self.plugin, "s1", "keep")
        stray = FakeImage(name="by-hand")
        FakeGimp.images.append(stray)
        FakeDisplay.new(stray)

        result = self.plugin._close_image(
            {"image": stray.get_id(), "_session": "s1", "force": True}
        )
        self.assertEqual(result["status"], "success", result)
        self.assertEqual(result["results"]["method"], "forced")
        self.assertEqual(FakeGimp.get_images(), [keep])

    def test_close_my_images_spares_other_sessions(self):
        open_canvas(self.plugin, "mine", "a")
        open_canvas(self.plugin, "mine", "b")
        theirs, _ = open_canvas(self.plugin, "other", "c")

        result = self.plugin._close_my_images({"_session": "mine"})["results"]
        self.assertEqual(result["closed_count"], 2)
        self.assertEqual(result["failed_count"], 0)
        self.assertEqual(FakeGimp.get_images(), [theirs])

    def test_closing_clears_the_session_cursor(self):
        _, identity = open_canvas(self.plugin, "s1", "only")
        self.plugin._close_image({"image": identity["handle"], "_session": "s1"})
        self.assertNotIn("s1", self.plugin._current)

    def test_reseat_gives_every_image_a_tracked_display(self):
        stray_a, stray_b = FakeImage(name="a"), FakeImage(name="b")
        FakeGimp.images.extend([stray_a, stray_b])
        FakeDisplay.new(stray_a)
        FakeDisplay.new(stray_b)
        self.assertEqual(self.plugin._displays, {})

        self.plugin._reseat_displays()

        self.assertEqual(len(FakeGimp.get_images()), 2)
        for image in FakeGimp.get_images():
            display_id = self.plugin._displays[image.get_id()]
            self.assertTrue(FakeDisplay.id_is_valid(display_id))


class TestSharedGimpSafety(RegistryTest):
    """Bulk operations must not reach into another session's images."""

    def test_batch_resize_refuses_when_session_owns_nothing(self):
        open_canvas(self.plugin, "other", "theirs")
        result = self.plugin._batch_resize(
            {"_session": "mine", "width": 10, "height": 10, "output_dir": "/tmp"}
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("all_images=true", result["error"])

    def test_sprite_sheet_from_images_is_session_scoped(self):
        open_canvas(self.plugin, "other", "theirs-a")
        open_canvas(self.plugin, "other", "theirs-b")
        result = self.plugin._export_sprite_sheet(
            {"_session": "mine", "source": "images", "output_path": "/tmp/s.png"}
        )
        # No frames of ours, so it must decline rather than sheet their images.
        self.assertEqual(result["status"], "error")
        self.assertIn("No frames", result["error"])


class TestAdoption(RegistryTest):
    def test_adopting_gives_a_handle_and_ownership(self):
        image = FakeImage(name="hand.png", path="/tmp/hand.png")
        FakeGimp.images.append(image)
        result = self.plugin._adopt_image(
            {"image": image.get_id(), "_session": "s1"}
        )["results"]
        self.assertFalse(result["already_mine"])
        self.assertEqual(result["handle"], "hand")
        self.assertTrue(result["mine"])

    def test_adopting_twice_is_a_no_op(self):
        _, identity = open_canvas(self.plugin, "s1", "already")
        result = self.plugin._adopt_image(
            {"image": identity["handle"], "_session": "s1"}
        )["results"]
        self.assertTrue(result["already_mine"])


class TestOwnershipGate(RegistryTest):
    """Without elevation, another session's images are simply not reachable."""

    def test_naming_another_sessions_handle_is_refused(self):
        open_canvas(self.plugin, "other", "theirs")
        with self.assertRaises(RuntimeError) as caught:
            self.plugin._resolve_image({"image": "theirs", "_session": "mine"})
        self.assertIn("another MCP session", str(caught.exception))
        self.assertIn("request_elevation", str(caught.exception))

    def test_naming_by_image_id_is_refused_too(self):
        image, _ = open_canvas(self.plugin, "other", "theirs")
        with self.assertRaises(RuntimeError):
            self.plugin._resolve_image(
                {"image": image.get_id(), "_session": "mine"}
            )

    def test_naming_by_path_is_refused_too(self):
        open_canvas(self.plugin, "other", "theirs", path="/tmp/theirs.png")
        with self.assertRaises(RuntimeError):
            self.plugin._resolve_image(
                {"image": "/tmp/theirs.png", "_session": "mine"}
            )

    def test_untracked_images_stay_reachable(self):
        stray = FakeImage(name="by-hand.png", path="/tmp/by-hand.png")
        FakeGimp.images.append(stray)
        open_canvas(self.plugin, "other", "theirs")
        resolved = self.plugin._resolve_image(
            {"image": "by-hand.png", "_session": "mine"}
        )
        self.assertIs(resolved, stray)

    def test_elevation_lifts_the_gate(self):
        theirs, _ = open_canvas(self.plugin, "other", "theirs")
        self.plugin._elevated["mine"] = {"granted_at": 0, "reason": "cleanup"}
        resolved = self.plugin._resolve_image(
            {"image": "theirs", "_session": "mine"}
        )
        self.assertIs(resolved, theirs)

    def test_revoking_restores_the_gate(self):
        open_canvas(self.plugin, "other", "theirs")
        self.plugin._elevated["mine"] = {"granted_at": 0, "reason": "cleanup"}
        self.plugin._revoke_elevation({"_session": "mine"})
        with self.assertRaises(RuntimeError):
            self.plugin._resolve_image({"image": "theirs", "_session": "mine"})

    def test_status_reports_elevation(self):
        info = self.plugin._elevation_status({"_session": "mine"})["results"]
        self.assertFalse(info["elevated"])
        self.plugin._elevated["mine"] = {"granted_at": 123, "reason": "why"}
        info = self.plugin._elevation_status({"_session": "mine"})["results"]
        self.assertTrue(info["elevated"])
        self.assertEqual(info["reason"], "why")

    def test_elevation_requires_a_reason(self):
        result = self.plugin._request_elevation({"_session": "mine", "reason": ""})
        self.assertEqual(result["status"], "error")
        self.assertIn("reason is required", result["error"])


class TestAdminClose(RegistryTest):
    def setUp(self):
        super().setUp()
        self.plugin._elevated["admin"] = {"granted_at": 0, "reason": "cleanup"}
        # mark the owner as recently active so notifications are kept
        self.plugin._last_seen["owner"] = MODULE.time.time()

    def test_closing_another_sessions_image_requires_a_reason(self):
        open_canvas(self.plugin, "owner", "theirs")
        result = self.plugin._close_image({"image": "theirs", "_session": "admin"})
        self.assertEqual(result["status"], "error")
        self.assertIn("requires reason", result["error"])
        self.assertEqual(len(FakeGimp.get_images()), 1)

    def test_admin_close_notifies_the_owner(self):
        open_canvas(self.plugin, "owner", "theirs")
        result = self.plugin._close_image({
            "image": "theirs", "_session": "admin",
            "reason": "stale canvas from a crashed run",
        })
        self.assertEqual(result["status"], "success", result)
        self.assertTrue(result["results"]["as_administrator"])
        self.assertTrue(result["results"]["owner_notified"])
        self.assertEqual(FakeGimp.get_images(), [])

        pending = self.plugin._get_notifications({"_session": "owner"})["results"]
        self.assertEqual(pending["count"], 1)
        note = pending["notifications"][0]
        self.assertEqual(note["type"], "image_closed_by_administrator")
        self.assertEqual(note["handle"], "theirs")
        self.assertEqual(note["closed_by"], "admin")
        self.assertEqual(note["reason"], "stale canvas from a crashed run")

    def test_notifications_are_delivered_once(self):
        open_canvas(self.plugin, "owner", "theirs")
        self.plugin._close_image({
            "image": "theirs", "_session": "admin", "reason": "because",
        })
        first = self.plugin._get_notifications({"_session": "owner"})["results"]
        second = self.plugin._get_notifications({"_session": "owner"})["results"]
        self.assertEqual(first["count"], 1)
        self.assertEqual(second["count"], 0)

    def test_no_notification_for_a_session_long_gone(self):
        open_canvas(self.plugin, "ghost", "theirs")
        self.plugin._last_seen["ghost"] = MODULE.time.time() - 99999
        result = self.plugin._close_image({
            "image": "theirs", "_session": "admin", "reason": "cleanup",
        })
        self.assertTrue(result["results"]["closed"])
        self.assertFalse(result["results"]["owner_notified"])

    def test_closing_your_own_image_is_not_an_admin_action(self):
        open_canvas(self.plugin, "admin", "mine")
        result = self.plugin._close_image({"image": "mine", "_session": "admin"})
        self.assertEqual(result["status"], "success", result)
        self.assertFalse(result["results"]["as_administrator"])

    def test_close_my_images_never_touches_other_sessions(self):
        """Elevation widens what you can name; it must not widen this."""
        open_canvas(self.plugin, "owner", "theirs")
        open_canvas(self.plugin, "admin", "ours")
        result = self.plugin._close_my_images({"_session": "admin"})["results"]
        self.assertEqual(result["closed_count"], 1)
        remaining = [i.get_name() for i in FakeGimp.get_images()]
        self.assertEqual(remaining, ["theirs"])


class TestReviewFindings(RegistryTest):
    """Regression pins for defects an adversarial review found.

    Each of these passed review only after a fix; they exist so the fix cannot
    quietly come back out.
    """

    # -- F2: reseat must never destroy an image ---------------------------
    def test_reseat_rolls_back_rather_than_destroying_an_image(self):
        keep, _ = open_canvas(self.plugin, "s1", "keepme")
        other, _ = open_canvas(self.plugin, "s1", "other")

        real_new = FakeDisplay.new

        def flaky(image):
            if image is keep:
                raise RuntimeError("Gimp.Display.new returned NULL")
            return real_new(image)

        FakeDisplay.new = staticmethod(flaky)
        try:
            with self.assertRaises(RuntimeError) as caught:
                self.plugin._reseat_displays()
        finally:
            FakeDisplay.new = staticmethod(real_new)

        self.assertIn("nothing was reseated", str(caught.exception))
        # Both images must still be open: losing unsaved work is the worst case.
        self.assertEqual(set(FakeGimp.get_images()), {keep, other})

    # -- F3: the no-argument path must respect ownership ------------------
    def test_lone_image_of_a_live_session_is_not_borrowed(self):
        open_canvas(self.plugin, "other", "theirs")
        with self.assertRaises(RuntimeError) as caught:
            self.plugin._resolve_image({"_session": "mine"})
        self.assertIn("belongs to another session", str(caught.exception))

    def test_revoking_elevation_drops_the_remembered_image(self):
        open_canvas(self.plugin, "other", "theirs")
        self.plugin._elevated["mine"] = {"granted_at": 0, "reason": "x"}
        self.plugin._resolve_image({"image": "theirs", "_session": "mine"})
        self.assertEqual(self.plugin._current["mine"], 1)

        self.plugin._revoke_elevation({"_session": "mine"})
        with self.assertRaises(RuntimeError):
            self.plugin._resolve_image({"_session": "mine"})

    # -- F4: a restarted client must not be locked out --------------------
    def test_images_of_a_vanished_session_are_reclaimable(self):
        open_canvas(self.plugin, "old-session", "work")
        # The client restarted: the old id never speaks again.
        self.plugin._last_seen["old-session"] = MODULE.time.time() - 99999
        resolved = self.plugin._resolve_image({"image": "work", "_session": "new"})
        self.assertEqual(resolved.get_name(), "work")

    def test_a_live_session_is_still_protected(self):
        open_canvas(self.plugin, "live", "work")
        with self.assertRaises(RuntimeError):
            self.plugin._resolve_image({"image": "work", "_session": "new"})

    # -- F5: bulk operations need the same permission ---------------------
    def test_batch_resize_all_images_needs_elevation(self):
        open_canvas(self.plugin, "mine", "ours")
        open_canvas(self.plugin, "other", "theirs")
        result = self.plugin._batch_resize({
            "_session": "mine", "width": 10, "height": 10,
            "output_dir": "/tmp", "all_images": True,
        })
        self.assertEqual(result["status"], "error")
        self.assertIn("administrator access", result["error"])

    def test_batch_resize_all_images_allowed_once_elevated(self):
        open_canvas(self.plugin, "mine", "ours")
        open_canvas(self.plugin, "other", "theirs")
        self.plugin._elevated["mine"] = {"granted_at": 0, "reason": "x"}
        result = self.plugin._batch_resize({
            "_session": "mine", "scale_factor": 0.5, "all_images": True,
        })
        self.assertEqual(result["status"], "success", result)
        # Elevation means it really does reach the other session's image.
        self.assertEqual(result["results"]["count"], 2)

    def test_sprite_sheet_all_images_needs_elevation(self):
        open_canvas(self.plugin, "mine", "ours")
        result = self.plugin._export_sprite_sheet({
            "_session": "mine", "source": "images",
            "output_path": "/tmp/s.png", "all_images": True,
        })
        self.assertEqual(result["status"], "error")
        self.assertIn("administrator access", result["error"])

    # -- F12: batch_export defaults to this session's images --------------
    def test_batch_export_defaults_to_mine_only(self):
        open_canvas(self.plugin, "mine", "ours")
        open_canvas(self.plugin, "other", "theirs")
        result = self.plugin._batch_export(
            {"_session": "mine", "output_dir": "/tmp"}
        )
        # Whether the export succeeds against stubs does not matter; the target
        # set does. Exactly one image should have been attempted.
        r = result["results"]
        attempted = len(r.get("exported", [])) + len(r.get("errors", []))
        self.assertEqual(attempted, 1, r)

    def test_batch_export_all_images_needs_elevation(self):
        open_canvas(self.plugin, "mine", "ours")
        open_canvas(self.plugin, "other", "theirs")
        result = self.plugin._batch_export({
            "_session": "mine", "output_dir": "/tmp", "mine_only": False,
        })
        self.assertEqual(result["status"], "error")
        self.assertIn("administrator access", result["error"])

    # -- F11: taking a live session's image is an accountable act ---------
    def test_adopting_a_live_sessions_image_needs_a_reason(self):
        open_canvas(self.plugin, "owner", "theirs")
        self.plugin._elevated["admin"] = {"granted_at": 0, "reason": "x"}
        result = self.plugin._adopt_image(
            {"image": "theirs", "_session": "admin"}
        )
        self.assertEqual(result["status"], "error")
        self.assertIn("reason", result["error"])

    def test_adopting_a_live_sessions_image_notifies_them(self):
        open_canvas(self.plugin, "owner", "theirs")
        self.plugin._elevated["admin"] = {"granted_at": 0, "reason": "x"}
        result = self.plugin._adopt_image({
            "image": "theirs", "_session": "admin", "reason": "taking over",
        })
        self.assertEqual(result["status"], "success", result)
        pending = self.plugin._get_notifications({"_session": "owner"})["results"]
        self.assertEqual(pending["count"], 1)
        self.assertEqual(
            pending["notifications"][0]["type"], "image_adopted_by_administrator"
        )

    def test_adopting_an_abandoned_image_needs_nothing(self):
        open_canvas(self.plugin, "ghost", "theirs")
        self.plugin._last_seen["ghost"] = MODULE.time.time() - 99999
        result = self.plugin._adopt_image(
            {"image": "theirs", "_session": "mine"}
        )
        self.assertEqual(result["status"], "success", result)
        self.assertTrue(result["results"]["mine"])

    # -- F9: a failed delivery must not lose the notification -------------
    def test_requeued_notification_is_not_lost(self):
        self.plugin._last_seen["owner"] = MODULE.time.time()
        self.plugin._notify("owner", {"type": "x", "message": "one"})
        taken = self.plugin._take_notifications("owner")
        self.assertEqual(len(taken), 1)
        for note in reversed(taken):
            self.plugin._requeue_notification("owner", note)
        again = self.plugin._get_notifications({"_session": "owner"})["results"]
        self.assertEqual(again["count"], 1)
        self.assertEqual(again["notifications"][0]["message"], "one")


class TestSessionInfo(RegistryTest):
    def test_reports_mine_versus_theirs(self):
        open_canvas(self.plugin, "mine", "a")
        open_canvas(self.plugin, "other", "b")
        info = self.plugin._session_info({"_session": "mine"})["results"]
        self.assertEqual(info["my_count"], 1)
        self.assertEqual(info["other_count"], 1)
        self.assertEqual(info["total_open"], 2)
        self.assertEqual(info["session"], "mine")


class TestConfig(unittest.TestCase):
    def test_defaults_when_no_file(self):
        MODULE.Gimp.directory = staticmethod(lambda: "/tmp/does-not-exist-xyz")
        cfg = MODULE.load_config()
        self.assertFalse(cfg["autostart"])
        self.assertEqual(cfg["port"], 9877)

    def test_round_trips(self):
        import tempfile

        tmp = tempfile.mkdtemp()
        MODULE.Gimp.directory = staticmethod(lambda: tmp)
        MODULE.save_config({"autostart": True, "port": 9999, "host": "localhost"})
        cfg = MODULE.load_config()
        self.assertTrue(cfg["autostart"])
        self.assertEqual(cfg["port"], 9999)

    def test_unreadable_config_falls_back_to_defaults(self):
        import tempfile

        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, MODULE.CONFIG_NAME), "w") as fh:
            fh.write("{ not json")
        MODULE.Gimp.directory = staticmethod(lambda: tmp)
        cfg = MODULE.load_config()
        self.assertFalse(cfg["autostart"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
