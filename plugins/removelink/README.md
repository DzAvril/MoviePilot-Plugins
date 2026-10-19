# 清理媒体文件

2.18 的设置界面沿用「做种复核」的青绿色样式，按运行设置、硬链接、STRM 联动和清理选项分区。切换分区仅编辑本地草稿，点击保存后才交给 MP 保存配置。界面不提供立即清理操作。

13 个原配置键、默认值、目录和映射格式均保留。清理与监控代码沿用 2.17；原生表单保留为兼容入口。共享 Vue 由 MP 提供，发布资产不包含独立 Vue 或 Vuetify 基础样式。

## 开发验证

```sh
npm --prefix plugins/removelink run check
npm --prefix plugins/removelink run build
for test in tests/removelink_*regression.py; do python "$test"; done
```

`tests/removelink_ui.test.mjs` 使用真实 Vue 的自定义渲染器，验证草稿切换、取消、配置保留和保存校验。通过 `REMOVELINK_VUE_RUNTIME` 指向 Vue 3 浏览器运行时 `.mjs` 文件，或在可解析的位置安装 Vue 后运行：

```sh
node --test tests/removelink_ui.test.mjs
```

CI 运行配置兼容、现有清理回归、真实 Vue 交互、样式范围及构建复现检查，主分支通过后发布含 `dist/assets` 的标准插件 ZIP。文件清理回归只使用测试临时目录。
