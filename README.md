# T2I Enhance

> 按官方模板名绑定增强配置，接管 AstrBot T2I 渲染，并且默认兼容官方模板里的 `{{ text | safe }}`。

![T2I Enhance Icon](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/icon.svg)

## 先看这个

这部分最重要，第一次使用前建议先看完。

### 1. 插件不负责保存 HTML 模板

这插件不会在插件设置里再维护一份 HTML 模板。

现在的分工是：

- 官方模板页面：负责保存和编辑 HTML 模板
- 本插件：负责按模板名绑定增强配置，并接管最终渲染

也就是说，**模板内容仍然在 AstrBot 官方 T2I 模板系统里维护。**

### 2. 插件现在默认兼容官方模板

这是这次文档里最需要强调的点。

AstrBot 官方默认模板通常这样写正文：

```html
<article>{{ text | safe }}</article>
```

为了避免第一次接入时“明明开了 Markdown 渲染却完全没效果”，插件现在会把**增强后的正文结果**同时写回：

- `text`
- `content`
- `html`

并额外保留：

- `raw_text`：未经过 Markdown 渲染的原始文本

所以现在有两种都能正常工作的写法：

官方默认写法：

```html
<article>{{ text | safe }}</article>
```

增强写法：

```html
<article>{{ content | safe }}</article>
```

结论：

- 第一次接入时，不改官方默认模板正文变量，也能看到 Markdown 生效
- 如果你想语义更清晰，后续再改成 `{{ content | safe }}` 更合适

### 3. 为什么以前会让人觉得“插件失效了”

因为插件早期增强语义是：

- `text`：原始文本
- `content`：Markdown 渲染后的 HTML

这会导致一个很糟糕的首次体验：

1. 用户绑定了官方模板名
2. 打开了 Markdown 渲染
3. 去测试
4. 官方模板还在用 `{{ text | safe }}`
5. 看起来就像插件完全没生效

现在这条坑已经补上了，插件默认兼容官方模板，不需要第一次就手改正文变量。

## 插件到底做什么

`T2I Enhance` 不是“全局一套增强配置”，而是：

1. 先读取当前 AstrBot 已激活的官方 T2I 模板名
2. 在插件自己的 `template_profiles` 里查找同名配置
3. 读取当前官方模板 HTML
4. 生成这一组模板专属的增强变量
5. 调用 `html_render(template, data, options)` 渲染
6. 把结果直接替换成图片

也就是说：

- 模板 HTML：官方维护
- 模板增强参数：插件维护
- 最终渲染执行：插件接管

## 快速上手

第一次使用建议按这个顺序来：

1. 在 AstrBot 设置里选好当前要用的官方 T2I 模板
2. 到官方“自定义文转图 HTML 模板”页面里编辑那个模板
3. 在插件设置里新增一条 `template_profiles`
4. 把这条配置里的 `template_name` 填成同一个官方模板名
5. 打开 `render_markdown`
6. 直接测试

如果你现在的官方模板正文还是：

```html
<article>{{ text | safe }}</article>
```

也没问题，这版插件会直接兼容。

## 最容易踩坑的地方

这部分建议重点看。

### 1. `template_name` 没填对

插件是“按当前官方模板名命中配置”的。

如果当前激活模板名是 `test`，而你在插件配置里写的是 `base`，那插件不会使用这条配置。

要保证：

- 当前激活模板名
- `template_profiles` 里的 `template_name`

这两个值完全一致。

### 2. 你以为模板也在插件里

不是。

插件设置里没有 HTML 编辑器，不代表模板丢了，而是因为：

- HTML 模板在官方页面里
- 插件只管理绑定配置和增强变量

### 3. 你想用背景图变量，但模板没写 `{{ bg_url }}`

插件能注入 `bg_url`，但模板是否使用它，是模板自己的事。

如果模板里没写：

```html
{{ bg_url }}
```

或者没把它放进 CSS / style 里，那背景图增强当然不会显示。

### 4. 你想拿原始文本，但现在 `text` 已经是增强结果

为了兼容官方默认模板，现在：

- `text` 是增强后的正文
- `raw_text` 才是原始文本

如果你模板里真的需要“未经 Markdown 渲染的原文”，请用：

```html
{{ raw_text }}
```

## 变量说明

插件会注入这些变量：

- `text`
- `raw_text`
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

重点解释：

- `text`：增强后的正文，默认兼容官方模板
- `raw_text`：原始文本，未经过 Markdown 渲染
- `content`：增强后的正文 HTML，推荐你后续逐步改用它
- `html`：同 `content`

## 模板怎么写

### 最省事的写法

继续沿用官方默认正文：

```html
<article>{{ text | safe }}</article>
```

优点：

- 第一次接入不用改模板
- Markdown 增强可以直接生效

### 推荐写法

如果你已经明确要走插件增强语义，建议用：

```html
<article>{{ content | safe }}</article>
```

优点：

- 语义更清楚
- `text` 和 `raw_text` 的职责更容易区分

### 原文写法

如果你就是要拿未经渲染的原文：

```html
<article>{{ raw_text }}</article>
```

## 绑定配置说明

插件配置定义见 [_conf_schema.json](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/_conf_schema.json:1)。

顶层配置只有两个：

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

## 多模板示例

比如你有两个官方模板：

- `base`
- `test`

那插件里就可以配两条绑定：

- `template_name = base`
  这一条专门给 `base` 模板使用
- `template_name = test`
  这一条专门给 `test` 模板使用

这样当 AstrBot 当前激活模板从 `base` 切到 `test` 时，插件也会自动切到 `test` 对应的增强配置。

## 渲染流程

基础调用方式：

```python
await self.html_render(template, data, options=options)
```

其中：

- `template`：当前 AstrBot 已启用的官方 T2I 模板内容
- `data`：当前模板绑定配置组生成的增强变量
- `options`：当前模板绑定配置组的截图参数

## 出问题先查什么

如果你测试后发现“插件没反应”或者“Markdown 像没生效”，先按这个顺序检查：

1. 当前 AstrBot 激活模板名是什么
2. 插件里有没有同名的 `template_profiles.template_name`
3. 这条 profile 有没有启用
4. `render_markdown` 有没有打开
5. 模板正文现在是 `{{ text | safe }}` 还是 `{{ content | safe }}`  
这两种现在都可以，但如果你写成别的变量，就可能看不到结果
6. 当前文本长度是否超过 AstrBot 当前的 T2I 触发阈值

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
