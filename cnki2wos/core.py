"""Pure conversion logic for CNKI RefWorks text to WOS tagged text."""

from __future__ import annotations

from collections import Counter
import codecs
from dataclasses import dataclass, replace
import hashlib
import os
from pathlib import Path
import re
import tempfile


FIELD_RE = re.compile(r"^([A-Za-z0-9]{2})\s+(.*)$")
RECORD_START_RE = re.compile(r"^(?:RT|PT)\s+")
PAGE_SEPARATOR_RE = re.compile(r"\s*[-–—]\s*")
SUPPORTED_RECORD_TYPE = "journal article"


class ConversionError(ValueError):
    """Raised when an input file cannot be converted safely."""


@dataclass(frozen=True)
class ConversionResult:
    output_text: str
    input_records: int
    output_records: int
    duplicate_records: int
    skipped_records: int
    input_encoding: str = "text"
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class _SourceRecord:
    lines: tuple[str, ...]
    fields: dict[str, str]

    @property
    def canonical_text(self) -> str:
        return "\n".join(line.strip() for line in self.lines if line.strip())


def _split_records(text: str) -> tuple[list[tuple[str, ...]], int]:
    records: list[tuple[str, ...]] = []
    current: list[str] = []
    ignored_preamble_lines = 0

    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line:
            continue
        if RECORD_START_RE.match(line):
            if current:
                records.append(tuple(current))
            current = [line]
        elif current:
            current.append(line)
        else:
            ignored_preamble_lines += 1

    if current:
        records.append(tuple(current))
    return records, ignored_preamble_lines


def _parse_record(lines: tuple[str, ...]) -> _SourceRecord:
    fields: dict[str, str] = {}
    current_key: str | None = None

    for line in lines:
        match = FIELD_RE.match(line)
        if match:
            key, value = match.groups()
            if key in fields and value:
                fields[key] = f"{fields[key]}; {value}"
            else:
                fields[key] = value.strip()
            current_key = key
        elif current_key:
            fields[current_key] = f"{fields[current_key]} {line.strip()}".strip()

    return _SourceRecord(lines=lines, fields=fields)


def _append_tag(lines: list[str], tag: str, value: str) -> None:
    value = value.strip()
    if value:
        lines.append(f"{tag} {value}")


def _append_people(lines: list[str], tag: str, people: list[str]) -> None:
    if not people:
        return
    lines.append(f"{tag} {people[0]}")
    lines.extend(f"   {person}" for person in people[1:])


def _authors(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;；]", value) if part.strip()]


def _keywords(value: str) -> str:
    return "; ".join(part.strip() for part in re.split(r"[;；]", value) if part.strip())


def _doi(value: str) -> str:
    return re.sub(
        r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    )


def _language(value: str) -> str:
    known = {"chi": "Chinese", "zh": "Chinese", "eng": "English", "en": "English"}
    return known.get(value.strip().casefold(), value.strip())


def _volume(fields: dict[str, str]) -> str:
    return fields.get("vo") or fields.get("VO") or fields.get("VL", "")


def _page_fields(value: str) -> tuple[str, str, str]:
    page_text = value.strip()
    if not page_text:
        return "", "", ""

    parts = PAGE_SEPARATOR_RE.split(page_text, maxsplit=1)
    begin = parts[0].strip()
    end = parts[1].strip() if len(parts) == 2 else begin
    page_count = ""
    if begin.isdigit() and end.isdigit():
        count = int(end) - int(begin) + 1
        if count > 0:
            page_count = str(count)
    return begin, end, page_count


