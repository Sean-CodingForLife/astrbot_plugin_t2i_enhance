# T2I Enhance

Render Markdown structure before AstrBot text-to-image generation.

AstrBot's default T2I flow may pass Markdown text directly into an HTML template, which can make headings, lists, quotes, code blocks, and tables look like one flat block of text. This plugin converts outgoing plain Markdown text into safe HTML before T2I rendering, so templates using `{{ text | safe }}` can preserve the original document structure.

## Features

- Converts Markdown to safe HTML before T2I rendering
- Preserves headings, paragraphs, lists, quotes, code blocks, tables, footnotes, and admonitions
- Sanitizes rendered HTML with `bleach`
- Skips content that already looks like rendered HTML
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

Keep your T2I HTML template using:

```html
{{ text | safe }}
```

The plugin renders Markdown into sanitized HTML before AstrBot passes the text into the template.

## Notes

This plugin is designed for AstrBot's HTML-based T2I rendering flow. If your T2I setup uses a pure Pillow/local renderer instead of an HTML template renderer, the rendered HTML may not be displayed as intended.

