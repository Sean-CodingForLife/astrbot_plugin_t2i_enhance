from __future__ import annotations

import json
import random
import re
from datetime import datetime, timezone, tzinfo
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from astrbot import __version__ as astrbot_version
import bleach
import markdown

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Image, Plain

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_SCREENSHOT_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
}
RESERVED_TEMPLATE_VARS = {
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
}
SAFE_VAR_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SAFE_HTML_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9:_-]*$")
SAFE_PROTOCOL_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")
MAX_CUSTOM_VAR_DEPTH = 5
ALLOWED_SCREENSHOT_KEYS = {
    "type",
    "quality",
    "omit_background",
    "full_page",
    "clip",
    "animations",
    "caret",
    "scale",
    "timeout",
}
DEFAULT_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "pre": ["class"],
    "span": ["class"],
    "div": ["class"],
    "th": ["align"],
    "td": ["align"],
}
DEFAULT_MARKDOWN_EXTENSIONS = [
    "extra",
    "sane_lists",
    "nl2br",
    "admonition",
    "toc",
]
DEFAULT_ALLOWED_PROTOCOLS = ["http", "https", "data"]
DEFAULT_ALLOWED_TAGS = [
    "a",
    "abbr",
    "blockquote",
    "br",
    "code",
    "del",
    "details",
    "div",
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
]
BACKGROUND_SWITCH_MODES = {"random", "sequential", "fixed"}
TEMPLATE_SECURITY_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "dunder_chain",
        re.compile(
            r"__\s*(class|globals|init|mro|base|bases|subclasses|reduce|getitem|builtins|import|self|func|code|reduce_ex)__",
        ),
    ),
    (
        "dangerous_builtins",
        re.compile(
            r"\b(import\s+(?!url)|os\.\w+|subprocess\.|\.popen\(|eval\(|exec\()",
        ),
    ),
    ("flask_context", re.compile(r"\{\{.*?\b(config|request|session|g)\b.*?\}\}")),
    ("script_tag", re.compile(r"<\s*script\b", re.IGNORECASE)),
    ("javascript_url", re.compile(r"javascript\s*:", re.IGNORECASE)),
]


def normalize_t2i_threshold(value: object) -> int:
    try:
        return max(int(value), 50)
    except (TypeError, ValueError):
        return 150


def validate_template_html(content: str) -> None:
    for label, pattern in TEMPLATE_SECURITY_PATTERNS:
        if pattern.search(content):
            logger.warning(
                "[t2i_enhance] blocked unsafe template content by rule: %s",
                label,
            )
            raise ValueError(f"unsafe template content ({label})")


def parse_json_config(raw: str, fallback: Any, label: str) -> Any:
    if not raw or not str(raw).strip():
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("[t2i_enhance] invalid JSON in %s, fallback applied.", label)
        return fallback


def normalize_allowed_attributes(config: dict) -> dict[str, list[str]]:
    raw = parse_json_config(
        config.get("allowed_attributes_json", ""),
        DEFAULT_ALLOWED_ATTRIBUTES,
        "allowed_attributes_json",
    )
    if not isinstance(raw, dict):
        return {}
    return {
        str(tag): [
            str(attr)
            for attr in attrs
            if attr and SAFE_HTML_NAME_RE.fullmatch(str(attr))
        ]
        for tag, attrs in raw.items()
        if isinstance(attrs, list) and attrs and SAFE_HTML_NAME_RE.fullmatch(str(tag))
    }


def normalize_allowed_tags(config: dict) -> set[str]:
    raw = config.get("allowed_tags", [])
    if not isinstance(raw, list):
        return set()
    return {
        str(tag)
        for tag in raw
        if str(tag).strip() and SAFE_HTML_NAME_RE.fullmatch(str(tag))
    }


def normalize_allowed_protocols(config: dict) -> list[str]:
    raw = config.get("allowed_protocols", [])
    if not isinstance(raw, list):
        return DEFAULT_ALLOWED_PROTOCOLS
    protocols = []
    for item in raw:
        protocol = str(item).strip().lower()
        if protocol and SAFE_PROTOCOL_RE.fullmatch(protocol):
            protocols.append(protocol)
    return protocols or DEFAULT_ALLOWED_PROTOCOLS


