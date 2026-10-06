"""T2I Enhance — plugin-owned HTML templates for AstrBot text-to-image rendering.

The plugin mirrors AstrBot's own T2I gate (the ``t2i`` switch, the leading
``Plain`` text of the result chain and ``t2i_word_threshold``) but renders with a
template, variables and screenshot options that this plugin owns end to end. It
never reads, binds to, or follows the official T2I templates.

Layering:

1. raw config  -> :func:`normalize_template_profiles` -> :class:`TemplateProfile`
2. result chain -> :func:`collect_leading_plain_text` -> leading text + count
3. leading text -> :func:`render_content` -> sanitized HTML body
4. profile + text -> :func:`T2IEnhancePlugin.build_template_data` -> template vars
5. template + vars -> ``Star.html_render`` -> image path
6. image path -> result chain (plain text in front of it is replaced)
"""

from __future__ import annotations

import hashlib
import inspect
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import bleach
import markdown

try:
    from astrbot import __version__ as astrbot_version
except ImportError:  # pragma: no cover - depends on the AstrBot build
    # Only the cosmetic ``version`` template variable needs this, so a build that
    # stops exporting it must not take the whole plugin down at import time.
    astrbot_version = ""
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Image, Plain

# --------------------------------------------------------------------------- #
# Defaults and constants
# --------------------------------------------------------------------------- #

#: Single source of truth for the version handed to AstrBot. Keep it in sync with
#: ``metadata.yaml`` when releasing.
PLUGIN_VERSION = "1.2.0"

#: Directory this plugin lives in. ``template_file`` values are resolved strictly
#: inside it, so a config entry can never read an arbitrary path off the disk.
PLUGIN_DIR = Path(__file__).resolve().parent

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_DATE_FORMAT = "%Y-%m-%d"
DEFAULT_TIME_FORMAT = "%H:%M:%S"
DEFAULT_WEEKDAY_FORMAT = "%A"

DEFAULT_T2I_WORD_THRESHOLD = 150
MIN_T2I_WORD_THRESHOLD = 50

MAX_CUSTOM_VAR_DEPTH = 5

BACKGROUND_SWITCH_MODES = ("random", "sequential", "fixed")
DEFAULT_BACKGROUND_SWITCH_MODE = "random"

#: Base options merged into every render. Whether the t2i endpoint honours each
#: key is up to the endpoint; unknown keys are dropped before they are sent.
DEFAULT_SCREENSHOT_OPTIONS: dict[str, Any] = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
}
ALLOWED_SCREENSHOT_KEYS = frozenset(
    {
        "type",
        "quality",
        "omit_background",
        "full_page",
        "clip",
        "animations",
        "caret",
        "scale",
        "timeout",
    },
)
SCREENSHOT_ENUM_OPTIONS: dict[str, frozenset[str]] = {
    "type": frozenset({"png", "jpeg"}),
    "animations": frozenset({"allow", "disabled"}),
    "caret": frozenset({"hide", "initial"}),
    "scale": frozenset({"css", "device"}),
}
SCREENSHOT_BOOL_OPTIONS = frozenset({"omit_background", "full_page"})
SCREENSHOT_CLIP_KEYS = ("x", "y", "width", "height")

DEFAULT_MARKDOWN_EXTENSIONS = ("extra", "sane_lists", "nl2br", "admonition", "toc")

DEFAULT_ALLOWED_PROTOCOLS = ("http", "https", "data")

DEFAULT_ALLOWED_TAGS = (
    "a",
    "abbr",
    "blockquote",
    "br",
    "code",
    "dd",
    "del",
    "details",
    "div",
    "dl",
    "dt",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "img",
    "ins",
    "kbd",
    "li",
    "mark",
    "ol",
    "p",
    "pre",
    "s",
    "span",
    "strong",
    "sub",
    "summary",
    "sup",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
)

#: ``p`` needs ``class`` because the markdown ``admonition`` extension puts
#: ``admonition-title`` on a paragraph; without it every admonition title loses
#: the hook the bundled templates style.
DEFAULT_ALLOWED_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "a": ("href", "title"),
    "img": ("src", "alt", "title"),
    "code": ("class",),
    "pre": ("class",),
    "span": ("class",),
    "div": ("class",),
    "p": ("class",),
    "th": ("align",),
    "td": ("align",),
}

#: Variable names the plugin injects itself. ``custom_vars_json`` may not
#: redefine them, and ``bg_url`` in particular belongs to ``background_candidates``.
RESERVED_TEMPLATE_VARS = frozenset(
    {
        "text",
        "raw_text",
        "content",
        "html",
        "template_name",
        "bg_url",
        "date",
        "time",
        "datetime",
        "timestamp",
        "timezone",
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
        "weekday",
        "version",
    },
)

SAFE_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SAFE_HTML_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]*$")
SAFE_PROTOCOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")

#: Characters that would let a crafted background URL break out of the CSS
#: ``url("...")`` (or the surrounding markup) it is interpolated into. Templates
#: are usually shared, so the value is tightened before it ever reaches one.
UNSAFE_URL_CHARS_RE = re.compile(r"[\s\"'<>\\`\x00-\x1f\x7f]")

#: Sentinel for "this config value is unusable" in the option validators.
_INVALID = object()

