# T2I Enhance

> 基于 `html_render(template, data, options)` 的 AstrBot T2I 增强插件。

![T2I Enhance Icon](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/icon.svg)

## 简介

`T2I Enhance` 是一套完整的插件侧 HTML 渲染架构，不依赖旧式“改写文本后再交给 Core 猜怎么处理”的做法。

插件会在命中 AstrBot T2I 条件后：

1. 提取前导 `Plain` 文本
2. 选择模板
3. 构造模板变量 `data`
4. 调用 `self.html_render(template, data, options)`
5. 将结果直接替换为图片消息

这个插件的唯一核心就是：**用插件后端直接驱动 HTML 模板渲染。**

## 架构

基础调用方式：

```python
await self.html_render(template, data, options=options)
```

其中：

- `template`: 完整 HTML 模板
- `data`: 后端注入的模板变量
- `options`: 截图参数

插件不是只传一个 `text`，而是自己构造完整变量集，再把渲染结果直接回填到消息链。

## 核心能力

- 自主接管符合条件的 AstrBot T2I 渲染
- 候选模板切换
- 后端变量注入
- 背景图变量注入
- 日期时间变量注入
- 自定义 JSON 变量注入
- Markdown 转安全 HTML
- 原始 HTML 清洗
- 截图参数透传

## 模板切换

支持三种模板切换模式：

- `fixed`: 固定使用第一个启用模板
- `random`: 每次随机选择
- `sequential`: 按顺序轮换，并持久化记录当前位置

## 模板变量

插件会注入这些变量：

- `text`
- `content`
- `html`
- `template_name`
- `bg_url`
- `date`
- `time`
- `datetime`
- `timestamp`
- `timezone`
- `year`
- `month`
- `day`
- `hour`
- `minute`
- `second`
- `weekday`

`custom_vars_json` 中的键值也会一起注入。

## 配置

配置定义见 [_conf_schema.json](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/_conf_schema.json:1)。

主要配置项：

- `plugin_enabled`
- `respect_official_excluded_templates`
- `excluded_templates`
- `template_switch_mode`
- `inject_datetime`
- `timezone`
- `datetime_format`
- `date_format`
- `time_format`
- `custom_vars_json`
- `global_background_candidates`
- `screenshot_options_json`
- `markdown_extensions`
- `allowed_protocols`
- `allowed_tags`
- `allowed_attributes_json`
- `template_candidates`

## 模板候选

每个候选模板支持：

- `enabled`
- `name`
- `title`
- `subtitle`
- `footer_left`
- `footer_right`
- `render_markdown`
- `sanitize_html_input`
- `background_candidates`
- `template_html`

## 模板示例

正文通常这样输出：

```html
<section class="content">
  {{ content | safe }}
</section>
```

背景图通常这样使用：

```html
<div class="hero" style="background-image: url('{{ bg_url }}');">
```

日期时间通常这样使用：

```html
<span>{{ date }}</span>
<span>{{ time }}</span>
<span>{{ datetime }}</span>
```

## 官方对照

本插件当前实现对照了 AstrBot 官方文档和源码，关键点如下：

- 官方文档支持 `html_render(template, data, options)`
- `data` 确实是 Jinja2 渲染变量
- AstrBot 默认 `t2i_word_threshold` 是 `150`
- Core 会把阈值最小保护到 `50`
- `ResultDecorateStage` 会缓存 `t2i_active_template`
- `on_decorating_result` 钩子可以直接改结果链

所以动态模板、动态变量、动态背景图这类需求，放在插件里自己 `html_render` 是正路。

## 安装

1. 放入 AstrBot 插件目录：

```text
data/plugins/astrbot_plugin_t2i_enhance
```

2. 安装依赖：

```bash
pip install -r requirements.txt
```

3. 在 AstrBot WebUI 重载插件

## 版本要求

- AstrBot: `>=4.26,<5`

## 支持平台

见 [metadata.yaml](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/metadata.yaml:1)。

## 变更记录

见 [CHANGELOG.md](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/CHANGELOG.md:1)。

## 许可证

本仓库使用 [MIT License](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/LICENSE:1)。
