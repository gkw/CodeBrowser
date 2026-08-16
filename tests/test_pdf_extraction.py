from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import server


class PdfExtractionTests(unittest.TestCase):
    def test_single_byte_ranges_support_open_ended_and_suffix_forms(self) -> None:
        self.assertEqual(server.parse_byte_range("bytes=2-5", 10), (2, 5))
        self.assertEqual(server.parse_byte_range("bytes=7-", 10), (7, 9))
        self.assertEqual(server.parse_byte_range("bytes=-3", 10), (7, 9))
        with self.assertRaises(ValueError):
            server.parse_byte_range("bytes=20-30", 10)

    def test_page_formatter_adds_page_markers_and_bounds_text(self) -> None:
        content, pages, truncated = server._format_pdf_pages("first page\fsecond page\f", 35)
        self.assertIn("[Page 1]", content)
        self.assertIn("[Page 2]", content)
        self.assertLessEqual(len(content), 35)
        self.assertEqual(pages, 2)
        self.assertTrue(truncated)

    def test_pdf_size_limit_is_separate_from_source_file_limit(self) -> None:
        self.assertGreater(server.MAX_PDF_BYTES, server.MAX_FILE_BYTES)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.pdf"
            with path.open("wb") as output:
                output.truncate(server.MAX_PDF_BYTES + 1)
            with self.assertRaisesRegex(server.PdfExtractionError, "PDF is too large"):
                server.extract_pdf_text(path)


if __name__ == "__main__":
    unittest.main()