# --------------------------------------------------------------------------- #
# Template security validation
# --------------------------------------------------------------------------- #
#
# ``template_html`` is admin-authored, but shared templates are usually copied
# from somewhere else, and the t2i endpoint renders them in a real browser. The
# checks below are therefore split in two, which keeps false positives low:
#
# * HTML-level constructs are matched against the whole document (a ``<script>``
#   is dangerous anywhere).
# * Code-execution patterns are matched only inside Jinja expressions/blocks, so
#   ordinary prose, CSS and URLs can never trip them.
#
# This is still not a sandbox. The endpoint is expected to run the template in a
# Jinja2 environment; treat ``template_html`` as trusted input.

JINJA_SEGMENT_RE = re.compile(r"\{[{%]-?(.*?)-?[}%]\}", re.DOTALL)

UNSAFE_HTML_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("script tag", re.compile(r"<\s*script\b", re.IGNORECASE)),
    ("inline frame", re.compile(r"<\s*iframe\b", re.IGNORECASE)),
    ("embedded object", re.compile(r"<\s*(?:object|embed|applet)\b", re.IGNORECASE)),
    ("inline event handler", re.compile(r"<[^<>]*\s+on[a-z]+\s*=", re.IGNORECASE)),
    ("javascript URL", re.compile(r"(?:javascript|vbscript)\s*:", re.IGNORECASE)),
    ("inline HTML data URL", re.compile(r"data\s*:\s*text/html", re.IGNORECASE)),
)

UNSAFE_JINJA_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dunder attribute", re.compile(r"__\w*__")),
    (
        "module attribute access",
        re.compile(
            r"\b(?:os|sys|subprocess|shutil|socket|pathlib|builtins|importlib|pickle"
            r"|pty|platform|inspect|ctypes|gc)\b\s*\.",
        ),
    ),
    (
        "code execution",
        re.compile(
            r"\b(?:popen|system|spawn\w*|eval|exec|compile|open|__import__)\s*\(",
        ),
    ),
    (
        "namespace introspection",
        re.compile(r"\b(?:globals|locals|vars|getattr|setattr|delattr|dir)\s*\("),
    ),
    ("jinja attr filter", re.compile(r"\|\s*attr\s*\(")),
    (
        "template introspection",
        re.compile(r"\b(?:self|lipsum|cycler|joiner|namespace)\b"),
    ),
    ("flask context object", re.compile(r"\b(?:config|request|session|g)\b")),
    (
        "template loader",
        re.compile(r"\b(?:include|extends|import|from)\b"),
    ),
)


class UnsafeTemplateError(ValueError):
    """Raised when ``template_html`` contains a blocked construct."""


def validate_template_html(content: str) -> None:
    """Raise :class:`UnsafeTemplateError` when the template is clearly unsafe.

    Blocked templates are skipped instead of rendered, so the caller keeps the
    plain-text path.
    """
    for label, pattern in UNSAFE_HTML_PATTERNS:
        if pattern.search(content):
            raise UnsafeTemplateError(f"unsafe HTML construct ({label})")
    if "{{" in content or "{%" in content:
        for segment in JINJA_SEGMENT_RE.findall(content):
            for label, pattern in UNSAFE_JINJA_PATTERNS:
                if pattern.search(segment):
                    raise UnsafeTemplateError(f"unsafe template expression ({label})")


# --------------------------------------------------------------------------- #
# Generic config helpers
# --------------------------------------------------------------------------- #


