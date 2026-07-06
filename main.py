from __future__ import annotations

import json
import random
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import bleach
import markdown

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Image, Plain

SEQUENCE_STATE_KEY = "template_sequence_index"
DEFAULT_TIMEZONE = "Asia/Shanghai"
DEFAULT_SCREENSHOT_OPTIONS = {
    "type": "png",
    "full_page": True,
    "animations": "disabled",
}


def normalize_t2i_threshold(value: object) -> int:
    try:
        return max(int(value), 50)
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
        str(tag): [str(attr) for attr in attrs if attr]
        for tag, attrs in raw.items()
        if isinstance(attrs, list) and attrs
    }


def markdown_to_safe_html(text: str, config: dict) -> str:
    html = markdown.markdown(
        text,
        extensions=config.get("markdown_extensions", []),
        output_format="html5",
    )
    return bleach.clean(
        html,
        tags=set(config.get("allowed_tags", [])),
        attributes=normalize_allowed_attributes(config),
        protocols=config.get("allowed_protocols", []),
        strip=True,
    )


def sanitize_html(text: str, config: dict) -> str:
    return bleach.clean(
        text,
        tags=set(config.get("allowed_tags", [])),
        attributes=normalize_allowed_attributes(config),
        protocols=config.get("allowed_protocols", []),
        strip=True,
    )


def parse_custom_vars(raw: str) -> dict[str, Any]:
    data = parse_json_config(raw, {}, "custom_vars_json")
    return data if isinstance(data, dict) else {}


def parse_screenshot_options(raw: str) -> dict[str, Any]:
    data = parse_json_config(raw, {}, "screenshot_options_json")
    if not isinstance(data, dict):
        data = {}
    options = dict(DEFAULT_SCREENSHOT_OPTIONS)
    options.update(data)
    return options


def normalize_template_candidates(config: dict) -> list[dict[str, Any]]:
    candidates = config.get("template_candidates", [])
    normalized: list[dict[str, Any]] = []
    if not isinstance(candidates, list):
        return normalized

    for item in candidates:
        if not isinstance(item, dict):
            continue
        enabled = item.get("enabled", True)
        template_html = str(item.get("template_html", "")).strip()
        if not enabled or not template_html:
            continue
        backgrounds = item.get("background_candidates", [])
        normalized.append(
            {
                "name": str(item.get("name", "")).strip() or "未命名模板",
                "template_html": template_html,
                "render_markdown": bool(item.get("render_markdown", True)),
                "sanitize_html_input": bool(item.get("sanitize_html_input", True)),
                "title": str(item.get("title", "")).strip(),
                "subtitle": str(item.get("subtitle", "")).strip(),
                "footer_left": str(item.get("footer_left", "")).strip(),
                "footer_right": str(item.get("footer_right", "")).strip(),
                "background_candidates": [
                    str(url).strip() for url in backgrounds if str(url).strip()
                ]
                if isinstance(backgrounds, list)
                else [],
            },
        )
    return normalized


def select_background(config: dict, template_item: dict[str, Any]) -> str:
    candidates = template_item.get("background_candidates", [])
    if isinstance(candidates, list) and candidates:
        return random.choice(candidates)

    global_candidates = config.get("global_background_candidates", [])
    if isinstance(global_candidates, list) and global_candidates:
        valid = [str(url).strip() for url in global_candidates if str(url).strip()]
        if valid:
            return random.choice(valid)
    return ""


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


def should_render(context: Context, plugin_config: dict, event: AstrMessageEvent, result) -> bool:
    if not plugin_config.get("plugin_enabled", True):
        return False

    astrbot_config = context.get_config(event.unified_msg_origin)

    if not (((result.use_t2i_ is None) and astrbot_config["t2i"]) or result.use_t2i_):
        return False

    if plugin_config.get("respect_official_excluded_templates", True):
        active_template = astrbot_config.get("t2i_active_template")
        if active_template in plugin_config.get("excluded_templates", []):
            return False

    plain_text, _ = collect_leading_plain_text(result)
    if not plain_text:
        return False

    threshold = normalize_t2i_threshold(astrbot_config.get("t2i_word_threshold"))
    return len(plain_text) > threshold


