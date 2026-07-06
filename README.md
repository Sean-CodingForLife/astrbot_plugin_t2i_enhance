# T2I Enhance

> 插件自己维护 HTML 模板，自己注入变量，自己调用 `html_render(template, data, options)` 渲染，不再读取或接管任何官方模板内容。

![T2I Enhance Icon](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/icon.svg)

## 先看这个

这版从架构上已经和官方模板彻底分开。

### 1. 官方模板是官方的，插件模板是插件自己的

现在开始，这个插件不再：

- 读取官方模板 HTML
- 绑定官方模板名
- 跟随官方模板切换
- 接手任何官方模板内容

现在的分工非常明确：

- AstrBot 官方模板：官方自己的系统，和本插件无关
- T2I Enhance 模板：插件自己维护，插件自己使用

也就是说，**不做交叉，不做混用，不做联动。**

### 2. 为什么要这样改

因为官方模板编辑器保存模板时有变量白名单限制。

比如你想在模板里写：

- `{{ bg_url }}`
- `{{ content | safe }}`
- `{{ datetime }}`

官方模板编辑器会直接拦截，不让保存。

所以如果插件还依赖官方模板内容，就会一直被官方模板保存校验卡住。

现在改成插件自己维护模板后，这个限制就不再存在。

### 3. 现在的核心原则

从 `v3.0.0` 开始，这个插件只有一条路线：

- 模板 HTML 由插件自己保存
- 模板变量由插件自己注入
- 渲染流程由插件自己执行

官方只剩下两件事还会影响插件：

- AstrBot 的 T2I 总开关
- AstrBot 的 T2I 触发阈值

除此之外，插件不再依赖官方模板系统。

## 现在怎么工作

插件渲染流程变成：

1. 检查当前 AstrBot 是否开启 T2I
2. 检查当前文本长度是否超过 AstrBot 当前阈值
3. 从插件配置里取出当前启用的 `active_profile`
4. 读取这条 profile 里的 `template_html`
5. 生成模板变量 `data`
6. 调用 `html_render(template_html, data, options)`
7. 把结果替换成图片

所以现在模板来源只有一个：

- `template_profiles[].template_html`

## 快速上手

第一次使用建议按这个顺序来：

1. 打开插件配置
2. 在 `template_profiles` 里保留或新增一条模板配置
3. 给这条配置起一个 `name`
4. 把 `active_profile` 填成这个 `name`
5. 在这条配置的 `template_html` 里写模板
6. 打开 `render_markdown`
7. 直接测试

默认模板就是：

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>New Template</title>
</head>
<body>
  <!-- 从这里开始编辑 -->
  <article>{{ text | safe }}</article>
</body>
</html>
```

## 最容易踩坑的地方

### 1. `active_profile` 没填对

插件现在不再按官方模板名命中配置，而是按：

- 顶层 `active_profile`
- 对应 `template_profiles[].name`

这两个值来选择当前模板。

如果 `active_profile = neon`，但你的模板配置名是 `default`，那插件不会用到你想要的模板。

### 2. 你还在官方模板页里改模板

现在已经没用了。

因为插件不再读取官方模板 HTML，所以你在官方模板页里改：

- `{{ bg_url }}`
- `{{ datetime }}`
- `{{ content | safe }}`

都不会影响插件这边的渲染。

你现在要改的是：

- 插件配置里的 `template_profiles[].template_html`

### 3. 你把背景图链接写到 `custom_vars_json`

不对。

背景图应该放在：

- `background_candidates`

模板里写：

```html
url("{{ bg_url }}")
```

不要自己在 `custom_vars_json` 里重复定义 `bg_url`。

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

每条模板配置里的 `custom_vars_json` 也会一起注入。

重点解释：

- `text`：增强后的正文，默认适合直接输出
- `raw_text`：原始文本，未经过 Markdown 渲染
- `content`：增强后的正文 HTML
- `html`：同 `content`
- `template_name`：当前插件模板配置名，不再是官方模板名

## 模板怎么写

### 最省事的写法

```html
<article>{{ text | safe }}</article>
```

优点：

- 第一次接入不用多想
- Markdown 增强可以直接生效

### 推荐写法

```html
<article>{{ content | safe }}</article>
```

优点：

- 语义更清楚
- `text` 和 `raw_text` 的职责更容易区分

### 原文写法

```html
<article>{{ raw_text }}</article>
```

### 背景图写法

```css
background:
  linear-gradient(rgba(3, 6, 12, 0.55), rgba(3, 6, 12, 0.7)),
  url("{{ bg_url }}") center / cover no-repeat;
```

更稳一点：

```jinja2
background:
  linear-gradient(rgba(3, 6, 12, 0.55), rgba(3, 6, 12, 0.7))
  {% if bg_url %}, url("{{ bg_url }}") center / cover no-repeat{% endif %};
```

### 时间变量写法

```html
<span>{{ date }}</span>
<span>{{ time }}</span>
<span>{{ datetime }}</span>
```

## 配置说明

配置定义见 [_conf_schema.json](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/_conf_schema.json:1)。

顶层配置项：

- `plugin_enabled`
- `active_profile`
- `template_profiles`

每条 `template_profiles` 模板配置包含：

- `enabled`
- `name`
- `template_html`
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

比如你想做两套插件模板：

- `default`
- `neon`

那插件里就可以配两条模板配置：

- `name = default`
- `name = neon`

然后顶层：

- `active_profile = neon`

这样插件就会使用 `neon` 这套模板，不再看官方模板系统。

## 出问题先查什么

如果你测试后发现“插件没反应”或者“Markdown 像没生效”，先按这个顺序检查：

1. `plugin_enabled` 是否开启
2. `active_profile` 是否填对
3. `template_profiles` 里有没有同名且启用的配置
4. 当前选中的那条配置里 `template_html` 是否非空
5. `render_markdown` 有没有打开
6. 模板正文现在是 `{{ text | safe }}` 还是 `{{ content | safe }}`
7. 当前文本长度是否超过 AstrBot 当前的 T2I 触发阈值

## 官方对照

本插件当前实现对照了 AstrBot 官方文档和源码，关键点如下：

- 官方文档支持 `html_render(template, data, options)`
- `data` 确实是 Jinja2 渲染变量
- AstrBot 默认 `t2i_word_threshold` 是 `150`
- `on_decorating_result` 钩子可以直接改结果链
- 官方模板编辑器存在变量白名单限制，所以本插件从 `v3.0.0` 起不再依赖官方模板内容

因此当前方案不是修改 Core，而是彻底改为插件自维护模板、自维护变量、自执行渲染。

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