def config_get(config: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping-like config, tolerating odd config objects."""
    if config is None:
        return default
    getter = getattr(config, "get", None)
    if callable(getter):
        try:
            value = getter(key, default)
        except TypeError:
            # Some config objects only accept a single argument.
            try:
                value = getter(key)
            except Exception:
                return default
        except Exception:
            return default
        return default if value is None else value
    try:
        value = config[key]
    except Exception:
        return default
    return default if value is None else value


def normalize_t2i_threshold(value: Any) -> int:
    """Mirror AstrBot core's clamping of ``t2i_word_threshold``."""
    try:
        return max(int(value), MIN_T2I_WORD_THRESHOLD)
    except Exception:
        return DEFAULT_T2I_WORD_THRESHOLD


def parse_json_object(raw: Any, label: str) -> dict[str, Any] | None:
    """Parse a JSON object coming from the WebUI.

    Returns the parsed object, ``{}`` for a blank value, or ``None`` when the
    value is present but unusable (so callers can fall back to their defaults
    instead of silently accepting an empty whitelist).
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("[t2i_enhance] %s is not valid UTF-8; ignored.", label)
            return None
    if not isinstance(raw, str):
        logger.warning(
            "[t2i_enhance] %s must be a JSON object, got %s; ignored.",
            label,
            type(raw).__name__,
        )
        return None
    text = raw.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except (ValueError, TypeError, RecursionError):
        logger.warning("[t2i_enhance] invalid JSON in %s; ignored.", label)
        return None
    if not isinstance(data, dict):
        logger.warning("[t2i_enhance] %s must contain a JSON object; ignored.", label)
        return None
    return data


def as_string_list(raw: Any, label: str) -> list[str] | None:
    """Coerce a WebUI list-ish value into a list of trimmed strings.

    Returns ``None`` when the value cannot be interpreted as a list at all, so
    the caller can fall back to its own defaults.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        # Tolerate the comma/space/newline separated form people type by hand.
        parts: list[str] = re.split(r"[,\s]+", raw)
    elif isinstance(raw, (list, tuple, set, frozenset)):
        parts = [str(item) for item in raw]
    else:
        logger.warning(
            "[t2i_enhance] %s must be a list of strings, got %s; using defaults.",
            label,
            type(raw).__name__,
        )
        return None
    return [part.strip() for part in parts if part and part.strip()]


def config_fingerprint(value: Any) -> str:
    """Cheap stable fingerprint used to invalidate the normalized-profile cache."""
    try:
        blob = repr(value).encode("utf-8", "replace")
    except Exception:
        return ""
    return hashlib.blake2b(blob, digest_size=16).hexdigest()


# --------------------------------------------------------------------------- #
# Config normalization
# --------------------------------------------------------------------------- #


def normalize_allowed_attributes(raw: Any) -> dict[str, tuple[str, ...]]:
    """Normalize the bleach attribute whitelist.

    A missing or unparsable value falls back to the defaults; an explicitly
    empty JSON object means "keep no attributes at all".
    """
    data = parse_json_object(raw, "allowed_attributes_json")
    if data is None:
        return dict(DEFAULT_ALLOWED_ATTRIBUTES)

    attributes: dict[str, tuple[str, ...]] = {}
    for tag, values in data.items():
        tag_name = str(tag).strip().lower()
        if not SAFE_HTML_NAME_RE.fullmatch(tag_name):
            logger.warning(
                "[t2i_enhance] ignore invalid allowed_attributes tag: %r",
                tag,
            )
            continue
        if not isinstance(values, (list, tuple, set, frozenset)):
            logger.warning(
                "[t2i_enhance] ignore allowed_attributes entry %r: value must be a list.",
                tag_name,
            )
            continue
        kept = [
            str(value).strip().lower()
            for value in values
            if value and SAFE_HTML_NAME_RE.fullmatch(str(value).strip())
        ]
        if kept:
            attributes[tag_name] = tuple(dict.fromkeys(kept))
    return attributes


def normalize_allowed_tags(raw: Any) -> frozenset[str]:
    items = as_string_list(raw, "allowed_tags")
    if items is None:
        return frozenset(DEFAULT_ALLOWED_TAGS)
    if not items:
        # An explicit empty list means "strip every tag". Say so out loud: losing
        # every tag turns the rendered body into plain text.
        logger.warning(
            "[t2i_enhance] allowed_tags is empty: every HTML tag in the rendered "
            "body will be stripped, leaving only the text.",
        )
        return frozenset()
    tags = {item.lower() for item in items if SAFE_HTML_NAME_RE.fullmatch(item)}
    if not tags:
        logger.warning(
            "[t2i_enhance] allowed_tags has no usable HTML tag names; using defaults.",
        )
        return frozenset(DEFAULT_ALLOWED_TAGS)
    return frozenset(tags)


def normalize_allowed_protocols(raw: Any) -> tuple[str, ...]:
    items = as_string_list(raw, "allowed_protocols")
    if items is None:
        return DEFAULT_ALLOWED_PROTOCOLS
    protocols = tuple(
        dict.fromkeys(
            item.lower() for item in items if SAFE_PROTOCOL_RE.fullmatch(item)
        ),
    )
    if not protocols:
        logger.warning(
            "[t2i_enhance] allowed_protocols is empty or invalid; using defaults.",
        )
        return DEFAULT_ALLOWED_PROTOCOLS
    return protocols


def normalize_markdown_extensions(raw: Any) -> tuple[str, ...]:
    """Drop markdown extensions that this environment cannot load.

    A typo in the extension list would otherwise abort every render, so failing
    once at config time (with a warning) is better than failing per message.
    """
    items = as_string_list(raw, "markdown_extensions")
    if items is None:
        return DEFAULT_MARKDOWN_EXTENSIONS
    accepted: list[str] = []
    for extension in items:
        try:
            markdown.markdown("", extensions=[extension])
        except Exception as exc:
            logger.warning(
                "[t2i_enhance] drop unusable markdown extension %r: %s",
                extension,
                exc,
            )
            continue
        if extension not in accepted:
            accepted.append(extension)
    return tuple(accepted)


def sanitize_custom_var_value(value: Any, depth: int = 0) -> Any:
    """Keep custom variables to plain JSON-ish data with safe key names."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if depth > MAX_CUSTOM_VAR_DEPTH:
        return None
    if isinstance(value, (list, tuple)):
        return [sanitize_custom_var_value(item, depth + 1) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            key_name = str(key).strip()
            if SAFE_VAR_NAME_RE.fullmatch(key_name):
                normalized[key_name] = sanitize_custom_var_value(item, depth + 1)
        return normalized
    return str(value)


def normalize_custom_vars(raw: Any) -> dict[str, Any]:
    data = parse_json_object(raw, "custom_vars_json")
    if not data:
        return {}

    normalized: dict[str, Any] = {}
    for key, value in data.items():
        key_name = str(key).strip()
        if not SAFE_VAR_NAME_RE.fullmatch(key_name):
            logger.warning("[t2i_enhance] ignore invalid custom var name: %r", key)
            continue
        if key_name in RESERVED_TEMPLATE_VARS:
            logger.warning("[t2i_enhance] ignore reserved custom var name: %s", key_name)
            continue
        normalized[key_name] = sanitize_custom_var_value(value)
    return normalized


def validate_clip(value: Any) -> dict[str, float] | None:
    """Playwright's ``clip`` requires all four positive coordinates."""
    if not isinstance(value, dict):
        return None
    clip: dict[str, float] = {}
    for key in SCREENSHOT_CLIP_KEYS:
        item = value.get(key)
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            return None
        if item < 0:
            return None
        clip[key] = item
    if clip["width"] <= 0 or clip["height"] <= 0:
        return None
    return clip


def validate_screenshot_value(key: str, value: Any) -> Any:
    """Return the accepted value for one screenshot option, or ``_INVALID``."""
    if key in SCREENSHOT_ENUM_OPTIONS:
        if isinstance(value, str) and value in SCREENSHOT_ENUM_OPTIONS[key]:
            return value
        return _INVALID
    if key in SCREENSHOT_BOOL_OPTIONS:
        return value if isinstance(value, bool) else _INVALID
    if key == "quality":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= value <= 100
        ):
            return _INVALID
        return int(value)
    if key == "timeout":
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value <= 0
        ):
            return _INVALID
        return value
    if key == "clip":
        clip = validate_clip(value)
        return _INVALID if clip is None else clip
    return _INVALID


