from __future__ import annotations

import json
import re

import bleach
import markdown

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain


def normalize_allowed_attributes(config: dict) -> dict[str, list[str]]:
    raw = json.loads(config["allowed_attributes_json"])
    return {
        tag: attrs
        for tag, attrs in raw.items()
        if attrs
    }


def markdown_to_safe_html(text: str, config) -> str:
    html = markdown.markdown(
        text,
        extensions=config["markdown_extensions"],
        output_format="html5",
    )
    return bleach.clean(
        html,
        tags=set(config["allowed_tags"]),
        attributes=normalize_allowed_attributes(config),
        protocols=config["allowed_protocols"],
        strip=True,
    )


def looks_like_html(text: str, config) -> bool:
    return bool(re.search(config["html_tag_pattern"], text, re.IGNORECASE))


def normalize_t2i_threshold(value: object) -> int:
    return max(int(value), 50)


def should_convert_for_t2i(context: Context, plugin_config, event: AstrMessageEvent, result) -> bool:
    astrbot_config = context.get_config(event.unified_msg_origin)

    if not plugin_config["plugin_enabled"]:
        return False

    if not (((result.use_t2i_ is None) and astrbot_config["t2i"]) or result.use_t2i_):
        return False

    if astrbot_config["t2i_active_template"] in plugin_config["excluded_templates"]:
        return False

    parts: list[str] = []
    for comp in result.chain:
        if isinstance(comp, Plain):
            parts.append("\n\n" + comp.text)
        else:
            break

    plain_str = "".join(parts)
    if not plain_str:
        return False

    return len(plain_str) > normalize_t2i_threshold(astrbot_config["t2i_word_threshold"])


@register(
    "t2i_enhance",
    "Codex",
    "T2I Enhance: render Markdown structure before AstrBot text-to-image.",
    "1.1.0",
)
class T2IEnhancePlugin(Star):
    def __init__(self, context: Context, config):
        super().__init__(context)
        self.config = config

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        result = event.get_result()
        if result is None or not result.chain:
            return

        if not should_convert_for_t2i(self.context, self.config, event, result):
            return

        changed = False
        for comp in result.chain:
            if not isinstance(comp, Plain):
                break
            if not comp.text:
                continue
            if self.config["skip_existing_html"] and looks_like_html(comp.text, self.config):
                continue
            comp.text = markdown_to_safe_html(comp.text, self.config)
            changed = True

        if changed:
            logger.debug("[t2i_enhance] converted Plain markdown to safe HTML.")
