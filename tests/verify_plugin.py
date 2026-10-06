"""End-to-end harness for T2IEnhancePlugin without AstrBot installed.

Stubs the `astrbot`, `bleach` and `markdown` modules, imports the real main.py,
and drives the real `on_decorating_result` hook: gate decisions, result-chain
replacement, template_file loading and the failure paths.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
import sys
import types
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

failures = 0
CALLS: list[dict[str, Any]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    global failures
    if ok:
        print(f"PASS  {label}")
    else:
        failures += 1
        print(f"FAIL  {label}  {detail}")


# --------------------------------------------------------------------------- #
# Stubs
# --------------------------------------------------------------------------- #


class RecordingLogger:
    def __init__(self) -> None:
        self.records: list[tuple[str, str]] = []

    def _add(self, level: str, msg: Any, *args: Any) -> None:
        try:
            text = msg % args if args else str(msg)
        except Exception:
            text = str(msg)
        self.records.append((level, text))

    def warning(self, m: Any, *a: Any, **k: Any) -> None:
        self._add("warning", m, *a)

    def info(self, m: Any, *a: Any, **k: Any) -> None:
        self._add("info", m, *a)

    def debug(self, m: Any, *a: Any, **k: Any) -> None:
        self._add("debug", m, *a)

    def error(self, m: Any, *a: Any, **k: Any) -> None:
        self._add("error", m, *a)

    def exception(self, m: Any, *a: Any, **k: Any) -> None:
        self._add("exception", m, *a)

    def warned(self, needle: str) -> bool:
        return any(lvl in ("warning", "exception") for lvl, t in self.records if needle in t)

    def clear(self) -> None:
        self.records.clear()


LOGGER = RecordingLogger()


def _tag_filter(text: str, tags: Any, strip: bool = True) -> str:
    """Crude stand-in for bleach.clean: drop tags that are not whitelisted."""
    allowed = set(tags) if tags is not None else None

    def repl(m: re.Match[str]) -> str:
        name = m.group(2).lower()
        if allowed is None or name in allowed:
            return m.group(0)
        return "" if strip else m.group(0)

    return re.sub(r"<(/?)([A-Za-z][A-Za-z0-9:_-]*)([^<>]*)>", repl, text)


def _fake_markdown(text: str, extensions: Any = None, output_format: Any = None) -> str:
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    out = []
    for b in blocks:
        b = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", b)
        b = b.replace("\n", "<br />")
        out.append(f"<p>{b}</p>")
    return "\n".join(out)


def _install_stubs() -> None:
    bleach = types.ModuleType("bleach")
    bleach.clean = lambda text, tags=None, attributes=None, protocols=None, strip=True: _tag_filter(text, tags, strip)  # type: ignore[attr-defined]
    sys.modules["bleach"] = bleach

    markdown = types.ModuleType("markdown")
    markdown.markdown = _fake_markdown  # type: ignore[attr-defined]
    sys.modules["markdown"] = markdown

    astrbot = types.ModuleType("astrbot")
    astrbot.__version__ = "4.26.0"  # type: ignore[attr-defined]
    sys.modules["astrbot"] = astrbot

    api = types.ModuleType("astrbot.api")
    api.logger = LOGGER  # type: ignore[attr-defined]
    sys.modules["astrbot.api"] = api
    astrbot.api = api  # type: ignore[attr-defined]

    class Plain:
        def __init__(self, text: str = "") -> None:
            self.text = text

        def __repr__(self) -> str:
            return f"Plain({self.text!r})"

    class Image:
        def __init__(self, path: str | None = None, url: str | None = None) -> None:
            self.path = path
            self.url = url

        @classmethod
        def fromFileSystem(cls, path: str) -> "Image":
            if Image._fail_fs:
                raise RuntimeError("fromFileSystem exploded")
            return cls(path=path)

        @classmethod
        def fromURL(cls, url: str) -> "Image":
            return cls(url=url)

        def __repr__(self) -> str:
            return f"Image(path={self.path!r}, url={self.url!r})"

    Image._fail_fs = False  # type: ignore[attr-defined]

    class AstrMessageEvent:
        def __init__(self, umo: str = "aiocqhttp:GroupMessage:100", result: Any = None) -> None:
            self.unified_msg_origin = umo
            self._result = result
            self.tracked: list[str] = []
            self.track_raises = False

        def get_result(self) -> Any:
            return self._result

        def track_temporary_local_file(self, path: str) -> None:
            if self.track_raises:
                raise RuntimeError("tracking exploded")
            self.tracked.append(path)

    class _Filter:
        def on_decorating_result(self, *a: Any, **k: Any) -> Any:
            def deco(fn: Any) -> Any:
                return fn

            return deco

    event_mod = types.ModuleType("astrbot.api.event")
    event_mod.AstrMessageEvent = AstrMessageEvent  # type: ignore[attr-defined]
    event_mod.filter = _Filter()  # type: ignore[attr-defined]
    sys.modules["astrbot.api.event"] = event_mod
    api.event = event_mod  # type: ignore[attr-defined]

    class Context:
        def __init__(self, config: dict[str, Any] | None = None) -> None:
            self._config = config if config is not None else {}
            self.raises = False

        def get_config(self, umo: Any = None) -> dict[str, Any]:
            if self.raises:
                raise RuntimeError("no config")
            return self._config

    class Star:
        def __init__(self, context: Any, config: dict[str, Any] | None = None) -> None:
            self.context = context
            self.config = config or {}

    def register(*a: Any, **k: Any) -> Any:
        def deco(cls: Any) -> Any:
            cls._register_args = a
            return cls

        return deco

    star_mod = types.ModuleType("astrbot.api.star")
    star_mod.Context = Context  # type: ignore[attr-defined]
    star_mod.Star = Star  # type: ignore[attr-defined]
    star_mod.register = register  # type: ignore[attr-defined]
    sys.modules["astrbot.api.star"] = star_mod
    api.star = star_mod  # type: ignore[attr-defined]

    core = types.ModuleType("astrbot.core")
    sys.modules["astrbot.core"] = core
    comp = types.ModuleType("astrbot.core.message.components")
    comp.Image = Image  # type: ignore[attr-defined]
    comp.Plain = Plain  # type: ignore[attr-defined]
    sys.modules["astrbot.core.message.components"] = comp
    core.message = types.ModuleType("astrbot.core.message")  # type: ignore[attr-defined]
    core.message.components = comp  # type: ignore[attr-defined]


_install_stubs()
import main  # noqa: E402  (must come after the stubs)

PLAIN = sys.modules["astrbot.core.message.components"].Plain
IMAGE = sys.modules["astrbot.core.message.components"].Image
EVENT = sys.modules["astrbot.api.event"].AstrMessageEvent
CONTEXT = sys.modules["astrbot.api.star"].Context

LONG = "这是一段足够长的正文，用来跨过阈值。" * 12
SHORT = "短"

INLINE_TEMPLATE = "<!doctype html><html><body><article>{{ content | safe }}</article></body></html>"


class Result:
    def __init__(self, chain: list[Any], use_t2i_: Any = None) -> None:
        self.chain = chain
        self.use_t2i_ = use_t2i_


def base_profile(**over: Any) -> dict[str, Any]:
    profile = {
        "enabled": True,
        "name": "default",
        "template_html": INLINE_TEMPLATE,
        "render_markdown": True,
        "sanitize_html_input": True,
    }
    profile.update(over)
    return profile


def plugin_config(**over: Any) -> dict[str, Any]:
    cfg: dict[str, Any] = {"plugin_enabled": True, "active_profile": "default"}
    cfg.update(over)
    if "template_profiles" not in cfg:
        cfg["template_profiles"] = [base_profile()]
    return cfg


def make_plugin(
    plugin_cfg: dict[str, Any],
    astrbot_cfg: dict[str, Any] | None = None,
    render: Any = None,
    context_factory: Any = None,
) -> Any:
    ctx = (context_factory or CONTEXT)(astrbot_cfg if astrbot_cfg is not None else {"t2i": True, "t2i_word_threshold": 10})
    plugin = main.T2IEnhancePlugin(ctx, plugin_cfg)
    if render is not None:
        plugin.html_render = render
    return plugin


async def ok_render(template: str, data: Any, return_url: bool = False, options: Any = None, **kw: Any) -> str:
    CALLS.append({"template": template, "data": data, "options": options, "kwargs": kw})
    return "C:/tmp/rendered.png"


async def ok_render_with_umo(
    template: str, data: Any, return_url: bool = False, options: Any = None, umo: Any = None
) -> str:
    CALLS.append({"template": template, "data": data, "options": options, "kwargs": {"umo": umo}})
    return "C:/tmp/rendered.png"


async def empty_render(template: str, data: Any, return_url: bool = False, options: Any = None, **kw: Any) -> str:
    CALLS.append({"template": template, "data": data, "options": options, "kwargs": kw})
    return ""


async def boom_render(template: str, data: Any, return_url: bool = False, options: Any = None, **kw: Any) -> str:
    raise RuntimeError("renderer exploded")


def run(coro: Any) -> Any:
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #

print("=== gate: when the plugin must NOT take over ===")

CALLS.clear()
p = make_plugin(plugin_config(plugin_enabled=False), render=ok_render)
r = Result([PLAIN(LONG)])
run(p.on_decorating_result(EVENT(result=r)))
check("plugin_enabled=false leaves the chain untouched and does not render",
      CALLS == [] and len(r.chain) == 1 and isinstance(r.chain[0], PLAIN))

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": False, "t2i_word_threshold": 10}, render=ok_render)
r = Result([PLAIN(LONG)])
run(p.on_decorating_result(EVENT(result=r)))
check("global t2i=false leaves the chain untouched", CALLS == [] and isinstance(r.chain[0], PLAIN))

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
r = Result([PLAIN(SHORT)])
run(p.on_decorating_result(EVENT(result=r)))
check("text at or below the threshold is not rendered", CALLS == [] and isinstance(r.chain[0], PLAIN))

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
r = Result([PLAIN(LONG)], use_t2i_=False)
run(p.on_decorating_result(EVENT(result=r)))
check("result.use_t2i_=False overrides a globally enabled t2i", CALLS == [] and isinstance(r.chain[0], PLAIN))

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": False, "t2i_word_threshold": 10}, render=ok_render)
r = Result([PLAIN(LONG)], use_t2i_=True)
run(p.on_decorating_result(EVENT(result=r)))
check("result.use_t2i_=True renders even when global t2i=false", len(CALLS) == 1)

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
r = Result([PLAIN("前缀"), IMAGE(path="keep.png")])
run(p.on_decorating_result(EVENT(result=r)))
check("a chain that does not start with Plain is skipped", CALLS == [] and isinstance(r.chain[0], PLAIN))

print("\n=== gate: takeover and result-chain replacement ===")

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
r = Result([PLAIN(LONG), PLAIN(LONG), IMAGE(path="tail.png")])
run(p.on_decorating_result(EVENT(result=r)))
check("renders once and replaces the leading Plain run",
      len(CALLS) == 1 and isinstance(r.chain[0], IMAGE) and isinstance(r.chain[1], PLAIN) is False)
check("the trailing non-Plain component is preserved",
      len(r.chain) == 2 and getattr(r.chain[1], "path", None) == "tail.png", repr(r.chain))
check("use_t2i_ is cleared so core does not render a second time", r.use_t2i_ is False)

CALLS.clear()
ev = EVENT(result=Result([PLAIN(LONG)]))
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(ev))
check("local render result is tracked for cleanup", ev.tracked == ["C:/tmp/rendered.png"], repr(ev.tracked))

print("\n=== template data ===")

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
data = CALLS[0]["data"]
check("content/raw_text/text/html are all populated",
      all(k in data and isinstance(data[k], str) and data[k] for k in ("content", "raw_text", "text", "html")))
check("raw_text keeps the joined leading Plain text", LONG.split("\n\n")[0] in data["raw_text"])
check("version is prefixed with v", data["version"] == "v4.26.0", data["version"])
check("datetime variables are injected",
      {"datetime", "date", "time", "timestamp", "timezone", "year", "weekday"} <= set(data))
check("screenshot options default to full-page png",
      CALLS[0]["options"] == {"type": "png", "full_page": True, "animations": "disabled"}, repr(CALLS[0]["options"]))

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
check("umo is omitted when html_render does not accept it", CALLS[0]["kwargs"] == {}, repr(CALLS[0]["kwargs"]))

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render_with_umo)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
check("umo is forwarded when html_render accepts it",
      CALLS[0]["kwargs"] == {"umo": "aiocqhttp:GroupMessage:100"}, repr(CALLS[0]["kwargs"]))

print("\n=== template_file ===")

CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(template_file="templates/frosted-glass.html")]),
                render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
expected = (ROOT / "templates" / "frosted-glass.html").read_text(encoding="utf-8")
check("template_file content is used verbatim (outer whitespace trimmed)",
      CALLS[0]["template"] == expected.strip())
check("template_file wins over the inline template_html", CALLS[0]["template"] != INLINE_TEMPLATE)

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(template_file="templates/nope.html")]),
                render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
check("a missing template_file falls back to template_html",
      CALLS and CALLS[0]["template"] == INLINE_TEMPLATE)
check("the missing template_file is reported", LOGGER.warned("template_file not found"))

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(template_file="../../secret.html")]),
                render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
check("a template_file escaping the plugin dir is refused",
      CALLS and CALLS[0]["template"] == INLINE_TEMPLATE and LOGGER.warned("must stay inside"))

CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(template_html="", template_file="")]),
                render=ok_render)
r = Result([PLAIN(LONG)])
run(p.on_decorating_result(EVENT(result=r)))
check("a profile with no template at all is skipped and core keeps the text",
      CALLS == [] and isinstance(r.chain[0], PLAIN) and r.use_t2i_ is None)

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(template_html="<div><script>x</script></div>")]),
                render=ok_render)
r = Result([PLAIN(LONG)])
run(p.on_decorating_result(EVENT(result=r)))
check("an unsafe inline template is skipped and reported",
      CALLS == [] and isinstance(r.chain[0], PLAIN) and LOGGER.warned("blocked unsafe template profile"))

print("\n=== cache: editing the template file takes effect ===")

scratch = ROOT / "_scratch_tpl.html"
scratch.write_text("<article>VERSION-ONE {{ content | safe }}</article>", encoding="utf-8")
try:
    CALLS.clear()
    p = make_plugin(plugin_config(template_profiles=[base_profile(template_file="_scratch_tpl.html")]),
                    render=ok_render)
    run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
    first = CALLS[0]["template"]
    scratch.write_text("<article>VERSION-TWO-IS-LONGER {{ content | safe }}</article>", encoding="utf-8")
    CALLS.clear()
    run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
    second = CALLS[0]["template"]
    check("editing the file changes what is rendered without touching the config",
          "VERSION-ONE" in first and "VERSION-TWO" in second, f"{first[:40]!r} -> {second[:40]!r}")
finally:
    scratch.unlink(missing_ok=True)

print("\n=== failure paths ===")

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=boom_render)
r = Result([PLAIN(LONG)])
run(p.on_decorating_result(EVENT(result=r)))
check("a raising renderer keeps the text and blocks a second core render",
      isinstance(r.chain[0], PLAIN) and r.use_t2i_ is False and LOGGER.warned("failed to render"))

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=empty_render)
r = Result([PLAIN(LONG)])
run(p.on_decorating_result(EVENT(result=r)))
check("an empty render result is treated as a failure",
      isinstance(r.chain[0], PLAIN) and r.use_t2i_ is False)

LOGGER.clear()
CALLS.clear()
ev = EVENT(result=Result([PLAIN(LONG)]))
ev.track_raises = True
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(ev))
check("a failing temp-file tracker does not lose the image",
      isinstance(ev.get_result().chain[0], IMAGE) and LOGGER.warned("temp-file cleanup"))

LOGGER.clear()
CALLS.clear()
IMAGE._fail_fs = True
try:
    p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
    r = Result([PLAIN(LONG)])
    run(p.on_decorating_result(EVENT(result=r)))
    check("an image-component failure degrades to text without raising",
          isinstance(r.chain[0], PLAIN) and r.use_t2i_ is False and LOGGER.warned("could not build an image component"))
finally:
    IMAGE._fail_fs = False

LOGGER.clear()
p = make_plugin(plugin_config())
r = Result([PLAIN(LONG)])
bad_ctx = CONTEXT()
bad_ctx.raises = True
p.context = bad_ctx
run(p.on_decorating_result(EVENT(result=r)))
check("a config read failure is handled",
      isinstance(r.chain[0], PLAIN) and LOGGER.warned("failed to read the AstrBot config"))

print("\n=== background selection ===")

CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(
    background_candidates=["https://a.example/1.png", "https://b.example/2.png"],
    background_switch_mode="sequential")]), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
seen = []
for _ in range(4):
    run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
    seen.append(CALLS[-1]["data"]["bg_url"])
check("sequential mode rotates through the candidates in order",
      seen == ["https://a.example/1.png", "https://b.example/2.png",
               "https://a.example/1.png", "https://b.example/2.png"], repr(seen))

CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(
    background_candidates=["https://a.example/1.png"],
    background_switch_mode="fixed")]), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
check("fixed mode always uses the first candidate",
      CALLS[0]["data"]["bg_url"] == "https://a.example/1.png")

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
check("no candidates means an empty bg_url", CALLS[0]["data"]["bg_url"] == "")

print("\n=== custom vars ===")

CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(
    custom_vars_json='{"site_name": "S", "bg_url": "hijack", "content": "hijack"}')]),
    {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
d = CALLS[0]["data"]
check("custom vars are injected", d.get("site_name") == "S")
check("reserved names cannot be hijacked",
      d["bg_url"] == "" and d["content"] != "hijack", f"bg_url={d['bg_url']!r} content={d['content']!r}")

print("\n=== screenshot options ===")

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(
    screenshot_options_json='{"clip": {"x": 0, "y": 0, "width": 800, "height": 600}}')]),
    {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
opts = CALLS[0]["options"]
check("clip drops the default full_page (Playwright rejects the pair)",
      opts.get("clip") == {"x": 0, "y": 0, "width": 800, "height": 600} and "full_page" not in opts,
      repr(opts))

CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(
    screenshot_options_json='{"type": "jpeg", "quality": 80}')]),
    {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
opts = CALLS[0]["options"]
check("an explicit jpeg + quality still keeps full_page",
      opts.get("type") == "jpeg" and opts.get("quality") == 80 and opts.get("full_page") is True,
      repr(opts))

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(template_profiles=[base_profile(
    screenshot_options_json='{"clip": {"x": 0, "y": 0, "width": 800, "height": 600}, "full_page": true}')]),
    {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
check("an explicit clip + full_page is passed through with a warning",
      CALLS[0]["options"].get("full_page") is True and LOGGER.warned("cannot be combined"))

print("\n=== failure policy ===")

LOGGER.clear()
CALLS.clear()
p = make_plugin(plugin_config(fallback_to_core_t2i=True),
                {"t2i": True, "t2i_word_threshold": 10}, render=boom_render)
r = Result([PLAIN(LONG)])
run(p.on_decorating_result(EVENT(result=r)))
check("fallback_to_core_t2i leaves use_t2i_ alone so core can render",
      isinstance(r.chain[0], PLAIN) and r.use_t2i_ is None, repr(r.use_t2i_))

print("\n=== leading blank line ===")

CALLS.clear()
p = make_plugin(plugin_config(), {"t2i": True, "t2i_word_threshold": 10}, render=ok_render)
run(p.on_decorating_result(EVENT(result=Result([PLAIN(LONG)]))))
d = CALLS[0]["data"]
check("raw_text / content do not begin with the core-identical blank line",
      not d["raw_text"].startswith("\n") and not d["content"].startswith("\n"),
      repr(d["raw_text"][:8]))

print("\n=== registration ===")

check("PLUGIN_VERSION is the single source for @register",
      main.T2IEnhancePlugin._register_args[3] == main.PLUGIN_VERSION,
      repr(main.T2IEnhancePlugin._register_args))

print()
print("RESULT:", "ALL OK" if failures == 0 else f"{failures} FAILURE(S)")
sys.exit(1 if failures else 0)
