from __future__ import annotations

import re

import bleach
import markdown

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Plain


ALLOWED_TAGS = {
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
}

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title"],
    "code": ["class"],
    "pre": ["class"],
    "span": ["class"],
    "div": ["class"],
    "th": ["align"],
    "td": ["align"],
}

MARKDOWN_EXTENSIONS = [
    "extra",
    "sane_lists",
    "nl2br",
    "admonition",
    "toc",
]

HTML_TAG_RE = re.compile(r"<[a-z][^>]*>", re.IGNORECASE)
OFFICIAL_MARKDOWN_TEMPLATES = {"base", "astrbot_vitepress", "astrbot_powershell"}


def markdown_to_safe_html(text: str) -> str:
    html = markdown.markdown(
        text,
        extensions=MARKDOWN_EXTENSIONS,
        output_format="html5",
    )
    return bleach.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=["http", "https", "data"],
        strip=True,
    )


def looks_like_html(text: str) -> bool:
    return bool(HTML_TAG_RE.search(text))


def normalize_t2i_threshold(value: object) -> int:
    return max(int(value), 50)


def should_convert_for_t2i(context: Context, event: AstrMessageEvent, result) -> bool:
    config = context.get_config(event.unified_msg_origin)

    if not (((result.use_t2i_ is None) and config["t2i"]) or result.use_t2i_):
        return False

    if config.get("t2i_active_template", "base") in OFFICIAL_MARKDOWN_TEMPLATES:
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

    return len(plain_str) > normalize_t2i_threshold(config["t2i_word_threshold"])


@register(
    "t2i_enhance",
    "Codex",
    "T2I Enhance: render Markdown structure before AstrBot text-to-image.",
    "1.0.1",
)
class T2IEnhancePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        result = event.get_result()
        if result is None or not result.chain:
            return

        if not should_convert_for_t2i(self.context, event, result):
            return

        changed = False
        for comp in result.chain:
            if not isinstance(comp, Plain):
                break
            if not comp.text or looks_like_html(comp.text):
                continue
            comp.text = markdown_to_safe_html(comp.text)
            changed = True

        if changed:
            logger.debug("[t2i_enhance] converted Plain markdown to safe HTML.")
