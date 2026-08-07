from pathlib import Path
import re
import tempfile
import unittest

from cnki2wos.core import ConversionError, convert_file, convert_text


SAMPLE = """RT Journal Article
A1 张三;李四
AD 示例大学
T1 示例标题
JF 示例学报
YR 2025
IS 2
vo 10
OP 12-18
K1 关键词一;关键词二
AB 第一行摘要
第二行摘要
SN 0000-0000
DO https://doi.org/10.0000/example
LK https://example.invalid/1
LA chi
"""


class ConvertTextTests(unittest.TestCase):
    def test_maps_supported_fields_and_file_markers(self):
        result = convert_text(SAMPLE)
        output = result.output_text
        self.assertTrue(output.startswith("FN CNKI2WOS\nVR 1.0\n"))
        self.assertTrue(output.endswith("\nEF\n"))
        for expected in (
            "PT J",
            "AU 张三\n   李四",
            "AF 张三\n   李四",
            "TI 示例标题",
            "SO 示例学报",
            "LA Chinese",
            "DT Article",
            "DE 关键词一; 关键词二",
            "AB 第一行摘要 第二行摘要",
            "C1 示例大学",
            "SN 0000-0000",
            "DI 10.0000/example",
            "UR https://example.invalid/1",
            "PY 2025",
            "VL 10",
            "IS 2",
            "BP 12",
            "EP 18",
            "PG 7",
            "ER",
        ):
            self.assertIn(expected, output)
        self.assertNotIn("PD JUN 15", output)
        self.assertNotIn("NR 0", output)
        self.assertNotIn("TC 0", output)

    def test_nonnumeric_pages_are_preserved_without_page_count(self):
        result = convert_text("RT Journal Article\nT1 示例\nOP S1-S5\n")
        self.assertIn("BP S1", result.output_text)
        self.assertIn("EP S5", result.output_text)
        self.assertNotIn("PG ", result.output_text)

    def test_exact_duplicates_are_preserved_with_unique_ut(self):
        result = convert_text(SAMPLE + "\n" + SAMPLE)
        unique_tags = re.findall(r"^UT (.+)$", result.output_text, flags=re.MULTILINE)
        self.assertEqual(result.input_records, 2)
        self.assertEqual(result.output_records, 2)
        self.assertEqual(result.duplicate_records, 1)
        self.assertEqual(len(set(unique_tags)), 2)
        self.assertTrue(unique_tags[1].endswith("-2"))

    def test_output_is_deterministic(self):
        first = convert_text(SAMPLE).output_text
        second = convert_text(SAMPLE).output_text
        self.assertEqual(first, second)

    def test_record_header_accepts_tabs(self):
        result = convert_text("RT\tJournal Article\nT1 制表符记录头\n")
        self.assertEqual(result.output_records, 1)
        self.assertIn("TI 制表符记录头", result.output_text)

    def test_convert_text_accepts_utf8_bom_character(self):
        result = convert_text("\ufeffRT Journal Article\nT1 BOM 记录头\n")
        self.assertEqual(result.output_records, 1)

    def test_missing_title_and_unsupported_type_are_skipped(self):
        text = SAMPLE + "\nRT Journal Article\nA1 无标题作者\n\nRT Book\nT1 一本书\n"
        result = convert_text(text)
        self.assertEqual(result.input_records, 3)
        self.assertEqual(result.output_records, 1)
        self.assertEqual(result.skipped_records, 2)

    def test_empty_or_unsupported_input_fails(self):
        with self.assertRaises(ConversionError):
            convert_text("not a tagged record")
        with self.assertRaises(ConversionError):
            convert_text("RT Book\nT1 一本书\n")


class ConvertFileTests(unittest.TestCase):
    def test_supported_encodings_write_utf8_without_bom(self):
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            with self.subTest(encoding=encoding), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root / "input.txt"
                destination = root / "output.txt"
                source.write_bytes(SAMPLE.encode(encoding))
                result = convert_file(source, destination)
                self.assertEqual(result.output_records, 1)
                self.assertEqual(result.input_encoding, encoding)
                raw = destination.read_bytes()
                self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
                self.assertIn("TI 示例标题", raw.decode("utf-8"))

    def test_input_and_output_must_differ(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "same.txt"
            path.write_text(SAMPLE, encoding="utf-8")
            with self.assertRaises(ConversionError):
                convert_file(path, path)


if __name__ == "__main__":
    unittest.main()
