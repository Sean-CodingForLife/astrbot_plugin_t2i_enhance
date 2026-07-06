# Changelog

## v1.1.0 - 2026-07-06

- 通过 `_conf_schema.json` 新增插件设置，支持配置模板排除列表、Markdown 扩展、HTML 检测规则和 sanitization 白名单。
- 进一步减少实现中的硬编码，把可调行为迁移到插件设置中。
- 更新 README 和 metadata，使其与新的配置结构保持一致。

## v1.0.1 - 2026-07-06

- 重构插件逻辑，在转换 Markdown 之前先复刻 AstrBot 自己的 T2I 触发条件。
- 避免在没有进入 T2I 渲染时，把原始 HTML 泄露到普通文本回复里。
- 将插件适用范围限制为直接渲染 `{{ text | safe }}` 的自定义模板。
- 排除 AstrBot 官方内置模板，因为这些模板本身已经会解析 Markdown。
- 更新 README 和 metadata，使其与实际 AstrBot 行为一致。

## v1.0.0 - 2026-07-06

- 初始版本。
- 新增在 AstrBot T2I 渲染前将 Markdown 转为安全 HTML 的能力。
- 支持标题、列表、引用、代码块、表格、脚注、定义列表和 admonitions。
- 使用 `bleach` 对 HTML 进行清洗。

