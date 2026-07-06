from __future__ import annotations

import json
import random
import re
from datetime import datetime
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
from astrbot.core.utils.t2i.template_manager import TemplateManager

DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_SCREENSHOT_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
}
RESERVED_TEMPLATE_VARS = {
    "text",
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


def normalize_t2i_threshold(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 150


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
        {
            "a": ["href", "title"],
            "img": ["src", "alt", "title"],
            "code": ["class"],
            "pre": ["class"],
            "span": ["class"],
            "div": ["class"],
            "th": ["align"],
            "td": ["align"],
        },
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
        return ["http", "https"]
    protocols = []
    for item in raw:
        protocol = str(item).strip().lower()
        if protocol and SAFE_PROTOCOL_RE.fullmatch(protocol):
            protocols.append(protocol)
    return protocols or ["http", "https"]


def normalize_markdown_extensions(config: dict) -> list[str]:
    raw = config.get("markdown_extensions", [])
    if not isinstance(raw, list):
        return []
    return [str(ext).strip() for ext in raw if str(ext).strip()]


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


def resolve_timezone(config: dict) -> ZoneInfo:
    timezone_name = str(config.get("timezone", DEFAULT_TIMEZONE)).strip() or DEFAULT_TIMEZONE
    try:
        return ZoneInfo(timezone_name)
    except Exception:
        logger.warning(
            "[t2i_enhance] invalid timezone %s, fallback to %s.",
            timezone_name,
            DEFAULT_TIMEZONE,
        )
        return ZoneInfo(DEFAULT_TIMEZONE)


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


def should_render(context: Context, plugin_config: dict, event: AstrMessageEvent, result) -> bool:
    if not plugin_config.get("plugin_enabled", True):
        return False

    astrbot_config = context.get_config(event.unified_msg_origin)

    if not (((result.use_t2i_ is None) and astrbot_config["t2i"]) or result.use_t2i_):
        return False

    plain_text, _ = collect_leading_plain_text(result)
    if not plain_text:
        return False

    threshold = normalize_t2i_threshold(astrbot_config.get("t2i_word_threshold"))
    return len(plain_text) > threshold


@register(
    "t2i_enhance",
    "Codex",
    "T2I Enhance: take over AstrBot active T2I template rendering with backend-injected variables.",
    "2.1.0",
)
class T2IEnhancePlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.template_manager = TemplateManager()

    def _resolve_active_template_name(self, event: AstrMessageEvent) -> str:
        astrbot_config = self.context.get_config(event.unified_msg_origin)
        return str(astrbot_config.get("t2i_active_template", "base")).strip() or "base"

    def _resolve_template_html(self, event: AstrMessageEvent) -> str:
        return self.template_manager.get_template(self._resolve_active_template_name(event))

    def _build_rendered_content(self, plain_text: str) -> str:
        if self.config.get("render_markdown", True):
            return markdown_to_safe_html(plain_text, self.config)

        if self.config.get("sanitize_html_input", True):
            return sanitize_html(plain_text, self.config)

        return plain_text

    def _select_background(self) -> str:
        candidates = self.config.get("background_candidates", [])
        if not isinstance(candidates, list):
            return ""
        valid = []
        for item in candidates:
            url = str(item).strip()
            if not url:
                continue
            if not is_allowed_url(url, self.config):
                logger.warning("[t2i_enhance] ignore background with disallowed protocol: %s", url)
                continue
            valid.append(url)
        return random.choice(valid) if valid else ""

    def _build_template_data(
        self,
        event: AstrMessageEvent,
        plain_text: str,
        rendered_content: str,
    ) -> dict[str, Any]:
        now = datetime.now(resolve_timezone(self.config))
        custom_vars = parse_custom_vars(self.config.get("custom_vars_json", "{}"))

        data: dict[str, Any] = {
            "text": plain_text,
            "content": rendered_content,
            "html": rendered_content,
            "template_name": self._resolve_active_template_name(event),
            "bg_url": self._select_background(),
            "version": f"v{astrbot_version}",
        }

        if self.config.get("inject_datetime", True):
            data.update(
                {
                    "datetime": now.strftime(
                        str(self.config.get("datetime_format", "%Y-%m-%d %H:%M:%S")),
                    ),
                    "date": now.strftime(str(self.config.get("date_format", "%Y-%m-%d"))),
                    "time": now.strftime(str(self.config.get("time_format", "%H:%M:%S"))),
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

        try:
            template_html = self._resolve_template_html(event)
            rendered_content = self._build_rendered_content(plain_text)
            template_data = self._build_template_data(event, plain_text, rendered_content)
            rendered_image = await self.html_render(
                template_html,
                template_data,
                return_url=False,
                options=parse_screenshot_options(
                    self.config.get("screenshot_options_json", "{}"),
                ),
            )
        except Exception:
            logger.exception("[t2i_enhance] failed to render active T2I template.")
            return

        suffix_chain = result.chain[leading_plain_count:]
        event.track_temporary_local_file(rendered_image)
        result.chain = [Image.fromFileSystem(rendered_image), *suffix_chain]
        result.use_t2i_ = False
        logger.debug(
            "[t2i_enhance] rendered image with active template: %s",
            self._resolve_active_template_name(event),
        )
