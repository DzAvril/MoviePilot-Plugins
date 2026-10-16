# 音乐歌单同步

<img src="https://raw.githubusercontent.com/DzAvril/MoviePilot-Plugins/main/icons/MusicPlaylistSync-1.7.1.png" width="96" alt="音乐歌单同步图标">

MoviePilot V3 插件，持续同步多个 **QQ 音乐、网易云音乐公开歌单**。为新增歌曲创建原生单曲订阅并立即发起搜索，下载与整理仍由 MP 完成。

当前版本 **1.7.1**，已在 MoviePilot **3.1.6** 联调。沿用插件 ID `QQMusicPlaylistSync`，旧版配置、订阅、账本和选曲记录可继续使用。

## 功能

- QQ 完整分页；网易云先取完整歌曲 ID，再按每批最多 200 首补齐详情，避免只导入网页预览部分。
- 支持多个歌单、QQ 官方短分享链接、网易云桌面与移动端链接；不同歌单读取失败时分别保留上次完整快照。
- 同平台按歌曲身份去重。跨平台只有在歌名、全部歌手、专辑、已知年份一致、时长相差不超过 2 秒且候选唯一时合并，同名不同版本独立保留。
- 本地音乐库已有歌曲跳过；原生订阅与完成历史参与去重，重启后不重复创建。
- 建好订阅立即提交 MP 原生手动搜索队列；后续新增优先处理。仍服从站点预算、冷却和订阅过滤。
- 始终保持 `recording` 单曲身份。从分轨专辑只勾选歌单需要的音轨；**含 CUE、仅有曲序、缺曲、版本歧义、无法验证文件清单的资源跳过**。
- qB 任务暂停添加 → 核对文件 → 只选目标音轨 → 回读优先级 → 登记所选文件 → 启动。任何选曲或回读失败都保持暂停。
- 歌曲状态显示待搜索、下载中、待入库、已入库；依据实际音轨进度与成功整理结果，每 15 秒更新。

公开歌单无需 Cookie。插件只读取音乐平台公开元数据，音频通过 MP 已配置站点获取。私密或要求登录的歌单暂不支持；没有匹配资源的歌曲保留订阅等待。

## 安装与配置

1. 在 MP 插件市场仓库设置中加入 `https://github.com/DzAvril/MoviePilot-Plugins`。
2. 刷新市场，安装 **音乐歌单同步**；V3 索引为仓库根 `package.v3.json`，联邦资源通过对应版本 Release 分发。
3. QQ、网易云分别填写在对应栏中，每行一个链接或数字 ID。网易云支持 `https://music.163.com/#/my/m/music/playlist?id=...`。
4. 开启持续同步，可先用“只预览歌单”核对总数，再关闭预览以创建订阅。

下载器、下载目录、音乐库目录 **留空时跟随 MP 音乐设置**，填写时仅覆盖对应字段。分轨选曲目前需要 qBittorrent。插件不会代替用户设置存储目录。

| 设置 | 默认 | 说明 |
| --- | --- | --- |
| 持续同步 | 关闭 | 启用后按间隔检查全部歌单 |
| 只预览歌单 | 开启 | 读取歌单，不创建订阅 |
| 同步间隔 | 1 分钟 | 1–1440 分钟 |
| 同时创建订阅数 | 4 | 1–8 路，有界并行 |
| 建好订阅立即搜索 | 开启 | 使用原生手动搜索队列 |
| 下载器、下载与音乐库目录 | 留空 | 跟随 MP 设置 |

## 兼容性与数据

注册 `qqmusic` 与 `netease` 单曲来源，不伪造 MusicBrainz 身份。QQ MID 与网易云数字 ID 保持原生身份，内部加来源前缀避免撞号。

账本通过 MP 插件数据接口持久化；完整快照才更新成员关系。移出歌单不会删除已有文件或取消原订阅。跨平台首次导入前保留 `state_before_netease_v1` 备份。

当前 MP 3.1.6 下载合同没有音轨选择字段，因此 `selected.py` 在已验证的关键词、候选匹配和下载提交边界做窄范围内存适配。只处理本插件追踪的单曲，停止时恢复原函数，重载不叠加；宿主签名不兼容时阻止本插件提交，不能回退整张专辑下载。升级主程序后应重新检查适配器状态。BT 共享分片可能带来少量邻曲缓存字节，未选歌曲的优先级仍为零。

插件 Python 依赖均由当前 MP 音乐运行环境提供，无额外安装清单。普通数据接口使用 MP API 认证；图片和联邦文件沿用 MP 静态资源访问检查。

## 开发验证

按[官方 V3 开发指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/Plugin_Development.md)与[发布指南](https://github.com/jxxghp/MoviePilot-Plugins/blob/main/docs/Repository_Guide.md)组织源码、元数据、图标和测试。

```sh
python -m compileall -q plugins.v3/qqmusicplaylistsync
python .github/scripts/check_plugin_versions.py package.v3.json
python -m pytest -q tests/v3/qqmusicplaylistsync
npm --prefix plugins.v3/qqmusicplaylistsync run check
npm --prefix plugins.v3/qqmusicplaylistsync run build
node --test tests/v3/qqmusicplaylistsync/test_page_ui.mjs
git diff --check
```

前端采用直接编写的 Vue 渲染函数 ESM，无 TypeScript/SFC 编译步骤。`frontend/` 为可维护源码，`build` 先校验模块语法再生成 `dist/assets/`，Vue 由 MP 联邦共享运行时提供，无前端第三方构建依赖。

145 项 Python 与 5 项页面验证覆盖完整读取、配置默认值、跨平台身份、增量去重、失败隔离、即时搜索、逐文件选曲与状态联动。纯模块测试使用 `app.plugins.qqmusicplaylistsync.*` 生产模块身份，方法契约隔离宿主运行时，不访问真实账号、数据库或下载器。

网易云读取方式参考“歌单同步工具”的完整成员读取策略，使用官方元数据接口和有界超时，不读取参考插件的登录配置。图标由内置 imagegen 生成，随插件分发。
