"""Large analysis caches must not outlive a closed Inspector."""

import gc
import unittest
import weakref
from types import SimpleNamespace

from python_to_exe.editor.debug_csv import DebugFrames
from python_to_exe.editor.frame_inspector import FrameInspector
from python_to_exe.editor.window import EditorWindow


class InspectorCacheLifecycleTests(unittest.TestCase):
    def test_closed_inspector_releases_data_even_if_widget_shell_is_referenced(self):
        frames = DebugFrames(("Frame",), (("0",),), {0: 0}, 1)
        reference = weakref.ref(frames)
        canceled = []
        inspector = SimpleNamespace(frames=frames, _draw_job="idle-draw",
                                    after_cancel=canceled.append, _on_close=None)
        editor = SimpleNamespace(_frame_inspector=inspector,
                                 _inspector_snapshot="large document snapshot")
        inspector._on_close = lambda closed: EditorWindow._frame_inspector_closed(editor, closed)
        del frames

        # Destroy events for child widgets must not discard the live data.
        FrameInspector._on_destroy(inspector, SimpleNamespace(widget=object()))
        self.assertIsNotNone(reference())
        FrameInspector._on_destroy(inspector, SimpleNamespace(widget=inspector))
        gc.collect()
        self.assertEqual(canceled, ["idle-draw"])
        self.assertIsNone(reference())
        self.assertIsNone(inspector.frames)
        self.assertIsNone(inspector._draw_job)
        self.assertIsNone(inspector._on_close)
        self.assertIsNone(editor._frame_inspector)
        self.assertIsNone(editor._inspector_snapshot)

    def test_old_close_callback_does_not_clear_a_replacement_inspector(self):
        replacement = object()
        editor = SimpleNamespace(_frame_inspector=replacement,
                                 _inspector_snapshot="current snapshot")
        EditorWindow._frame_inspector_closed(editor, object())
        self.assertIs(editor._frame_inspector, replacement)
        self.assertEqual(editor._inspector_snapshot, "current snapshot")


if __name__ == "__main__":
    unittest.main()
