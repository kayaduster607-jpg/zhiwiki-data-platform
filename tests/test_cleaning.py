"""Behavioral checks for conservative and repeatable cleaning."""

import unittest

from zhiwiki.cleaning import clean_text


class CleaningTests(unittest.TestCase):
    def test_normalizes_without_losing_content(self):
        result = clean_text("甲  \r\n\r\n\r\n\r\n乙\t")
        self.assertEqual(result["text"], "甲\n\n\n乙")
        self.assertTrue(result["changed"])
        self.assertEqual(result["changes"]["trailing_whitespace_lines"], 2)
        self.assertEqual(result["changes"]["blank_line_runs_reduced"], 1)

    def test_second_pass_does_not_change_document(self):
        cleaned = clean_text("条目一\n\n条目二")
        self.assertFalse(cleaned["changed"])
        self.assertEqual(clean_text(cleaned["text"])["text"], cleaned["text"])


if __name__ == "__main__":
    unittest.main()
