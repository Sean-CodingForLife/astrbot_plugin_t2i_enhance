# T2I Enhance

> 插件启动后会按当前 AstrBot 官方 T2I 模板名，匹配对应的增强配置组，再通过 `html_render(template, data, options)` 接管渲染。

![T2I Enhance Icon](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/icon.svg)

## 简介

`T2I Enhance` 现在不是“全局一套增强配置”。

现在的工作方式是：

1. AstrBot 里先选好当前正在使用的官方 T2I 模板
2. 插件在结果装饰阶段接管渲染
3. 插件读取当前激活模板名
4. 插件在自己的 `template_profiles` 里找到同名绑定配置
5. 插件读取当前官方模板 HTML
6. 插件构造这一组模板专属的增强变量
7. 插件调用 `html_render(template, data, options)`
8. 插件直接把结果替换成图片

也就是说，**模板 HTML 仍然在 AstrBot 官方模板系统里维护，插件只负责“按模板名绑定增强配置”并接管渲染。**

## 架构

基础调用方式：

```python
await self.html_render(template, data, options=options)
```

其中：

- `template`：当前 AstrBot 已启用的官方 T2I 模板内容
- `data`：当前模板绑定配置组生成的增强变量
- `options`：当前模板绑定配置组的截图参数

## 核心能力

- 自动接管当前 AstrBot 已启用模板
- 按官方模板名绑定不同的增强配置
- 后端变量注入
- 背景图变量注入
- 日期时间变量注入
- 自定义 JSON 变量注入
- Markdown 转安全 HTML
- 原始 HTML 清洗
- 截图参数透传

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
- `version`

每条绑定配置里的 `custom_vars_json` 也会一起注入。

## 现在怎么用

你只需要：

1. 在 AstrBot 设置里选好当前 T2I 模板
2. 在官方“自定义文转图 HTML 模板”页面里编辑那个模板
3. 在插件里新增一条 `template_profiles`
4. 把这条配置的 `template_name` 填成同一个官方模板名
5. 再按这条模板需要的变量、背景图、时间格式、Markdown 规则去配置

当当前激活模板名命中这条绑定配置时，插件就会自动使用这一组增强参数。

## 插件配置

配置定义见 [_conf_schema.json](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/_conf_schema.json:1)。

顶层配置项：

- `plugin_enabled`
- `template_profiles`

每条 `template_profiles` 绑定配置包含：

- `enabled`
- `template_name`
- `inject_datetime`
- `timezone`
- `datetime_format`
- `date_format`
- `time_format`
- `render_markdown`
- `sanitize_html_input`
- `background_candidates`
- `custom_vars_json`
- `screenshot_options_json`
- `markdown_extensions`
- `allowed_protocols`
- `allowed_tags`
- `allowed_attributes_json`

## 模板里该怎么写

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

如果你还要自定义变量，例如：

```json
{
  "site_name": "AstrBot",
  "card_title": "今日简报"
}
```

那模板里就可以直接写：

```html
<h1>{{ card_title }}</h1>
<p>{{ site_name }}</p>
```

## 绑定示例

比如你有两个官方模板：

- `base`
- `test`

那插件里就可以配两条绑定：

- `template_name = base`
  这一条专门给 `base` 模板使用
- `template_name = test`
  这一条专门给 `test` 模板使用

这样当 AstrBot 当前激活模板从 `base` 切到 `test` 时，插件也会自动切到 `test` 这一组增强配置。

## 官方对照

本插件当前实现对照了 AstrBot 官方文档和源码，关键点如下：

- 官方文档支持 `html_render(template, data, options)`
- `data` 确实是 Jinja2 渲染变量
- AstrBot 默认 `t2i_word_threshold` 是 `150`
- `ResultDecorateStage` 会缓存 `t2i_active_template`
- `on_decorating_result` 钩子可以直接改结果链
- `_conf_schema.json` 官方支持 `template_list`

因此当前方案不是修改 Core，而是使用官方公开给插件的渲染能力和配置能力来接管当前激活模板。

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
