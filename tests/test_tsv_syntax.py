"""Candidate and lightweight highlighting rules, independent of Tk."""

import unittest

from python_to_exe.editor.tsv_syntax import (
    CANDIDATES, CompletionState, PALETTE_CATEGORIES, candidates_for,
    classify_cell, completion_span, insert_template, syntax_spans,
)


class SyntaxHintsTests(unittest.TestCase):
    def test_palette_metadata_does_not_change_inserted_syntax(self):
        dpad = next(item for item in CANDIDATES if item.text == "dp-u")
        self.assertEqual((dpad.display_label, dpad.short_label, dpad.icon_key),
                         ("dp-u", "Up", "dpad_up"))
        self.assertEqual(insert_template("", 0, 0, dpad), ("dp-u", 4, None))
        accel = next(item for item in CANDIDATES if item.category == "accel")
        self.assertIsNone(accel.icon_key)
        self.assertEqual(accel.display_label, accel.label)
        self.assertEqual(insert_template("", 0, 0, accel)[0], accel.text)

    def test_verified_candidate_categories_and_filtering(self):
        self.assertTrue(set(PALETTE_CATEGORIES) <= {item.category for item in CANDIDATES})
        self.assertTrue({"buttons", "left_stick", "right_stick", "accel", "gyro",
                         "cappy", "commands", "notation"} <=
                        {item.category for item in CANDIDATES})
        self.assertIn("a", [item.text for item in candidates_for("a", 1, 1)])
        self.assertIn("ls(0)", [item.text for item in candidates_for("l", 1, 1)])
        self.assertIn("la(0; 0; 0)", [item.text for item in candidates_for("la", 2, 1)])
        self.assertIn("lg(0; 0; 0)", [item.text for item in candidates_for("lg", 2, 1)])
        self.assertIn("ca", [item.text for item in candidates_for("ca", 2, 1)])
        commands = candidates_for("/", 1, 0)
        self.assertEqual({item.text.split()[0] for item in commands},
                         {"/tp", "/ctp", "/absStick", "/speed", "/pause",
                          "/loadFile", "/reloadFile", "/demo"})
        self.assertEqual(candidates_for("/", 1, 1), ())
        self.assertEqual(completion_span("a/ls", 4, 1), (2, 4, "ls"))

    def test_template_replacement_and_placeholder_selection(self):
        stick = next(item for item in CANDIDATES if item.label == "ls(angle)")
        self.assertEqual(insert_template("l", 0, 1, stick), ("ls(0)", 5, (3, 4)))
        self.assertEqual(insert_template("a/l", 2, 3, stick), ("a/ls(0)", 7, (5, 6)))
        pause = next(item for item in CANDIDATES if item.text == "/pause")
        self.assertEqual(insert_template("/", 0, 1, pause), ("/pause", 6, None))
        toggle = next(item for item in CANDIDATES if item.text == "/absStick on")
        self.assertEqual(insert_template("/a", 0, 2, toggle),
                         ("/absStick on", 12, (10, 12)))

    def test_completion_state_navigation_and_close(self):
        state = CompletionState()
        self.assertFalse(state.open)
        state.show(("a", "b", "c"))
        self.assertEqual(state.step(1), "b")
        self.assertEqual(state.step(-1), "a")
        self.assertEqual(state.step(-1), "c")
        state.close()
        self.assertFalse(state.open)
        self.assertIsNone(state.current)

    def test_visual_classification_is_not_validation(self):
        self.assertEqual(classify_cell("// comment", 0), "comment")
        self.assertEqual(classify_cell("/pause", 0), "command")
        self.assertEqual(classify_cell("$angle = 90", 0), "variable")
        self.assertEqual(classify_cell("12", 0), "duration")
        self.assertEqual(classify_cell("ls(90)", 1), "input")
        self.assertEqual(classify_cell("ca", 2), "input")
        self.assertEqual(classify_cell("la(0; 0; 0)", 1), "input")
        self.assertEqual(classify_cell("unknown", 1), None)
        self.assertEqual(syntax_spans("1\ta\tls(90)"),
                         (("duration", 0, 1), ("input", 2, 3), ("input", 4, 10)))
        self.assertEqual(syntax_spans("/pause"), (("command", 0, 6),))


if __name__ == "__main__":
    unittest.main()