@register(
    "t2i_enhance",
    "Codex",
    "T2I Enhance: self-render HTML templates with backend-injected variables for AstrBot text-to-image.",
    "2.0.0",
)
class T2IEnhancePlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

    async def _select_template(self, templates: list[dict[str, Any]]) -> dict[str, Any]:
        mode = str(self.config.get("template_switch_mode", "fixed")).strip().lower()
        if not templates:
            raise ValueError("No template candidates available")

        if mode == "random":
            return random.choice(templates)

        if mode == "sequential":
            current = await self.get_kv_data(SEQUENCE_STATE_KEY, 0)
            try:
                index = int(current or 0)
            except (TypeError, ValueError):
                index = 0
            selected = templates[index % len(templates)]
            await self.put_kv_data(SEQUENCE_STATE_KEY, (index + 1) % len(templates))
            return selected

        return templates[0]

    def _build_rendered_content(self, plain_text: str, template_item: dict[str, Any]) -> str:
        render_markdown = template_item.get("render_markdown", True)
        sanitize_html_input = template_item.get("sanitize_html_input", True)

        if render_markdown:
            return markdown_to_safe_html(plain_text, self.config)

        if sanitize_html_input:
            return sanitize_html(plain_text, self.config)

        return plain_text

    def _build_template_data(
        self,
        plain_text: str,
        template_item: dict[str, Any],
        rendered_content: str,
    ) -> dict[str, Any]:
        now = datetime.now(resolve_timezone(self.config))
        custom_vars = parse_custom_vars(self.config.get("custom_vars_json", "{}"))
        background_url = select_background(self.config, template_item)

        data: dict[str, Any] = {
            "text": plain_text,
            "content": rendered_content,
            "html": rendered_content,
            "template_name": template_item.get("name", ""),
            "bg_url": background_url,
        }

        if self.config.get("inject_datetime", True):
            datetime_format = str(
                self.config.get("datetime_format", "%Y-%m-%d %H:%M:%S"),
            )
            date_format = str(self.config.get("date_format", "%Y-%m-%d"))
            time_format = str(self.config.get("time_format", "%H:%M:%S"))
            data.update(
                {
                    "datetime": now.strftime(datetime_format),
                    "date": now.strftime(date_format),
                    "time": now.strftime(time_format),
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

        if template_item.get("title"):
            data["title"] = template_item["title"]
        if template_item.get("subtitle"):
            data["subtitle"] = template_item["subtitle"]
        if template_item.get("footer_left"):
            data["footer_left"] = template_item["footer_left"]
        if template_item.get("footer_right"):
            data["footer_right"] = template_item["footer_right"]

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

        templates = normalize_template_candidates(self.config)
        if not templates:
            logger.warning("[t2i_enhance] no valid template candidates configured.")
            return

        plain_text, leading_plain_count = collect_leading_plain_text(result)
        if not plain_text or leading_plain_count == 0:
            return

        try:
            template_item = await self._select_template(templates)
            rendered_content = self._build_rendered_content(plain_text, template_item)
            template_data = self._build_template_data(
                plain_text=plain_text,
                template_item=template_item,
                rendered_content=rendered_content,
            )
            rendered_image = await self.html_render(
                template_item["template_html"],
                template_data,
                return_url=False,
                options=parse_screenshot_options(
                    self.config.get("screenshot_options_json", "{}"),
                ),
            )
        except Exception:
            logger.exception("[t2i_enhance] failed to render custom HTML template.")
            return

        suffix_chain = result.chain[leading_plain_count:]
        event.track_temporary_local_file(rendered_image)
        image_component = Image.fromFileSystem(rendered_image)
        result.chain = [image_component, *suffix_chain]
        result.use_t2i_ = False
        logger.debug(
            "[t2i_enhance] rendered image with template: %s",
            template_item.get("name", ""),
        )
