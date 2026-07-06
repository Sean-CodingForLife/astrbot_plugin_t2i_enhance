# T2I Enhance

> 为自定义 AstrBot HTML T2I 模板预渲染 Markdown，保留结构、控制清洗范围，并避免污染官方内置模板流程。

![T2I Enhance Icon](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/icon.svg)

## 简介

`T2I Enhance` 是一个面向 AstrBot 文转图链路的增强插件。

它的目标不是替代 AstrBot 官方内置模板，而是服务于这一类自定义模板：

```html
{{ text | safe }}
```

当你的 T2I 模板直接把 `text` 当 HTML 渲染时，这个插件会在 AstrBot 真正进入 T2I 流程之前，把 Markdown 转成经过 `bleach` 清洗的 HTML，从而保留标题、列表、引用、代码块、表格等结构。

## 适用场景

- 你正在使用自定义 HTML T2I 模板
- 模板直接渲染 `{{ text | safe }}`
- 你希望 Markdown 在图片里保持结构，而不是变成一整块纯文本
- 你希望可配置地控制允许的标签、属性、协议和 HTML 检测规则

## 不适用场景

- AstrBot 官方内置模板：`base`、`astrbot_vitepress`、`astrbot_powershell`
- 模板内部还会再次解析 Markdown
- 非 HTML 渲染器
- 不希望在 T2I 前对输出文本做任何结构化处理

## 功能特性

- 在 T2I 渲染前把 Markdown 转成安全 HTML
- 保留标题、段落、列表、引用、代码块、表格、脚注、admonition 等结构
- 使用 `bleach` 清洗渲染后的 HTML
- 已经像 HTML 的内容可以跳过转换
- 复刻 AstrBot 当前 T2I 触发条件，包括 `t2i`、`use_t2i_`、消息链结构和 `t2i_word_threshold`
- 默认排除 AstrBot 官方内置 Markdown 模板，避免重复渲染
- 通过插件设置暴露 Markdown 扩展、标签白名单、属性白名单、协议白名单和 HTML 检测规则

## 兼容性

### AstrBot 版本

- 推荐：`>=4.26,<5`

### 平台

这个插件本身不直接依赖某个消息平台的专属能力，它作用在 AstrBot 的 T2I 文本处理链路上。

理论上，只要对应平台上的消息最终会进入 AstrBot 的标准 T2I 流程，就可以使用。当前元数据里已补充常见平台声明，具体仍以你的 AstrBot 运行链路为准。

## 安装

1. 将当前目录放入 AstrBot 插件目录：

   ```text
   data/plugins/astrbot_plugin_t2i_enhance
   ```

2. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. 在 AstrBot WebUI 中重载插件。

## 快速开始

推荐模板写法：

```html
{{ text | safe }}
```

推荐流程：

1. 在 AstrBot 中启用 T2I。
2. 使用一个自定义 HTML 模板，并确保模板直接渲染 `text`。
3. 启用本插件。
4. 发送超过 `t2i_word_threshold` 的 Markdown 文本，验证图片内是否保留结构。

## 插件设置

插件配置定义位于 [_conf_schema.json](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/_conf_schema.json:1)。

主要配置项：

- `plugin_enabled`：是否启用插件
- `skip_existing_html`：检测到消息已经像 HTML 时是否跳过转换
- `excluded_templates`：永远不预渲染的模板名列表
- `markdown_extensions`：传给 Python-Markdown 的扩展列表
- `allowed_protocols`：`bleach` 清洗时允许保留的 URL 协议
- `allowed_tags`：清洗后允许保留的 HTML 标签
- `allowed_attributes_json`：JSON 形式的标签属性白名单
- `html_tag_pattern`：用于检测现有 HTML 的 regex

## 工作原理

这个插件不会盲目改写所有文本，而是尽量与当前 AstrBot 的官方行为对齐：

1. 读取当前会话配置。
2. 判断本次消息是否真的会进入 T2I 流程。
3. 排除官方内置 Markdown 模板。
4. 复用 AstrBot 的前置 `Plain` 文本链路和 `t2i_word_threshold` 逻辑。
5. 仅在满足条件时把 Markdown 转成清洗后的 HTML。

## 项目结构

```text
.
├─ main.py
├─ metadata.yaml
├─ _conf_schema.json
├─ requirements.txt
├─ icon.svg
└─ CHANGELOG.md
```

## 开发

本项目是一个轻量 AstrBot 插件仓库，当前没有引入复杂的构建流程。

本地开发建议：

1. 修改代码或配置 schema。
2. 在 AstrBot WebUI 中重载插件。
3. 使用自定义 HTML T2I 模板联调。
4. 检查短文本、长文本、官方模板、自定义模板四种路径。

## 已知限制

- 仅在 AstrBot 实际进入 T2I 流程时生效
- 默认不接管官方内置 Markdown 模板
- `allowed_attributes_json` 使用 JSON 文本配置，是为了更稳地兼容当前 AstrBot 插件配置 schema 约束

## 变更记录

详见 [CHANGELOG.md](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/CHANGELOG.md:1)。

## 许可证

本仓库使用 [MIT License](C:/Users/Administrator/Desktop/astrbot_plugin_t2i_enhance/LICENSE:1)。