def normalize_screenshot_options(raw: Any) -> dict[str, Any]:
    """Merge the user's screenshot options over the plugin defaults."""
    options = dict(DEFAULT_SCREENSHOT_OPTIONS)
    data = parse_json_object(raw, "screenshot_options_json")
    if not data:
        return options

    clip_requested = False
    full_page_requested = False
    for key, value in data.items():
        key_name = str(key)
        if key_name not in ALLOWED_SCREENSHOT_KEYS:
            logger.warning(
                "[t2i_enhance] ignore unsupported screenshot option: %s",
                key_name,
            )
            continue
        accepted = validate_screenshot_value(key_name, value)
        if accepted is _INVALID:
            logger.warning(
                "[t2i_enhance] ignore invalid value for screenshot option %s: %r",
                key_name,
                value,
            )
            continue
        if key_name == "clip":
            clip_requested = True
        elif key_name == "full_page":
            full_page_requested = True
        options[key_name] = accepted

    # Playwright refuses ``clip`` together with ``full_page: true``, and the plugin
    # default forces full_page. Without this, merely configuring a clip would make
    # every render fail, and ``clip`` would be a whitelisted option that can never
    # work.
    if clip_requested and not full_page_requested:
        options.pop("full_page", None)
        logger.info(
            "[t2i_enhance] clip configured without full_page; dropped the default "
            "full_page so the screenshot options stay valid.",
        )
    elif clip_requested and options.get("full_page"):
        logger.warning(
            "[t2i_enhance] clip and full_page=true cannot be combined; the "
            "renderer will most likely reject these screenshot options.",
        )
    return options


def normalize_background_candidates(
    raw: Any,
    allowed_protocols: tuple[str, ...],
) -> tuple[str, ...]:
    """Keep only absolute, deduplicated URLs whose scheme is whitelisted."""
    items = as_string_list(raw, "background_candidates")
    if not items:
        return ()

    allowed = set(allowed_protocols)
    candidates: list[str] = []
    seen: set[str] = set()
    for url in items:
        if url in seen:
            continue
        scheme = _url_scheme(url)
        if scheme is None or scheme not in allowed:
            logger.warning(
                "[t2i_enhance] ignore background with disallowed protocol: %s",
                url,
            )
            continue
        if UNSAFE_URL_CHARS_RE.search(url):
            logger.warning(
                "[t2i_enhance] ignore background with characters that are unsafe "
                "inside a template: %r",
                url,
            )
            continue
        seen.add(url)
        candidates.append(url)
    return tuple(candidates)


def _url_scheme(url: str) -> str | None:
    try:
        scheme = urlparse(url).scheme
    except ValueError:
        return None
    return scheme.lower() or None


_TIMEZONE_CACHE: dict[str, tzinfo] = {}


def resolve_timezone(name: str) -> tzinfo:
    cached = _TIMEZONE_CACHE.get(name)
    if cached is not None:
        return cached
    try:
        resolved: tzinfo = ZoneInfo(name)
    except Exception:
        logger.warning(
            "[t2i_enhance] invalid timezone %r; falling back to UTC.",
            name,
        )
        resolved = timezone.utc
    _TIMEZONE_CACHE[name] = resolved
    return resolved


def timezone_label(resolved: tzinfo, fallback: str) -> str:
    key = getattr(resolved, "key", None)
    if isinstance(key, str) and key:
        return key
    try:
        return str(resolved)
    except Exception:
        return fallback


#: Invalid ``strftime`` formats that were already reported, so a bad format in the
#: config warns once instead of once per rendered message.
_WARNED_STRFTIME_FORMATS: set[str] = set()
_MAX_WARNED_STRFTIME_FORMATS = 64


