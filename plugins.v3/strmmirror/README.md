# 115 STRM 副库

适用于 MoviePilot 3.1.6 及以上 V3 版本。115 STRM 助手负责生成源文件。本插件沿用「清理媒体文件」的原生文件事件监听方式，优先使用 watchfiles，也可使用 watchdog，将影片目录同步到副库，并为 STRM 写入新播放地址。

| MoviePilot 插件设置 | 示例 |
| --- | --- |
| 源 STRM 目录 | `/ssd/strm` |
| 副库输出目录 | `/ssd/strm-funnel` |
| 新的 STRM 播放 URL | `https://relay.example.net/api/v1/plugin/P115StrmHelper/redirect_url` |

填写 MoviePilot 容器内的路径。两个目录需要分开，MoviePilot 要能读取源目录并写入输出目录，Emby 要能读取两套目录。目标 URL 可以包含固定参数，插件会从源文件填充 `pickcode` 和可选的 `file_name`。源链接中的 API Key 和其他查询参数不会被复制。

启用时先启动监听，并补齐一次存量文件。之后按事件处理。比如源目录的 `series/国产剧/片名/Season 01/第 1 集.strm` 会对应副库中的同一相对路径。检测到新增、更新或移入的 STRM 时，按相对路径同步对应的影片或剧集目录，包含图片、NFO、外挂字幕等普通文件。后续单独添加或更新的附属文件也会跟随同步。分类目录中的平铺 STRM 关联同名附属文件。源端删除或改名不会触发副库清理。副库文件也不应纳入会联动删除 115 原视频的监控范围。

在 Emby 中分别为直连和 Funnel 建库，使用 Emby 容器看到的实际路径。电影库分别指向源目录和副库的 `movies`，剧集库分别指向各自的 `series`。如果现有源目录里已经有 Funnel 链接，本插件也能生成对应的副库文件。要把存量源库切换成直连，需要单独迁移源文件。

上线时先启用副库并在纯 IPv4 网络试播。确认后，在 115 STRM 助手中设置直连模板，用于后续新生成的源 STRM：

```text
https://direct.example.net:4430/api/v1/plugin/P115StrmHelper/redirect_url?pickcode={{ pickcode }}{% if file_name %}&file_name={{ file_name | urlencode }}{% endif %}
```