def _convert_record(record: _SourceRecord, unique_tag: str) -> list[str]:
    fields = record.fields
    lines = ["PT J"]

    authors = _authors(fields.get("A1", ""))
    _append_people(lines, "AU", authors)
    _append_people(lines, "AF", authors)
    _append_tag(lines, "TI", fields.get("T1", ""))
    _append_tag(lines, "SO", fields.get("JF", ""))
    _append_tag(lines, "LA", _language(fields.get("LA", "")))
    lines.append("DT Article")
    _append_tag(lines, "DE", _keywords(fields.get("K1", "")))
    _append_tag(lines, "AB", fields.get("AB", ""))
    _append_tag(lines, "C1", fields.get("AD", ""))
    _append_tag(lines, "SN", fields.get("SN", ""))
    _append_tag(lines, "DI", _doi(fields.get("DO", "")))
    _append_tag(lines, "UR", fields.get("LK", ""))
    _append_tag(lines, "PY", fields.get("YR", ""))
    _append_tag(lines, "VL", _volume(fields))
    _append_tag(lines, "IS", fields.get("IS", ""))

    begin, end, page_count = _page_fields(fields.get("OP", ""))
    _append_tag(lines, "BP", begin)
    _append_tag(lines, "EP", end)
    _append_tag(lines, "PG", page_count)
    lines.append(f"UT {unique_tag}")
    lines.append("ER")
    return lines


def convert_text(text: str) -> ConversionResult:
    """Convert CNKI RefWorks tagged text into WOS-style tagged text."""
    raw_records, ignored_preamble = _split_records(text)
    if not raw_records:
        raise ConversionError("未找到以 RT 或 PT 开头的文献记录。")

    parsed_records = [_parse_record(lines) for lines in raw_records]
    canonical_counts: Counter[str] = Counter()
    converted: list[list[str]] = []
    missing_title = 0
    unsupported_type = 0

    for record in parsed_records:
        fields = record.fields
        if not fields.get("T1", "").strip():
            missing_title += 1
            continue
        if fields.get("RT", "").strip().casefold() != SUPPORTED_RECORD_TYPE:
            unsupported_type += 1
            continue

        canonical = record.canonical_text
        canonical_counts[canonical] += 1
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        occurrence = canonical_counts[canonical]
        unique_tag = f"CNKI:{digest}" if occurrence == 1 else f"CNKI:{digest}-{occurrence}"
        converted.append(_convert_record(record, unique_tag))

    if not converted:
        raise ConversionError("没有可转换的 Journal Article 记录。")

    duplicate_count = sum(count - 1 for count in canonical_counts.values() if count > 1)
    warnings: list[str] = []
    if duplicate_count:
        warnings.append(f"保留了 {duplicate_count} 条完全重复记录，并为其生成了唯一 UT。")
    if missing_title:
        warnings.append(f"跳过了 {missing_title} 条缺少标题的记录。")
    if unsupported_type:
        warnings.append(f"跳过了 {unsupported_type} 条非 Journal Article 记录。")
    if ignored_preamble:
        warnings.append(f"忽略了记录开始前的 {ignored_preamble} 行内容。")

    output_lines = ["FN CNKI2WOS", "VR 1.0", ""]
    for index, record_lines in enumerate(converted):
        if index:
            output_lines.append("")
        output_lines.extend(record_lines)
    output_lines.extend(["", "EF", ""])

    skipped = missing_title + unsupported_type
    return ConversionResult(
        output_text="\n".join(output_lines),
        input_records=len(raw_records),
        output_records=len(converted),
        duplicate_records=duplicate_count,
        skipped_records=skipped,
        warnings=tuple(warnings),
    )


def _read_source(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    if raw.startswith(codecs.BOM_UTF8):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ConversionError("输入文件不是有效的 UTF-8、UTF-8 BOM 或 GB18030 文本。")


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def convert_file(input_path: str | Path, output_path: str | Path) -> ConversionResult:
    """Convert one file and atomically replace the requested output file."""
    source = Path(input_path)
    destination = Path(output_path)
    if _same_path(source, destination):
        raise ConversionError("输入文件和输出文件不能是同一路径。")
    if not source.is_file():
        raise ConversionError(f"找不到输入文件：{source}")
    if not destination.parent.is_dir():
        raise ConversionError(f"输出目录不存在：{destination.parent}")

    text, encoding = _read_source(source)
    result = replace(convert_text(text), input_encoding=encoding)

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(result.output_text)
            temporary_name = temporary.name
        os.replace(temporary_name, destination)
    except OSError as exc:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)
        raise ConversionError(f"写入输出文件失败：{exc}") from exc

    return result