def format_time(value: datetime, fmt: str, fallback: str = "") -> str:
    """``strftime`` that survives platform-specific format directives.

    Windows raises ``ValueError`` for directives it does not recognise, so a typo
    in a configured format must not abort the render.
    """
    try:
        return value.strftime(fmt)
    except (ValueError, TypeError, OverflowError):
        if (
            isinstance(fmt, str)
            and fmt not in _WARNED_STRFTIME_FORMATS
            and len(_WARNED_STRFTIME_FORMATS) < _MAX_WARNED_STRFTIME_FORMATS
        ):
            _WARNED_STRFTIME_FORMATS.add(fmt)
            logger.warning(
                "[t2i_enhance] invalid strftime format %r; falling back to %r.",
                fmt,
                fallback,
            )
    if fallback:
        try:
            return value.strftime(fallback)
        except (ValueError, TypeError, OverflowError):
            pass
    return value.isoformat()


def unix_timestamp(value: datetime) -> int:
    """Unix seconds, tolerating platforms that reject pre-epoch timestamps."""
    try:
        return int(value.timestamp())
    except (OSError, OverflowError, ValueError):
        return 0


@dataclass(frozen=True)
class TemplateProfile:
    """One normalized ``template_profiles`` entry, ready to render with."""

    name: str
    enabled: bool
    template_html: str
    template_file: str
    inject_datetime: bool
    timezone_name: str
    timezone_label: str
    tz: tzinfo
    datetime_format: str
    date_format: str
    time_format: str
    render_markdown: bool
    sanitize_html_input: bool
    background_candidates: tuple[str, ...]
    background_switch_mode: str
    custom_vars: dict[str, Any]
    screenshot_options: dict[str, Any]
    markdown_extensions: tuple[str, ...]
    allowed_tags: frozenset[str]
    allowed_attributes: dict[str, tuple[str, ...]]
    allowed_protocols: tuple[str, ...]


def build_profile(
    name: str,
    item: dict[str, Any],
    template_html: str,
    template_file: str = "",
) -> TemplateProfile:
    timezone_name = (
        str(item.get("timezone", DEFAULT_TIMEZONE) or "").strip() or DEFAULT_TIMEZONE
    )
    resolved_tz = resolve_timezone(timezone_name)

    raw_switch_mode = item.get(
        "background_switch_mode",
        DEFAULT_BACKGROUND_SWITCH_MODE,
    )
    switch_mode = str(raw_switch_mode or "").strip().lower()
    if switch_mode not in BACKGROUND_SWITCH_MODES:
        if switch_mode:
            logger.warning(
                "[t2i_enhance] unknown background_switch_mode %r in profile %r; using %r.",
                switch_mode,
                name,
                DEFAULT_BACKGROUND_SWITCH_MODE,
            )
        switch_mode = DEFAULT_BACKGROUND_SWITCH_MODE

    allowed_protocols = normalize_allowed_protocols(item.get("allowed_protocols"))

    return TemplateProfile(
        name=name,
        enabled=bool(item.get("enabled", True)),
        template_html=template_html,
        template_file=template_file,
        inject_datetime=bool(item.get("inject_datetime", True)),
        timezone_name=timezone_name,
        timezone_label=timezone_label(resolved_tz, timezone_name),
        tz=resolved_tz,
        datetime_format=str(
            item.get("datetime_format", DEFAULT_DATETIME_FORMAT)
            or DEFAULT_DATETIME_FORMAT,
        ),
        date_format=str(
            item.get("date_format", DEFAULT_DATE_FORMAT) or DEFAULT_DATE_FORMAT,
        ),
        time_format=str(
            item.get("time_format", DEFAULT_TIME_FORMAT) or DEFAULT_TIME_FORMAT,
        ),
        render_markdown=bool(item.get("render_markdown", True)),
        sanitize_html_input=bool(item.get("sanitize_html_input", True)),
        background_candidates=normalize_background_candidates(
            item.get("background_candidates"),
            allowed_protocols,
        ),
        background_switch_mode=switch_mode,
        custom_vars=normalize_custom_vars(item.get("custom_vars_json")),
        screenshot_options=normalize_screenshot_options(
            item.get("screenshot_options_json"),
        ),
        markdown_extensions=normalize_markdown_extensions(
            item.get("markdown_extensions"),
        ),
        allowed_tags=normalize_allowed_tags(item.get("allowed_tags")),
        allowed_attributes=normalize_allowed_attributes(
            item.get("allowed_attributes_json"),
        ),
        allowed_protocols=allowed_protocols,
    )


def resolve_template_path(raw: Any) -> Path | None:
    """Resolve a ``template_file`` value to a path inside the plugin directory.

    ``None`` means "not usable": blank, wrong type, or anything that escapes the
    plugin directory — absolute paths, other drives, ``..`` traversal, and
    symlinks that resolve outside.
    """
    if not isinstance(raw, str):
        return None
    relative = raw.strip().replace("\\", "/")
    if not relative:
        return None
    try:
        candidate = (PLUGIN_DIR / relative).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    try:
        candidate.relative_to(PLUGIN_DIR)
    except ValueError:
        return None
    return candidate


