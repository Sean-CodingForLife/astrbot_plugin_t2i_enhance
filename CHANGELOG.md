# Changelog

## v1.1.0 - 2026-07-06

- Added plugin settings via `_conf_schema.json` for template exclusions, Markdown extensions, HTML detection, and sanitization allowlists.
- Removed more hard-coded behavior from the plugin implementation and moved it into configurable settings.
- Updated README and metadata to document the new configuration surface.

## v1.0.1 - 2026-07-06

- Reworked the plugin to mirror AstrBot's own T2I gating before converting Markdown.
- Prevented raw HTML from leaking into normal text replies when the payload does not enter T2I rendering.
- Limited the plugin to custom templates that directly render `{{ text | safe }}`.
- Excluded AstrBot's official built-in templates, which already parse Markdown internally.
- Updated README and metadata to match actual AstrBot behavior.

## v1.0.0 - 2026-07-06

- Initial release.
- Added Markdown-to-safe-HTML conversion before AstrBot T2I rendering.
- Added support for headings, lists, blockquotes, code blocks, tables, footnotes, definition lists, and admonitions.
- Added HTML sanitization with `bleach`.

