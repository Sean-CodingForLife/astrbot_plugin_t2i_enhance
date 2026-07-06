# T2I Enhance

Render Markdown structure before AstrBot text-to-image generation.

This plugin is only for custom AstrBot T2I templates that render `text` as raw HTML. It converts outgoing Markdown into sanitized HTML right before AstrBot runs text-to-image, so templates using `{{ text | safe }}` can preserve headings, lists, quotes, code blocks, and tables.

It does not target AstrBot's official built-in templates such as `base`, `astrbot_vitepress`, or `astrbot_powershell`. Those templates already parse Markdown themselves with `marked.parse(...)`, so pre-rendering Markdown to HTML would conflict with the official flow.

## Features

- Converts Markdown to safe HTML before T2I rendering
- Preserves headings, paragraphs, lists, quotes, code blocks, tables, footnotes, and admonitions
- Sanitizes rendered HTML with `bleach`
- Skips content that already looks like rendered HTML
- Mirrors AstrBot's own T2I gating, including `t2i`, `use_t2i_`, the message-chain shape, and `t2i_word_threshold`
- Ignores AstrBot's official Markdown-driven templates to avoid double rendering
- Works with custom HTML T2I templates that use `{{ text | safe }}`

## Installation

1. Copy this folder to your AstrBot plugin directory:

   ```text
   data/plugins/astrbot_plugin_t2i_enhance
   ```

2. Install plugin dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Reload the plugin in AstrBot WebUI.

## Requirements

- `markdown>=3.6`
- `bleach>=6.1.0`

## Recommended T2I Template

Use a custom T2I template that renders `text` directly:

```html
{{ text | safe }}
```

The plugin renders Markdown into sanitized HTML before AstrBot passes the text into the template.

## Notes

- This plugin only runs when AstrBot would already enter its T2I path and the plain-text payload length exceeds `t2i_word_threshold` (default `150`).
- This plugin does not affect AstrBot's official built-in templates, because they already render Markdown inside the template.
- If your T2I setup uses a non-HTML renderer, or a template that re-parses Markdown instead of rendering raw HTML, this plugin is not the right tool.