def normalize_markdown_extensions(config: dict) -> list[str]:
    raw = config.get("markdown_extensions", [])
    if not isinstance(raw, list):
        return []
    return [str(ext).strip() for ext in raw if str(ext).strip()]


def normalize_template_profiles(config: dict) -> list[dict[str, Any]]:
    profiles = config.get("template_profiles", [])
    if not isinstance(profiles, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in profiles:
        if not isinstance(item, dict):
            continue

        profile_name = str(item.get("name", "")).strip()
        template_html = str(item.get("template_html", "")).strip()
        if not profile_name or not template_html:
            continue

        try:
            validate_template_html(template_html)
        except ValueError:
            logger.warning(
                "[t2i_enhance] ignore invalid template profile: %s",
                profile_name or "<unnamed>",
            )
            continue

        normalized.append(
            {
                "name": profile_name,
                "enabled": bool(item.get("enabled", True)),
                "template_html": template_html,
                "inject_datetime": bool(item.get("inject_datetime", True)),
                "timezone": str(item.get("timezone", DEFAULT_TIMEZONE)).strip()
                or DEFAULT_TIMEZONE,
                "datetime_format": str(
                    item.get("datetime_format", "%Y-%m-%d %H:%M:%S"),
                ),
                "date_format": str(item.get("date_format", "%Y-%m-%d")),
                "time_format": str(item.get("time_format", "%H:%M:%S")),
                "render_markdown": bool(item.get("render_markdown", True)),
                "sanitize_html_input": bool(item.get("sanitize_html_input", True)),
                "background_candidates": item.get("background_candidates", []),
                "background_switch_mode": str(
                    item.get("background_switch_mode", "random"),
                ).strip().lower()
                or "random",
                "custom_vars_json": str(item.get("custom_vars_json", "{}")),
                "screenshot_options_json": str(
                    item.get("screenshot_options_json", "{}"),
                ),
                "markdown_extensions": item.get(
                    "markdown_extensions",
                    list(DEFAULT_MARKDOWN_EXTENSIONS),
                ),
                "allowed_protocols": item.get(
                    "allowed_protocols",
                    list(DEFAULT_ALLOWED_PROTOCOLS),
                ),
                "allowed_tags": item.get("allowed_tags", list(DEFAULT_ALLOWED_TAGS)),
                "allowed_attributes_json": str(
                    item.get(
                        "allowed_attributes_json",
                        json.dumps(DEFAULT_ALLOWED_ATTRIBUTES, ensure_ascii=False),
                    ),
                ),
            },
        )

    return normalized


def markdown_to_safe_html(text: str, config: dict) -> str:
    html = markdown.markdown(
        text,
        extensions=normalize_markdown_extensions(config),
        output_format="html5",
    )
    return bleach.clean(
        html,
        tags=normalize_allowed_tags(config),
        attributes=normalize_allowed_attributes(config),
        protocols=normalize_allowed_protocols(config),
        strip=True,
    )


def sanitize_html(text: str, config: dict) -> str:
    return bleach.clean(
        text,
        tags=normalize_allowed_tags(config),
        attributes=normalize_allowed_attributes(config),
        protocols=normalize_allowed_protocols(config),
        strip=True,
    )


def sanitize_custom_var_value(value: Any, depth: int = 0) -> Any:
    if depth > MAX_CUSTOM_VAR_DEPTH:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return [sanitize_custom_var_value(item, depth + 1) for item in value]
    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            key_name = str(key).strip()
            if SAFE_VAR_NAME_RE.fullmatch(key_name):
                normalized[key_name] = sanitize_custom_var_value(item, depth + 1)
        return normalized
    return str(value)


def parse_custom_vars(raw: str) -> dict[str, Any]:
    data = parse_json_config(raw, {}, "custom_vars_json")
    if not isinstance(data, dict):
        return {}

    normalized: dict[str, Any] = {}
    for key, value in data.items():
        key_name = str(key).strip()
        if not SAFE_VAR_NAME_RE.fullmatch(key_name):
            logger.warning("[t2i_enhance] ignore invalid custom var name: %s", key_name)
            continue
        if key_name in RESERVED_TEMPLATE_VARS:
            logger.warning("[t2i_enhance] ignore reserved custom var name: %s", key_name)
            continue
        normalized[key_name] = sanitize_custom_var_value(value)
    return normalized


def parse_screenshot_options(raw: str) -> dict[str, Any]:
    data = parse_json_config(raw, {}, "screenshot_options_json")
    if not isinstance(data, dict):
        data = {}
    options = dict(DEFAULT_SCREENSHOT_OPTIONS)
    for key, value in data.items():
        if key not in ALLOWED_SCREENSHOT_KEYS:
            logger.warning("[t2i_enhance] ignore unsupported screenshot option: %s", key)
            continue
        if key == "type" and value in {"png", "jpeg"}:
            options[key] = value
        elif key == "quality" and isinstance(value, int) and 0 <= value <= 100:
            options[key] = value
        elif key in {"omit_background", "full_page"} and isinstance(value, bool):
            options[key] = value
        elif key == "animations" and value in {"allow", "disabled"}:
            options[key] = value
        elif key == "caret" and value in {"hide", "initial"}:
            options[key] = value
        elif key == "scale" and value in {"css", "device"}:
            options[key] = value
        elif key == "timeout" and isinstance(value, (int, float)) and value > 0:
            options[key] = value
        elif key == "clip" and isinstance(value, dict):
            clip = {
                clip_key: value.get(clip_key)
                for clip_key in ("x", "y", "width", "height")
                if isinstance(value.get(clip_key), (int, float)) and value.get(clip_key) >= 0
            }
            if len(clip) == 4 and clip["width"] > 0 and clip["height"] > 0:
                options[key] = clip
    return options


def resolve_timezone(config: dict) -> tzinfo:
    timezone_name = str(config.get("timezone", DEFAULT_TIMEZONE)).strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        logger.warning(
            "[t2i_enhance] invalid timezone %s, fallback to UTC.",
            timezone_name,
        )
        return timezone.utc


def collect_leading_plain_text(result) -> tuple[str, int]:
    parts: list[str] = []
    count = 0
    for comp in result.chain:
        if not isinstance(comp, Plain):
            break
        if comp.text:
            parts.append("\n\n" + comp.text)
        count += 1
    return "".join(parts), count


def is_allowed_url(url: str, config: dict) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme:
        return False
    return parsed.scheme.lower() in set(normalize_allowed_protocols(config))


def config_get(config: Any, key: str, fallback: Any = None) -> Any:
    if hasattr(config, "get"):
        try:
            return config.get(key, fallback)
        except TypeError:
            try:
                value = config.get(key)
                return fallback if value is None else value
            except Exception:
                return fallback
        except Exception:
            return fallback
    try:
        return config[key]
    except Exception:
        return fallback


def should_render(context: Context, plugin_config: dict, event: AstrMessageEvent, result) -> bool:
    if not plugin_config.get("plugin_enabled", True):
        logger.debug("[t2i_enhance] skip: plugin disabled.")
        return False

    astrbot_config = context.get_config(event.unified_msg_origin) or {}
    use_t2i = getattr(result, "use_t2i_", None)
    t2i_enabled = bool(config_get(astrbot_config, "t2i", False))

    if not (((use_t2i is None) and t2i_enabled) or use_t2i):
        logger.debug(
            "[t2i_enhance] skip: T2I not requested. use_t2i=%s, global_t2i=%s",
            use_t2i,
            t2i_enabled,
        )
        return False

    plain_text, _ = collect_leading_plain_text(result)
    if not plain_text:
        logger.debug("[t2i_enhance] skip: no leading Plain text in result chain.")
        return False

    threshold = normalize_t2i_threshold(config_get(astrbot_config, "t2i_word_threshold"))
    if len(plain_text) <= threshold:
        logger.debug(
            "[t2i_enhance] skip: text length %s <= threshold %s.",
            len(plain_text),
            threshold,
        )
        return False

    return True


@register(
    "t2i_enhance",
    "Codex",
    "T2I Enhance: self-managed HTML templates with backend-injected variables.",
    "1.0.0",
)
class T2IEnhancePlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

    def _resolve_template_profile(self) -> dict[str, Any] | None:
        profiles = [profile for profile in normalize_template_profiles(self.config) if profile.get("enabled", True)]
        if not profiles:
            return None

        active_profile = str(self.config.get("active_profile", "")).strip()
        if active_profile:
            for profile in profiles:
                if profile["name"] == active_profile:
                    return profile

        return profiles[0]

    def _build_rendered_content(self, plain_text: str, profile: dict[str, Any]) -> str:
        if profile.get("render_markdown", True):
            return markdown_to_safe_html(plain_text, profile)

        if profile.get("sanitize_html_input", True):
            return sanitize_html(plain_text, profile)

        return plain_text

    def _select_background(self, profile: dict[str, Any]) -> str:
        candidates = profile.get("background_candidates", [])
        if not isinstance(candidates, list):
            return ""
        valid = []
        for item in candidates:
            url = str(item).strip()
            if not url:
                continue
            if not is_allowed_url(url, profile):
                logger.warning("[t2i_enhance] ignore background with disallowed protocol: %s", url)
                continue
            valid.append(url)
        if not valid:
            return ""

        mode = str(profile.get("background_switch_mode", "random")).strip().lower()
        if mode not in BACKGROUND_SWITCH_MODES:
            mode = "random"

        if mode == "fixed":
            return valid[0]
        if mode == "sequential":
            current = getattr(self, "_background_sequence_state", {})
            profile_name = profile["name"]
            index = int(current.get(profile_name, 0)) if isinstance(current, dict) else 0
            selected = valid[index % len(valid)]
            if not isinstance(current, dict):
                current = {}
            current[profile_name] = (index + 1) % len(valid)
            self._background_sequence_state = current
            return selected
        return random.choice(valid)

    def _build_template_data(
        self,
        plain_text: str,
        rendered_content: str,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        now = datetime.now(resolve_timezone(profile))
        custom_vars = parse_custom_vars(profile.get("custom_vars_json", "{}"))

        data: dict[str, Any] = {
            # Keep official default templates usable by writing the enhanced body back to text.
            "text": rendered_content,
            "raw_text": plain_text,
            "content": rendered_content,
            "html": rendered_content,
            "template_name": profile["name"],
            "bg_url": self._select_background(profile),
            "version": f"v{astrbot_version}",
        }

        if profile.get("inject_datetime", True):
            data.update(
                {
                    "datetime": now.strftime(
                        str(profile.get("datetime_format", "%Y-%m-%d %H:%M:%S")),
                    ),
                    "date": now.strftime(str(profile.get("date_format", "%Y-%m-%d"))),
                    "time": now.strftime(str(profile.get("time_format", "%H:%M:%S"))),
                    "timestamp": int(now.timestamp()),
                    "timezone": str(now.tzinfo),
                    "year": now.year,
                    "month": now.month,
                    "day": now.day,
                    "hour": now.hour,
                    "minute": now.minute,
                    "second": now.second,
                    "weekday": now.strftime("%A"),
                },
            )

        for key, value in custom_vars.items():
            data[key] = value

        return data

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        result = event.get_result()
        if result is None or not result.chain:
            return

        if not should_render(self.context, self.config, event, result):
            return

        plain_text, leading_plain_count = collect_leading_plain_text(result)
        if not plain_text or leading_plain_count == 0:
            return

        profile = self._resolve_template_profile()
        if profile is None:
            logger.debug(
                "[t2i_enhance] no enabled plugin template profile found.",
            )
            return

        try:
            template_html = profile["template_html"]
            rendered_content = self._build_rendered_content(plain_text, profile)
            template_data = self._build_template_data(
                plain_text,
                rendered_content,
                profile,
            )
            rendered_image = await self.html_render(
                template_html,
                template_data,
                return_url=False,
                options=parse_screenshot_options(profile.get("screenshot_options_json", "{}")),
            )
        except Exception:
            result.use_t2i_ = False
            logger.exception("[t2i_enhance] failed to render active T2I template.")
            return

        suffix_chain = result.chain[leading_plain_count:]
        event.track_temporary_local_file(rendered_image)
        result.chain = [Image.fromFileSystem(rendered_image), *suffix_chain]
        result.use_t2i_ = False
        logger.debug(
            "[t2i_enhance] rendered image with plugin template: %s",
            profile["name"],
        )
