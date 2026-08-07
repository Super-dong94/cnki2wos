from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
EXE_NAME = "CNKI2WOS_1.0.0_Windows_x64.exe"
REQUIRED = (
    "README.md",
    "LICENSE",
    "CHANGELOG.md",
    "THIRD_PARTY_NOTICES.md",
    "cnki2wos/core.py",
    "cnki2wos/gui.py",
    "samples/sample_cnki.txt",
    "samples/sample_wos.txt",
    "tests/test_core.py",
    ".github/workflows/validate.yml",
    "docs/images/gui.png",
)
FORBIDDEN_NAMES = {"input.txt", "output.txt", "download_1_500.txt", ".ipynb_checkpoints", "build"}
SECRET_PATTERNS = (
    re.compile(r"C:\\Users\\", re.IGNORECASE),
    re.compile(r"[A-Z]:\\BaiduSyncdisk", re.IGNORECASE),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gho_[A-Za-z0-9]+"),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
)


def fail(message: str) -> None:
    print(f"ERROR: {message}")
    raise SystemExit(1)


def tracked_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [ROOT / name for name in completed.stdout.decode("utf-8").split("\0") if name]


def validate_files() -> None:
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            fail(f"缺少文件：{relative}")
    for path in tracked_files():
        if path.name in FORBIDDEN_NAMES or path.suffix in {".pyc", ".ipynb"}:
            fail(f"发现不应发布的路径：{path.relative_to(ROOT)}")


def validate_version() -> None:
    init_text = (ROOT / "cnki2wos/__init__.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name, text in (("__init__.py", init_text), ("pyproject.toml", pyproject), ("README.md", readme)):
        if "1.0.0" not in text:
            fail(f"{name} 中缺少版本 1.0.0")


def validate_sample() -> None:
    sys.path.insert(0, str(ROOT))
    from cnki2wos import convert_text

    source = (ROOT / "samples/sample_cnki.txt").read_text(encoding="utf-8")
    expected = (ROOT / "samples/sample_wos.txt").read_text(encoding="utf-8")
    actual = convert_text(source).output_text
    if actual != expected:
        fail("虚构样例输出与当前转换器不一致")


def validate_text_safety() -> None:
    for path in tracked_files():
        if not path.is_file() or path.suffix.lower() in {".exe", ".png"}:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        if path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                fail(f"发现本机路径或凭据模式：{path.relative_to(ROOT)}")


def validate_dist() -> None:
    exe = ROOT / "dist" / EXE_NAME
    sums = ROOT / "dist/SHA256SUMS.txt"
    if not exe.is_file() or not sums.is_file():
        fail("缺少 EXE 或 SHA256SUMS.txt")
    expected_line = sums.read_text(encoding="ascii").strip()
    digest = hashlib.sha256(exe.read_bytes()).hexdigest()
    if expected_line != f"{digest}  {EXE_NAME}":
        fail("EXE 的 SHA-256 与 SHA256SUMS.txt 不一致")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--require-dist", action="store_true")
    args = parser.parse_args()
    validate_files()
    validate_version()
    validate_sample()
    validate_text_safety()
    if args.require_dist:
        validate_dist()
    print("Repository validation passed.")


if __name__ == "__main__":
    main()