def read_template_file(raw: Any, profile_name: str) -> str:
    """Return the body of ``template_file``, or ``""`` when it is unusable."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    path = resolve_template_path(raw)
    if path is None:
        logger.warning(
            "[t2i_enhance] profile %r: template_file must stay inside the plugin "
            "directory, got %r; ignored.",
            profile_name,
            raw,
        )
        return ""
    if not path.is_file():
        logger.warning(
            "[t2i_enhance] profile %r: template_file not found: %s; ignored.",
            profile_name,
            path,
        )
        return ""
    try:
        # ``utf-8-sig`` tolerates a BOM written by some editors.
        return path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning(
            "[t2i_enhance] profile %r: cannot read template_file %s: %s; ignored.",
            profile_name,
            path,
            exc,
        )
        return ""


def template_file_fingerprint(raw_profiles: Any) -> str:
    """Fingerprint the size and mtime of every referenced template file.

    Editing a template file does not change the plugin config, so without this
    the normalized-profile cache would keep serving the previous HTML until the
    plugin was reloaded.
    """
    if not isinstance(raw_profiles, (list, tuple)):
        return ""
    entries: list[tuple[str, int, int]] = []
    for item in raw_profiles:
        if not isinstance(item, dict):
            continue
        path = resolve_template_path(item.get("template_file"))
        if path is None:
            continue
        try:
            stat = path.stat()
        except OSError:
            entries.append((str(path), -1, -1))
        else:
            entries.append((str(path), stat.st_mtime_ns, stat.st_size))
    return config_fingerprint(entries) if entries else ""


def normalize_template_profiles(raw_profiles: Any) -> tuple[TemplateProfile, ...]:
    """Validate and normalize every configured profile.

    Profiles that are unsafe or incomplete are skipped with a warning, so one
    bad entry can never break the whole plugin.
    """
    if not isinstance(raw_profiles, (list, tuple)):
        if raw_profiles is not None:
            logger.warning(
                "[t2i_enhance] template_profiles must be a list, got %s; ignoring it.",
                type(raw_profiles).__name__,
            )
        return ()

    profiles: list[TemplateProfile] = []
    seen_names: set[str] = set()
    for index, item in enumerate(raw_profiles):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "") or "").strip()
        template_file = str(item.get("template_file", "") or "").strip()
        inline_html = str(item.get("template_html", "") or "").strip()
        # The file wins over the inline copy. The schema always ships a non-empty
        # ``template_html`` default, so the other order would make ``template_file``
        # impossible to adopt without blanking the inline field by hand.
        file_html = read_template_file(template_file, name or f"#{index}").strip()
        if file_html:
            template_html = file_html
            # Record the file only when it was really the source, so the render log
            # does not claim a file that had silently fallen back to the inline copy.
            template_source = template_file
        else:
            template_html = inline_html
            template_source = ""
        if not name or not template_html:
            logger.warning(
                "[t2i_enhance] skip template profile #%s: a name plus either "
                "template_html or template_file is required.",
                index,
            )
            continue
        if name in seen_names:
            logger.warning(
                "[t2i_enhance] skip duplicate template profile name: %s",
                name,
            )
            continue
        try:
            validate_template_html(template_html)
        except UnsafeTemplateError as exc:
            logger.warning(
                "[t2i_enhance] blocked unsafe template profile %r: %s",
                name,
                exc,
            )
            continue
        seen_names.add(name)
        profiles.append(build_profile(name, item, template_html, template_source))
    return tuple(profiles)


# --------------------------------------------------------------------------- #
# Content rendering
# --------------------------------------------------------------------------- #


def clean_html(text: str, profile: TemplateProfile) -> str:
    """Run the profile's whitelist over already-produced HTML."""
    return bleach.clean(
        text,
        tags=set(profile.allowed_tags),
        attributes={
            tag: list(attrs) for tag, attrs in profile.allowed_attributes.items()
        },
        protocols=list(profile.allowed_protocols),
        strip=True,
    )


def render_content(plain_text: str, profile: TemplateProfile) -> str:
    """Turn the leading plain text into the HTML body injected into the template."""
    if profile.render_markdown:
        html = markdown.markdown(
            plain_text,
            extensions=list(profile.markdown_extensions),
            output_format="html5",
        )
        return clean_html(html, profile)
    if profile.sanitize_html_input:
        return clean_html(plain_text, profile)
    return plain_text


# --------------------------------------------------------------------------- #
# Result-chain helpers
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LeadingPlainText:
    """The leading ``Plain`` run of a result chain."""

    text: str
    count: int


def collect_leading_plain_text(result: Any) -> LeadingPlainText:
    """Join the leading contiguous ``Plain`` components of a result chain.

    This intentionally mirrors ``ResultDecorateStage`` in AstrBot core,
    including the ``"\\n\\n"`` separator, so the plugin sees exactly the text the
    core would have rendered and makes the same threshold decision.
    """
    parts: list[str] = []
    count = 0
    for component in getattr(result, "chain", None) or ():
        if not isinstance(component, Plain):
            break
        parts.append("\n\n" + (component.text or ""))
        count += 1
    return LeadingPlainText(text="".join(parts), count=count)


