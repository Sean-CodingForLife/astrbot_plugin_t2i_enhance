# T2I Enhance

在 AstrBot 文转图前保留 Markdown 结构。

这个插件只适用于自定义 AstrBot T2I 模板，并且模板需要把 `text` 直接当原始 HTML 渲染。插件会在 AstrBot 执行文转图之前，把输出的 Markdown 转成经过清洗的 HTML，这样使用 `{{ text | safe }}` 的模板就能保留标题、列表、引用、代码块、表格等结构。

它不会作用于 AstrBot 官方内置模板，例如 `base`、`astrbot_vitepress`、`astrbot_powershell`。这些模板本身已经通过 `marked.parse(...)` 解析 Markdown，提前把 Markdown 渲染成 HTML 反而会和官方流程冲突。

## 功能说明

- 在 T2I 渲染前把 Markdown 转成安全 HTML
- 保留标题、段落、列表、引用、代码块、表格、脚注、admonition 等结构
- 使用 `bleach` 清洗渲染后的 HTML
- 已经看起来像 HTML 的内容可以跳过转换
- 复刻 AstrBot 自己的 T2I 触发条件，包括 `t2i`、`use_t2i_`、消息链结构和 `t2i_word_threshold`
- 默认忽略 AstrBot 官方 Markdown 模板，避免重复渲染
- 适用于使用 `{{ text | safe }}` 的自定义 HTML T2I 模板
- sanitizer 和匹配行为都可以通过插件设置调整，不再依赖硬编码常量

## 安装方式

1. 把当前目录复制到 AstrBot 插件目录：

   ```text
   data/plugins/astrbot_plugin_t2i_enhance
   ```

2. 安装插件依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. 在 AstrBot WebUI 里重载插件。

4. 如果你想调整排除模板、Markdown 扩展、HTML 检测规则或 sanitizer 白名单，可以在 AstrBot WebUI 里打开插件设置。

## 依赖要求

- `markdown>=3.6`
- `bleach>=6.1.0`

## 推荐模板写法

推荐使用直接渲染 `text` 的自定义 T2I 模板：

```html
{{ text | safe }}
```

插件会在 AstrBot 把 `text` 传进模板之前，先把 Markdown 转成经过清洗的 HTML。

## 插件设置

插件当前通过 [_conf_schema.json](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/_conf_schema.json:1) 读取配置。主要设置项如下：

- `plugin_enabled`：控制插件是否启用。
- `skip_existing_html`：当消息内容本身已经像 HTML 时，是否跳过转换。
- `excluded_templates`：这些模板名永远不会被本插件预渲染。
- `markdown_extensions`：转换前传给 Python-Markdown 的扩展列表。
- `allowed_protocols`：`bleach` 清洗时允许保留的 URL 协议。
- `allowed_tags`：清洗后允许保留的 HTML 标签。
- `allowed_attributes_json`：JSON 对象，用来配置每个标签允许保留哪些 HTML 属性。
- `html_tag_pattern`：用于判断文本是否已经包含 HTML 的 regex。

## 注意事项

- 只有当 AstrBot 本来就会进入 T2I 流程，并且纯文本长度超过 `t2i_word_threshold`（默认 `150`）时，插件才会生效。
- 插件不会影响 AstrBot 官方内置模板，因为这些模板已经会在模板内部处理 Markdown。
- 如果你的 T2I 使用的不是 HTML 渲染器，或者模板本身还会再次解析 Markdown，那这个插件并不适合你的场景。

