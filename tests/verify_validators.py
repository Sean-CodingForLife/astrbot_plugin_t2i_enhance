"""One-off verification for the v1.2.0 enhancements.

The functions under test are extracted from main.py via AST and executed, so
this exercises the shipped source rather than a re-typed copy. Everything the
extracted code needs at runtime (re, hashlib, Path, a logger, __file__) is
injected, and ``from __future__ import annotations`` is prepended so the type
annotations are never evaluated.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import sys
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

REPO = pathlib.Path(__file__).resolve().parent.parent
MAIN = REPO / "main.py"
src = MAIN.read_text(encoding="utf-8")
tree = ast.parse(src)

WANT_ASSIGN = {
    "PLUGIN_VERSION",
    "PLUGIN_DIR",
    "UNSAFE_URL_CHARS_RE",
    "_WARNED_STRFTIME_FORMATS",
    "_MAX_WARNED_STRFTIME_FORMATS",
    "JINJA_SEGMENT_RE",
    "UNSAFE_HTML_PATTERNS",
    "UNSAFE_JINJA_PATTERNS",
}
WANT_FUNC = {
    "config_fingerprint",
    "as_string_list",
    "_url_scheme",
    "normalize_background_candidates",
    "resolve_template_path",
    "read_template_file",
    "template_file_fingerprint",
    "format_time",
    "validate_template_html",
}
WANT_CLASS = {"UnsafeTemplateError"}

chunks: list[str] = []
for node in tree.body:
    if isinstance(node, ast.Assign):
        if {t.id for t in node.targets if isinstance(t, ast.Name)} & WANT_ASSIGN:
            chunks.append(ast.get_source_segment(src, node) or "")
    elif isinstance(node, ast.AnnAssign):
        if isinstance(node.target, ast.Name) and node.target.id in WANT_ASSIGN:
            chunks.append(ast.get_source_segment(src, node) or "")
    elif isinstance(node, ast.ClassDef) and node.name in WANT_CLASS:
        chunks.append(ast.get_source_segment(src, node) or "")
    elif isinstance(node, ast.FunctionDef) and node.name in WANT_FUNC:
        chunks.append(ast.get_source_segment(src, node) or "")

assert all(chunks), "ast.get_source_segment returned None"
missing = sorted((WANT_FUNC | WANT_CLASS | WANT_ASSIGN) - {n for c in chunks for n in [c[4:].split("(")[0].split(":")[0].strip().split()[0]]})
print(f"extracted {len(chunks)} definition(s) from {MAIN}")


class RecordingLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _add(self, level: str, msg: Any, *args: Any) -> None:
        try:
            text = msg % args if args else str(msg)
        except Exception:
            text = str(msg)
        self.records.append((level, text))

    def warning(self, msg: Any, *a: Any, **k: Any) -> None:
        self._add("warning", msg, *a)

    def info(self, msg: Any, *a: Any, **k: Any) -> None:
        self._add("info", msg, *a)

    def debug(self, msg: Any, *a: Any, **k: Any) -> None:
        self._add("debug", msg, *a)

    def exception(self, msg: Any, *a: Any, **k: Any) -> None:
        self._add("exception", msg, *a)

    def warned(self, needle: str) -> bool:
        return any(level in ("warning", "exception") and needle in text for level, text in self.records)


logger = RecordingLogger()
ns: dict[str, Any] = {
    "re": re,
    "hashlib": hashlib,
    "Path": pathlib.Path,
    "urlparse": urlparse,
    "datetime": datetime,
    "logger": logger,
    "__file__": str(MAIN.resolve()),
    "__name__": "extracted",
}
exec(compile("from __future__ import annotations\n\n" + "\n\n".join(chunks), "<extracted>", "exec"), ns)

failures = 0
skips = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        print(f"PASS  {label}")
    else:
        failures += 1
        print(f"FAIL  {label}  {detail}")


ROOT: pathlib.Path = ns["PLUGIN_DIR"]
resolve_path = ns["resolve_template_path"]
read_file = ns["read_template_file"]
file_fp = ns["template_file_fingerprint"]
bg = ns["normalize_background_candidates"]
fmt_time = ns["format_time"]
validate = ns["validate_template_html"]
unsafe_error = ns["UnsafeTemplateError"]

print(f"\nPLUGIN_VERSION = {ns['PLUGIN_VERSION']}")
print(f"PLUGIN_DIR     = {ROOT}")
print()

print("--- resolve_template_path: containment ---")
check("relative path resolves under the plugin dir",
      resolve_path("templates/paper-light.html") == ROOT / "templates" / "paper-light.html")
check("inner '..' that stays inside is allowed",
      resolve_path("templates/../icon.svg") == ROOT / "icon.svg")
check("'..' traversal out of the plugin dir is rejected",
      resolve_path("../../../Windows/win.ini") is None)
check("drive-absolute path is rejected",
      resolve_path("C:/Windows/win.ini") is None)
check("root-absolute path is rejected",
      resolve_path("/etc/passwd") is None)
check("backslash traversal is rejected",
      resolve_path("..\\..\\secret.txt") is None)
check("blank / wrong type is rejected",
      resolve_path("   ") is None and resolve_path(None) is None and resolve_path(123) is None)

print("\n--- read_template_file ---")
body = read_file("templates/paper-light.html", "t")
check("reads a real template file", "{{ content | safe }}" in body, f"len={len(body)}")
check("missing file yields ''", read_file("templates/does-not-exist.html", "t") == "")
logger.records.clear()
check("escaping path yields ''", read_file("../../secret.txt", "t") == "")
check("escaping path warns", logger.warned("must stay inside"))
logger.records.clear()
check("blank value yields '' silently", read_file("", "t") == "" and not logger.records)

print("\n--- template_file_fingerprint: file edits must invalidate the cache ---")
scratch = ROOT / "_scratch_tpl.html"
scratch.write_text("<article>A</article>", encoding="utf-8")
profiles = [{"name": "s", "template_file": "_scratch_tpl.html"}]
f1 = file_fp(profiles)
scratch.write_text("<article>BBBB</article>", encoding="utf-8")
f2 = file_fp(profiles)
check("fingerprint changes after editing the file", bool(f1) and bool(f2) and f1 != f2, f"{f1} vs {f2}")
scratch.unlink()
f3 = file_fp(profiles)
check("fingerprint changes after deleting the file", f3 != f2 and bool(f3))
check("profiles without template_file contribute nothing", file_fp([{"name": "x"}]) == "")
check("non-list input is tolerated", file_fp("nonsense") == "" and file_fp(None) == "")

print("\n--- normalize_background_candidates: URL tightening ---")
logger.records.clear()
kept = bg(
    [
        "https://a.example/x.png",
        "https://a.example/x.png",
        'https://a.example/a");background:url("b',
        "https://a.example/sp ace.png",
        "javascript:alert(1)",
        "/relative/x.png",
        "https://ok.example/y.png",
    ],
    ("http", "https", "data"),
)
check("keeps only clean absolute http(s) URLs, deduplicated",
      kept == ("https://a.example/x.png", "https://ok.example/y.png"), repr(kept))
check("rejected the quote/space/javascript/relative entries",
      logger.warned("unsafe") and logger.warned("disallowed protocol"))

print("\n--- format_time: invalid directives must not raise, and warn once ---")
check("valid format still works", fmt_time(datetime(2026, 10, 6, 12, 0, 0), "%Y-%m-%d") == "2026-10-06")
check("non-str format is tolerated",
      isinstance(fmt_time(datetime(2026, 10, 6, 12, 0, 0), None), str))  # type: ignore[arg-type]
logger.records.clear()
fmt_time(datetime(2026, 10, 6), "%Q")
raised_invalid = logger.warned("invalid strftime format")
if raised_invalid:
    for _ in range(5):
        fmt_time(datetime(2026, 10, 6), "%Q")
    n = sum(1 for _, t in logger.records if "invalid strftime format" in t)
    check("a bad format warns exactly once across repeated renders", n == 1, f"warned {n}x")
else:
    skips += 1
    print("SKIP  bad-format warning: this platform passes unknown directives through")

print("\n--- regression: the template validator still behaves ---")
for path in sorted((REPO / "templates").glob("*.html")):
    text = path.read_text(encoding="utf-8")
    try:
        validate(text)
    except unsafe_error as exc:
        check(f"{path.name} passes", False, str(exc))
    else:
        check(f"{path.name} passes", True)
controls = {
    "script tag": "<div><script>alert(1)</script></div>",
    "event handler": '<img src="a.png" onerror="steal()">',
    "jinja dunder": "{{ ''.__class__ }}",
    "jinja loader": "{% include 'x.html' %}",
    "flask g": "{{ g.user }}",
}
for label, payload in controls.items():
    try:
        validate(payload)
    except unsafe_error:
        check(f"control rejected: {label}", True)
    else:
        check(f"control rejected: {label}", False, "validator missed it")

print()
print("RESULT:", "ALL OK" if failures == 0 else f"{failures} FAILURE(S)", f"({skips} skipped)")
sys.exit(1 if failures else 0)
