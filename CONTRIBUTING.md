# 贡献指南

## 提交前建议

1. 确认改动符合当前 AstrBot 官方 T2I 行为。
2. 如果修改了 `_conf_schema.json`，同时更新 README。
3. 如果修改了用户可见行为，同时更新 CHANGELOG。
4. 尽量补充最小必要说明，避免让插件能力和文档脱节。

## 代码风格

- Python 使用 4 空格缩进
- 优先保持实现简单直接
- 配置项尽量通过 `_conf_schema.json` 暴露，而不是继续硬编码

## 测试建议

至少手动覆盖以下路径：

- AstrBot 的 `t2i` 关闭时插件不应介入
- 自定义 `{{ text | safe }}` 模板下插件应正常生效
- 短文本不应进入 T2I 预渲染
- 结果链开头不是连续 `Plain` 时插件应跳过
- 模板命中安全校验时插件应跳过该模板并回退为纯文本
- `active_profile` 与任何已启用配置都不匹配时，应回落并输出告警日志
- `template_file` 指向插件目录外的路径（绝对路径、`..` 穿越、其他盘符）时应被拒绝、告警并回退到 `template_html`
- `template_file` 指向存在的文件时应优先于 `template_html`；文件被删后应告警并回退
- 修改 `template_file` 指向的文件后，下一次渲染应使用新内容（缓存指纹包含文件 mtime 与大小）
- 背景图候选里含有引号、空白、反斜杠等字符时应被剔除，其余候选继续参与切换
- 渲染成功后图片组件构建失败时，应回退为纯文本而不是抛异常中断整条回复
- `screenshot_options_json` 里配置 `clip` 时应自动去掉默认的 `full_page`，否则 Playwright 会拒绝这组选项
- `fallback_to_core_t2i` 关闭时渲染失败应抑制本次 T2I；开启时应保留 `use_t2i_`，由 Core 用官方模板渲染
- 一段带 `!!! note` 的文本经默认配置渲染后，`<p>` 上的 `admonition-title` 类应被保留

## 自动化验证

`tests/` 下有两个不依赖 AstrBot 的验证脚本，直接 `python` 运行即可（退出码非 0 表示失败）：

- [tests/verify_validators.py](tests/verify_validators.py) —— 用 AST 从 `main.py` 中抽出真实函数来跑：模板安全校验与负向样本、`template_file` 路径限制、背景图 URL 收紧、缓存指纹、`strftime` 容错。
- [tests/verify_plugin.py](tests/verify_plugin.py) —— 用桩模块替换 `astrbot` / `bleach` / `markdown`，直接驱动真实的 `on_decorating_result`：开关判定、结果链替换、模板数据、背景切换、失败路径。

两者都会从脚本自身位置推导仓库根目录，因此在任意工作目录下运行都可以。
