# 极影视助手 1.8.0（MoviePilot V3）

在原有豆瓣观影状态同步与评分功能上增加字幕搜索页。输入片名或 IMDb ID，可查看字幕版本、格式和大小，并筛选、翻页。
同时填写片名和 IMDb ID 时优先使用 IMDb ID，空结果再回退片名。搜索结果仅在内存中缓存五分钟。

这一版只搜索和展示，不下载、解包或挂载字幕。字幕下载定位信息不会返回浏览器、记录到插件数据或输出日志。
原 V2 插件及其配置不变；V3 复用同一插件 ID `ZvideoHelper`，沿用已有豆瓣配置。

## NAS 授权环境

插件在自己的数据目录 `ZvideoHelper/subtitle-cli` 调用已有的极空间原生 CLI。原 CLI 独立管理 OAuth、刷新和凭证，
插件不读取、导出或复制凭证文件。此实现无需 Mac 常驻。

原 CLI 使用你已有的安装包，本仓库只包含插件与扩展源码。
请从自己的 `zspace-nas-agent-toolkit` 安装包取出 `bin/zspace-cli-linux-x64`（ARM64 NAS 对应 `linux-arm64`），
放入插件数据目录并命名为 `zspace-cli`，设置为仅当前用户可执行。默认 V3 容器内路径：

```text
/config/plugins/ZvideoHelper/subtitle-cli/zspace-cli
```

首次授权在 NAS 终端执行（按实际容器名调整）：

```sh
docker exec -it \
  -e ZSPACE_CLI_HOME=/config/plugins/ZvideoHelper/subtitle-cli/profile \
  MoviePilot_V3 /config/plugins/ZvideoHelper/subtitle-cli/zspace-cli \
  --profile zvideohelper --credential-store file login --no-open
```

在浏览器自行授权，将一次性授权码直接粘贴到终端隐藏输入框。不要把授权码、Cookie 或 Token 填进插件配置或聊天。
CLI 文件后端使用权限收紧的专用目录；这个 profile 只供本插件使用。

## 接入边界

- 仅额外允许 `POST /subs/v2/searchsub`，仅接受字符串 `q`。
- 无 Rust 源码时，由本机临时中继转换一个固定只读传输路径，认证始终由原 CLI 完成。
- NAS 使用插件专用 profile，搜索时串行设置临时连接地址，进入和退出时恢复自动选路；中断后下次搜索先恢复。
- 中继仅监听本机随机端口，拒绝其他业务路径、额外参数和上游重定向，随搜索结束关闭。
- 必须在局域网中可访问极空间 NAS；未验证云端代理。
- CLI 版本基线 0.1.4。实测 IMDb ID、片名有效，`db` 前缀的豆瓣 ID 可能为空。

## 开发验证

```sh
python3 -m unittest discover -s tests/v3/zvideohelper -v
node plugins.v3/zvideohelper/frontend/build.mjs
```