def resolve_render_text(
    context: Any,
    plugin_config: Any,
    event: AstrMessageEvent,
    result: Any,
) -> LeadingPlainText | None:
    """Decide whether this result should be rendered, and with which text.

    Mirrors the core gate: plugin switch, ``t2i`` switch / ``use_t2i_`` override,
    a non-empty leading ``Plain`` run, and the word threshold.
    """
    if not config_get(plugin_config, "plugin_enabled", True):
        logger.debug("[t2i_enhance] skip: plugin disabled.")
        return None

    try:
        astrbot_config = context.get_config(event.unified_msg_origin)
    except Exception:
        logger.warning(
            "[t2i_enhance] skip: failed to read the AstrBot config.",
            exc_info=True,
        )
        return None
    if astrbot_config is None:
        astrbot_config = {}

    use_t2i = getattr(result, "use_t2i_", None)
    t2i_enabled = bool(config_get(astrbot_config, "t2i", False))
    if not ((use_t2i is None and t2i_enabled) or use_t2i):
        logger.debug(
            "[t2i_enhance] skip: T2I not requested. use_t2i=%s, global_t2i=%s",
            use_t2i,
            t2i_enabled,
        )
        return None

    leading = collect_leading_plain_text(result)
    if not leading.text.strip():
        logger.debug("[t2i_enhance] skip: no leading Plain text in result chain.")
        return None

    threshold = normalize_t2i_threshold(
        config_get(astrbot_config, "t2i_word_threshold"),
    )
    if len(leading.text) <= threshold:
        logger.debug(
            "[t2i_enhance] skip: text length %s <= threshold %s.",
            len(leading.text),
            threshold,
        )
        return None

    return leading


# --------------------------------------------------------------------------- #
# Plugin
# --------------------------------------------------------------------------- #


