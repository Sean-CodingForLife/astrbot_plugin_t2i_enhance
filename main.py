from __future__ import annotations

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
    "tables",
    "fenced_code",
    "admonition",
    "attr_list",
    "def_list",
    "footnotes",
    "toc",
]


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
    return any(
        token in text.lower()
        for token in ("<p", "<h1", "<h2", "<ul", "<ol", "<pre", "<blockquote", "<table")
    )


@register(
    "t2i_enhance",
    "Codex",
    "T2I Enhance: render Markdown structure before AstrBot text-to-image.",
    "1.0.0",
)
class T2IEnhancePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        result = event.get_result()
        if result is None or not result.chain:
            return

        should_t2i = getattr(result, "use_t2i_", None)
        if should_t2i is False:
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