@register(
    "t2i_enhance",
    "Codex",
    "T2I Enhance: self-managed HTML templates with backend-injected variables.",
    PLUGIN_VERSION,
)
class T2IEnhancePlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self._profile_cache_fingerprint = ""
        self._profile_cache: tuple[TemplateProfile, ...] = ()
        self._background_cursor: dict[str, int] = {}
        self._background_last: dict[str, str] = {}
        self._html_render_accepts_umo: bool | None = None
        self._warned_active_profile = ""

    async def initialize(self) -> None:
        self._invalidate_caches()

    async def terminate(self) -> None:
        self._invalidate_caches()

    def _invalidate_caches(self) -> None:
        self._profile_cache_fingerprint = ""
        self._profile_cache = ()
        self._background_cursor.clear()
        self._background_last.clear()
        self._warned_active_profile = ""

    # -- configuration ----------------------------------------------------- #

    def _profiles(self) -> tuple[TemplateProfile, ...]:
        """Return the normalized profiles, reusing the last result when unchanged.

        Normalizing a profile costs six regex scans over the whole template plus
        several JSON parses, and it used to happen on every message. The raw
        config is fingerprinted instead so repeated renders are free while a
        WebUI edit still takes effect immediately. Profiles that read their HTML
        from ``template_file`` also fold that file's size and mtime into the key,
        so editing the file is picked up on the next render too.
        """
        raw_profiles = config_get(self.config, "template_profiles", [])
        fingerprint = config_fingerprint(raw_profiles)
        file_fingerprint = template_file_fingerprint(raw_profiles)
        if file_fingerprint:
            fingerprint = f"{fingerprint}:{file_fingerprint}"
        if fingerprint and fingerprint == self._profile_cache_fingerprint:
            return self._profile_cache

        profiles = normalize_template_profiles(raw_profiles)
        if fingerprint:
            self._profile_cache_fingerprint = fingerprint
            self._profile_cache = profiles
        return profiles

    def _resolve_active_profile(self) -> TemplateProfile | None:
        profiles = [profile for profile in self._profiles() if profile.enabled]
        if not profiles:
            return None

        active_name = str(config_get(self.config, "active_profile", "") or "").strip()
        if active_name:
            for profile in profiles:
                if profile.name == active_name:
                    self._warned_active_profile = active_name
                    return profile
            # Warn once per distinct value so a wrong name does not flood the log.
            if active_name != self._warned_active_profile:
                self._warned_active_profile = active_name
                logger.warning(
                    "[t2i_enhance] active_profile %r matches no enabled profile; "
                    "falling back to %r.",
                    active_name,
                    profiles[0].name,
                )
        return profiles[0]

    # -- template data ----------------------------------------------------- #

    def _select_background(self, profile: TemplateProfile) -> str:
        candidates = profile.background_candidates
        if not candidates:
            return ""

        profile_name = profile.name
        mode = profile.background_switch_mode
        index: int | None = None

        if mode == "fixed":
            selected = candidates[0]
            index = 0
        elif mode == "sequential":
            index = self._background_cursor.get(profile_name, 0) % len(candidates)
            selected = candidates[index]
            self._background_cursor[profile_name] = (index + 1) % len(candidates)
        else:
            previous = self._background_last.get(profile_name)
            pool = [url for url in candidates if url != previous] or list(candidates)
            selected = random.choice(pool)
            self._background_last[profile_name] = selected

        logger.info(
            "[t2i_enhance] selected background: mode=%s, profile=%s, count=%s, "
            "index=%s, url=%s",
            mode,
            profile_name,
            len(candidates),
            index,
            selected,
        )
        return selected

    def build_template_data(
        self,
        plain_text: str,
        rendered_content: str,
        profile: TemplateProfile,
    ) -> dict[str, Any]:
        """Build the Jinja2 variables for one render."""
        custom_vars = dict(profile.custom_vars)
        data: dict[str, Any] = {
            # ``text`` keeps the official default templates usable: the enhanced
            # HTML body is written back to it. Use ``content`` for new templates.
            "text": rendered_content,
            "raw_text": plain_text,
            "content": rendered_content,
            "html": rendered_content,
            "template_name": profile.name,
            "bg_url": self._select_background(profile),
            "version": f"v{astrbot_version}" if astrbot_version else "",
        }

        if profile.inject_datetime:
            now = datetime.now(profile.tz)
            data.update(
                {
                    "datetime": format_time(
                        now,
                        profile.datetime_format,
                        DEFAULT_DATETIME_FORMAT,
                    ),
                    "date": format_time(now, profile.date_format, DEFAULT_DATE_FORMAT),
                    "time": format_time(now, profile.time_format, DEFAULT_TIME_FORMAT),
                    "timestamp": unix_timestamp(now),
                    "timezone": profile.timezone_label,
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                    "weekday": format_time(now, DEFAULT_WEEKDAY_FORMAT),
                },
            )

        # Custom variables were filtered against RESERVED_TEMPLATE_VARS while
        # normalizing, so they cannot shadow anything injected above.
        data.update(custom_vars)
        return data

    # -- rendering --------------------------------------------------------- #

    def _accepts_umo(self) -> bool:
        """Whether this AstrBot version forwards ``umo`` to the renderer.

        ``umo`` (>= 4.28) lets a session-bound ``t2i_endpoint`` apply, which the
        plugin's declared floor (4.26) does not support.
        """
        cached = self._html_render_accepts_umo
        if cached is None:
            cached = False
            render = getattr(self, "html_render", None)
            if callable(render):
                try:
                    cached = "umo" in inspect.signature(render).parameters
                except (TypeError, ValueError):
                    cached = False
            self._html_render_accepts_umo = cached
        return cached

    async def _render_template(
        self,
        profile: TemplateProfile,
        template_data: dict[str, Any],
        event: AstrMessageEvent,
    ) -> str:
        render = getattr(self, "html_render", None)
        if not callable(render):
            raise RuntimeError("this AstrBot version does not expose Star.html_render")

        kwargs: dict[str, Any] = {}
        if self._accepts_umo():
            kwargs["umo"] = event.unified_msg_origin

        return await render(
            profile.template_html,
            template_data,
            return_url=False,
            options=dict(profile.screenshot_options),
            **kwargs,
        )

    @staticmethod
    def _build_image_component(event: AstrMessageEvent, location: str) -> Image | None:
        """Wrap a render result as an image component, or ``None`` on failure.

        ``return_url=False`` normally yields a downloaded temp file, but a
        custom renderer may still hand back a URL; tracking a URL as a temporary
        local file would be wrong, so both shapes are handled.

        This runs *after* a successful render, so it must never raise: losing the
        finished image to an unrelated API difference would be the worst outcome.
        """
        try:
            if location.startswith(("http://", "https://")):
                return Image.fromURL(location)
            tracker = getattr(event, "track_temporary_local_file", None)
            if callable(tracker):
                try:
                    tracker(location)
                except Exception:
                    # Cleanup bookkeeping only; the image itself is still valid.
                    logger.warning(
                        "[t2i_enhance] could not register %s for temp-file cleanup.",
                        location,
                        exc_info=True,
                    )
            return Image.fromFileSystem(location)
        except Exception:
            logger.warning(
                "[t2i_enhance] could not build an image component for %s.",
                location,
                exc_info=True,
            )
            return None

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent) -> None:
        result = event.get_result()
        if result is None or not result.chain:
            return

        leading = resolve_render_text(self.context, self.config, event, result)
        if leading is None:
            return

        profile = self._resolve_active_profile()
        if profile is None:
            logger.debug("[t2i_enhance] no enabled plugin template profile found.")
            return

        # ``leading.text`` keeps the core-identical "\n\n" prefixes so the threshold
        # decision still lines up with ResultDecorateStage, but a template should
        # not receive the leading blank line.
        render_text = leading.text.lstrip("\r\n")
        try:
            rendered_content = render_content(render_text, profile)
            template_data = self.build_template_data(
                render_text,
                rendered_content,
                profile,
            )
            logger.info(
                "[t2i_enhance] rendering plugin template: %s (source=%s), chars=%s",
                profile.name,
                profile.template_file or "inline",
                len(render_text),
            )
            location = await self._render_template(profile, template_data, event)
            if not isinstance(location, str) or not location:
                raise RuntimeError("html_render returned no image")
        except Exception:
            if config_get(self.config, "fallback_to_core_t2i", False):
                logger.exception(
                    "[t2i_enhance] failed to render template %r; leaving T2I "
                    "enabled so AstrBot core can render this reply instead.",
                    profile.name,
                )
            else:
                # Default: keep the core from retrying with its own template, which
                # would double the latency and use a template the user did not pick.
                result.use_t2i_ = False
                logger.exception(
                    "[t2i_enhance] failed to render template %r; sending the plain "
                    "text instead and suppressing T2I for this reply. Set "
                    "fallback_to_core_t2i to let core render it instead.",
                    profile.name,
                )
            return

        suffix_chain = result.chain[leading.count :]
        component = self._build_image_component(event, location)
        if component is None:
            # Fall back to the text rather than leaving the core to render again.
            result.use_t2i_ = False
            return
        result.chain = [component, *suffix_chain]
        result.use_t2i_ = False
        logger.info(
            "[t2i_enhance] rendered image with plugin template: %s",
            profile.name,
        )
