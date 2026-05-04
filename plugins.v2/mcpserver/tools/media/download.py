import json
import logging
import mcp.types as types
from ..base import BaseTool
from .recognize import MediaRecognizeTool
from ..resource_cache import resource_cache


# Configure logging
logger = logging.getLogger(__name__)


class MovieDownloadTool(BaseTool):
    """媒体搜索和下载工具"""

    def __init__(self, token_manager=None):
        super().__init__(token_manager)
        # 创建媒体识别工具实例
        self._recognize_tool = MediaRecognizeTool(token_manager)

    async def execute(self, tool_name: str, arguments: dict) -> list[types.TextContent | types.ImageContent]:
        """执行工具逻辑"""
        if tool_name == "search-media-resources":
            return await self._search_media_resources(arguments)
        elif tool_name == "fuzzy-search-media-resources":
            return await self._fuzzy_search_media_resources(arguments)
        elif tool_name == "search-site-resources":
            return await self._search_site_resources(arguments)
        elif tool_name == "download-torrent":
            return await self._download_torrent(arguments)
        elif tool_name == "get-downloaders":
            return await self._get_downloaders(arguments)
        else:
            return [
                types.TextContent(
                    type="text",
                    text=f"错误：未知的工具 '{tool_name}'"
                )
            ]

    @staticmethod
    def _as_dict(value) -> dict:
        """Return dict values as-is and treat malformed nested API fields as empty."""
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _first_text(*values, default: str = "") -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return default

    def _format_search_results(self, torrents: list, keyword: str, year: str = None, detailed: bool = True, limit: int = 50) -> str:
        """
        格式化搜索结果

        参数:
            torrents: 种子列表
            keyword: 搜索关键词
            year: 年份(可选)
            detailed: 是否显示详细信息(默认为True)
            limit: 最大返回结果数量(默认为50)

        返回:
            格式化后的文本
        """
        if not torrents:
            return f"未找到符合条件的资源：{keyword} {year or ''}"

        # 限制结果数量
        if limit > 0 and len(torrents) > limit:
            torrents = torrents[:limit]
            result_text = f"找到 {len(torrents)} 个资源（已限制显示前 {limit} 个）：\n\n"
        else:
            result_text = f"找到 {len(torrents)} 个资源：\n\n"
        for i, torrent in enumerate(torrents):
            # 检查torrent是否是字典类型
            if not isinstance(torrent, dict):
                logger.warning(f"种子数据不是字典类型: {type(torrent)}")
                continue

            # 提取需要的信息
            # 检查torrent_info字段
            torrent_info = self._as_dict(torrent.get("torrent_info"))
            meta_info = self._as_dict(torrent.get("meta_info"))
            if not torrent_info:
                # 可能是Context对象的直接序列化
                torrent_info = torrent

            # 从torrent_info中提取数据
            title = self._first_text(
                torrent_info.get("description"),
                torrent_info.get("title"),
                meta_info.get("subtitle"),
                meta_info.get("org_string"),
                default="未知标题"
            )

            site_name = self._first_text(
                torrent_info.get("site_name"),
                torrent_info.get("site"),
                default="未知站点"
            )

            # 处理大小显示
            size_bytes = torrent_info.get("size", 0)
            if isinstance(size_bytes, (int, float)) and size_bytes > 0:
                # 转换为人类可读的大小
                if size_bytes < 1024:
                    size = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size = f"{size_bytes/1024:.2f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    size = f"{size_bytes/(1024*1024):.2f} MB"
                else:
                    size = f"{size_bytes/(1024*1024*1024):.2f} GB"
            else:
                size = torrent_info.get("size", "未知大小")

            # 提取分辨率
            resolution = "未知分辨率"
            if meta_info:
                # 尝试直接从标题中提取分辨率
                title_str = self._first_text(meta_info.get("org_string"))
                if title_str:
                    import re
                    res_pattern = (
                        r'(4K|1080[pi]|720[pi]|2160[pi]|UHD|'
                        r'MINIBD1080P|BD1080P|HD1080P|BD720P|HD720P)'
                    )
                    res_match = re.search(
                        res_pattern, title_str, re.IGNORECASE)
                    if res_match:
                        resolution = res_match.group(1)

            seeders = torrent_info.get("seeders", 0)
            peers = torrent_info.get("peers", 0)

            # 格式化资源信息
            result_text += f"{i+1}. {title}\n"
            result_text += f"   站点: {site_name} | 大小: {size}\n"
            result_text += f"   分辨率: {resolution}\n"
            result_text += f"   做种: {seeders} | 下载: {peers}\n"

            # 如果需要详细信息，添加更多字段
            if detailed:
                # 是否H&R
                is_hr = torrent_info.get("hit_and_run", False)
                # 打折
                discount = torrent_info.get("volume_factor", 0)

                # 提取视频编码
                video_encode = self._first_text(
                    meta_info.get("video_encode"), default="未知编码")
                # 提取音频编码
                audio_encode = self._first_text(
                    meta_info.get("audio_encode"), default="未知音频")
                # 提取资源类型
                resource_type = self._first_text(
                    meta_info.get("resource_type"), default="未知来源")
                # 提取制作组/字幕组
                resource_team = self._first_text(meta_info.get("resource_team"))

                # 提取字幕信息
                subtitle_info = "无字幕信息"
                description = self._first_text(
                    torrent_info.get("description"),
                    torrent_info.get("title"),
                    meta_info.get("subtitle"),
                    meta_info.get("org_string")
                )
                if description:
                    # 检查是否包含字幕信息
                    subtitle_keywords = [
                        "中字", "中文字幕", "简体", "繁体",
                        "双语", "特效字幕", "SUP", "SRT", "ASS"
                    ]
                    subtitle_matches = []
                    for keyword in subtitle_keywords:
                        if keyword in description:
                            subtitle_matches.append(keyword)

                    if subtitle_matches:
                        subtitle_info = "、".join(subtitle_matches)

                # 提取音轨信息
                audio_info = "未知音轨"
                audio_keywords = ["国语", "粤语", "英语", "双语", "多语", "国英双语", "中英双语"]
                audio_matches = []
                for keyword in audio_keywords:
                    if keyword in description:
                        audio_matches.append(keyword)

                if audio_matches:
                    audio_info = "、".join(audio_matches)

                # 添加详细信息
                result_text += (
                    f"   视频编码: {video_encode} | "
                    f"音频编码: {audio_encode}\n"
                )
                result_text += f"   资源类型: {resource_type}"
                if resource_team:
                    result_text += f" | 制作组: {resource_team}"
                result_text += "\n"
                result_text += f"   字幕: {subtitle_info} | 音轨: {audio_info}\n"
                if is_hr:
                    result_text += "   H&R: 是\n"
                result_text += f"   折扣: {discount}\n"

            # 生成资源标识符并缓存真实下载链接
            resource_id = resource_cache.generate_resource_id(torrent_info)
            resource_cache.store_resource(resource_id, torrent_info)

            # 添加资源标识符（隐藏真实下载链接）
            result_text += f"   资源标识符: {resource_id}\n\n"

        return result_text

    async def _search_media_resources(self, arguments: dict) -> list[types.TextContent]:
        """
        搜索媒体资源
        参数:
            - keyword: 媒体名称关键词(可选)
            - mediaid: 媒体ID(可选)，格式为"tmdb:123"或"douban:456"，如果提供则优先使用
            - year: 年份(可选)
            - resolution: 清晰度(可选)，如 1080p, 2160p, 4K 等
            - media_type: 媒体类型(可选)，默认为 "电影"
            - sites: 站点ID列表(可选)，多个站点ID用逗号分隔
            - limit: 最大返回结果数量(可选)，默认为50
        """
        # 检查是否直接提供了媒体ID
        mediaid = arguments.get("mediaid")
        keyword = arguments.get("keyword")

        # 如果既没有提供mediaid也没有提供keyword，则返回错误
        if not mediaid and not keyword:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供媒体名称关键词或媒体ID"
                )
            ]

        # 获取其他可选参数
        year = arguments.get("year")
        media_type = arguments.get("media_type", "电影")
        sites = arguments.get("sites")

        # 强制要求提供sites参数
        if not sites:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供sites参数，指定1-3个站点ID进行搜索，避免token超限。可通过get-sites工具获取站点列表。"
                )
            ]

        limit = int(arguments.get("limit", 50))  # 默认限制为10个结果

        try:
            # 如果直接提供了媒体ID，则直接使用
            media_id = mediaid

            # 如果没有提供媒体ID，则尝试识别媒体信息
            if not media_id:
                # 首先识别媒体信息
                media_info = await self._recognize_tool.recognize_media(keyword, year, media_type)
                if not media_info:
                    # 媒体识别失败，建议用户使用search-media工具
                    suggestion_text = (
                        f"无法识别媒体信息：{keyword} {year or ''}\n\n"
                        f"建议使用search-media工具进行模糊搜索，找到正确的媒体信息后再使用search-movie工具。\n"
                        f"例如：search-media工具，参数 keyword=\"{keyword}\"\n"
                    )
                    return [
                        types.TextContent(
                            type="text",
                            text=suggestion_text
                        )
                    ]

                # 获取媒体ID
                if "tmdb_id" in media_info and media_info["tmdb_id"]:
                    media_id = f"tmdb:{media_info['tmdb_id']}"
                elif "douban_id" in media_info and media_info["douban_id"]:
                    media_id = f"douban:{media_info['douban_id']}"

                if not media_id:
                    return [
                        types.TextContent(
                            type="text",
                            text=f"无法获取媒体ID：{keyword} {year or ''}"
                        )
                    ]

            # 搜索资源
            params = {
                "mediaid": media_id,
                "mtype": "电影" if media_type == "电影" else "电视剧",
                "sites": sites,
                "sort": "seeders"
            }

            # 调用搜索API
            try:
                response = await self._make_request(
                    method="GET",
                    endpoint=f"/api/v1/search/media/{media_id}",
                    params=params
                )
            except Exception as e:
                logger.error(f"调用搜索API时出错: {str(e)}")
                return [
                    types.TextContent(
                        type="text",
                        text=f"搜索资源时出错: {str(e)}"
                    )
                ]

            # 检查是否有错误
            is_error_response = (
                isinstance(response, dict) and
                not response.get("success", False)
            )
            if is_error_response:
                return [
                    types.TextContent(
                        type="text",
                        text=f"搜索资源失败: {response.get('message', '未知错误')}"
                    )
                ]

            # 获取搜索结果
            torrents = response.get("data", [])

            # 使用公共方法格式化结果
            result_text = self._format_search_results(
                torrents, keyword, year, detailed=True, limit=limit)

            return [
                types.TextContent(
                    type="text",
                    text=result_text
                )
            ]

        except Exception as e:
            logger.error(f"搜索媒体资源时出错: {str(e)}")
            return [
                types.TextContent(
                    type="text",
                    text=f"搜索媒体资源时出错: {str(e)}"
                )
            ]

    async def _download_torrent(
        self, arguments: dict
    ) -> list[types.TextContent]:
        """
        下载指定的种子资源
        参数:
            - torrent_url: 种子资源下载链接（与resource_id二选一）
            - resource_id: 资源标识符（与torrent_url二选一）
            - downloader: 下载器名称(可选)
            - save_path: 保存路径(可选)
        """
        torrent_url = arguments.get("torrent_url")
        resource_id = arguments.get("resource_id")

        # 检查参数：必须提供torrent_url或resource_id之一
        if not torrent_url and not resource_id:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供要下载的资源链接(torrent_url)或资源标识符(resource_id)"
                )
            ]

        # 如果提供了resource_id，从缓存中获取真实下载链接
        if resource_id and not torrent_url:
            torrent_url = resource_cache.get_torrent_url(resource_id)
            if not torrent_url:
                return [
                    types.TextContent(
                        type="text",
                        text=f"错误：无法找到资源标识符对应的下载链接: {resource_id}。可能资源已过期或不存在。"
                    )
                ]
            logger.info(f"通过资源标识符 {resource_id} 获取到下载链接")

        # 如果同时提供了两个参数，优先使用torrent_url
        if torrent_url and resource_id:
            logger.info("同时提供了torrent_url和resource_id，优先使用torrent_url")

        # 获取其他可选参数
        downloader = arguments.get("downloader")
        save_path = arguments.get("save_path")

        try:
            logger.info(f"开始下载资源，URL: {torrent_url}")

            # 如果没有指定下载器，尝试获取可用的下载器列表
            if not downloader:
                logger.info("未指定下载器，尝试获取可用的下载器列表")

                # 获取下载器列表
                downloaders = await self._make_request(
                    method="GET",
                    endpoint="/api/v1/download/clients"
                )

                # 如果找到了下载器列表，尝试选择一个可用的下载器
                if downloaders:
                    for dl in downloaders:
                        if isinstance(dl, dict) and dl.get("status", True):
                            downloader = dl.get("name")
                            logger.info(f"自动选择下载器: {downloader}")
                            break

            # 准备请求参数
            payload = {
                "torrent_url": torrent_url,
                "downloader": downloader,
                "media_type": arguments.get("media_type")
            }

            # 添加其他可选参数
            if save_path:
                payload["save_path"] = save_path

            # 调用mcpserver的下载API
            response = await self._make_request(
                method="POST",
                endpoint="/api/v1/plugin/MCPServer/download_torrent",
                json=payload
            )

            # 记录响应
            # logger.info(f"下载API响应: {json.dumps(response, ensure_ascii=False)}")

            # 检查是否有错误
            is_error = (
                isinstance(response, dict) and
                not response.get("success", False)
            )
            if is_error:
                error_msg = response.get("message", "未知错误")
                logger.error(f"添加下载任务失败: {error_msg}")
                return [
                    types.TextContent(
                        type="text",
                        text=f"添加下载任务失败: {error_msg}"
                    )
                ]

            # 下载成功
            site_name = response.get("site", "未知站点")
            save_path = response.get("save_path", "默认路径")
            success_msg = f"已成功添加下载任务：来自 {site_name} 的种子，保存至 {save_path}"
            logger.info(success_msg)
            return [
                types.TextContent(
                    type="text",
                    text=success_msg
                )
            ]

        except Exception as e:
            logger.error(f"下载资源时出错: {str(e)}", exc_info=True)
            return [
                types.TextContent(
                    type="text",
                    text=f"下载资源时出错: {str(e)}"
                )
            ]

    async def _get_sites_info(self):
        """获取所有站点信息"""
        try:
            # 调用站点API获取所有站点信息
            sites_response = await self._make_request(
                method="GET",
                endpoint="/api/v1/site/"
            )

            # 检查响应格式
            if isinstance(sites_response, list):
                return sites_response
            elif isinstance(sites_response, dict) and "data" in sites_response:
                return sites_response.get("data", [])
            return []
        except Exception as e:
            logger.warning(f"获取站点信息失败: {str(e)}")
            return []

    async def _ensure_site_mapping(self):
        """确保站点映射缓存是最新的"""
        try:
            # 检查站点映射是否过期
            if resource_cache.is_site_mapping_expired():
                logger.info("站点映射缓存已过期，正在更新...")

                # 获取站点信息
                sites_data = await self._get_sites_info()
                if sites_data:
                    resource_cache.update_site_mapping(sites_data)
                    logger.info("站点映射缓存已更新")
                else:
                    logger.warning("无法获取站点信息，站点映射缓存未更新")
        except Exception as e:
            logger.error(f"更新站点映射缓存失败: {str(e)}")

    async def _search_site_resources(self, arguments: dict) -> list[types.TextContent]:
        """
        在指定站点搜索资源，直接使用关键词搜索，无需媒体ID
        参数:
            - site_id: 站点ID(必需)
            - keyword: 搜索关键词(必需)
            - cat: 资源分类(可选)，501=电影，502=剧集，503=纪录片，504=动画，505=综艺
            - limit: 最大返回结果数量(可选)，默认为50
        """
        site_id = arguments.get("site_id")
        keyword = arguments.get("keyword")

        # 检查必需参数
        if not site_id:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供站点ID(site_id)参数"
                )
            ]

        if not keyword:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供搜索关键词(keyword)参数"
                )
            ]

        # 获取可选参数
        cat = arguments.get("cat")
        limit = int(arguments.get("limit", 50))

        try:
            logger.info(f"开始在站点 {site_id} 搜索资源，关键词：{keyword}")

            # 确保站点映射是最新的
            await self._ensure_site_mapping()

            # 构建请求参数
            params = {
                "keyword": keyword
            }

            # 添加分类参数
            if cat:
                params["cat"] = cat

            # 调用站点资源搜索API
            response = await self._make_request(
                method="GET",
                endpoint=f"/api/v1/site/resource/{site_id}",
                params=params
            )

            # 处理不同的响应格式
            if isinstance(response, list):
                # 如果响应直接是列表，则这就是资源列表
                resources = response
            elif isinstance(response, dict):
                # 检查是否有错误
                if not response.get("success", True):
                    error_msg = response.get("message", "未知错误")
                    return [
                        types.TextContent(
                            type="text",
                            text=f"站点资源搜索失败: {error_msg}"
                        )
                    ]
                # 获取搜索结果
                resources = response.get("data", [])
            else:
                # 未知响应格式
                logger.error(f"未知的API响应格式: {type(response)}")
                return [
                    types.TextContent(
                        type="text",
                        text=f"API响应格式错误: {type(response)}"
                    )
                ]

            if not resources:
                # 获取站点名称用于错误消息（优先从缓存获取，因为没有资源数据）
                site_name = resource_cache.get_site_name(site_id)
                site_display = f"{site_name}({site_id})" if site_name != site_id else site_id
                return [
                    types.TextContent(
                        type="text",
                        text=f"在站点 {site_display} 未找到符合条件的资源：{keyword}"
                    )
                ]

            # 格式化结果
            result_text = self._format_site_search_results(resources, keyword, site_id, limit)

            return [
                types.TextContent(
                    type="text",
                    text=result_text
                )
            ]

        except Exception as e:
            logger.error(f"站点资源搜索时出错: {str(e)}")
            return [
                types.TextContent(
                    type="text",
                    text=f"站点资源搜索时出错: {str(e)}"
                )
            ]

    def _format_site_search_results(self, resources: list, keyword: str, site_id: str, limit: int = 50) -> str:
        """
        格式化站点搜索结果，注意隐私保护

        参数:
            resources: 资源列表
            keyword: 搜索关键词
            site_id: 站点ID
            limit: 最大返回结果数量

        返回:
            格式化后的文本
        """
        # 从第一个资源中获取站点名称（如果有的话）
        site_name = None
        if resources and len(resources) > 0:
            first_resource = resources[0]
            if isinstance(first_resource, dict):
                site_name = first_resource.get("site_name")

        # 如果没有从API响应获取到站点名称，则尝试从缓存获取
        if not site_name:
            site_name = resource_cache.get_site_name(site_id)

        # 构建站点显示名称
        if site_name and site_name != site_id:
            site_display = f"{site_name}({site_id})"
        else:
            site_display = site_id

        if not resources:
            return f"在站点 {site_display} 未找到符合条件的资源：{keyword}"

        # 限制结果数量
        if limit > 0 and len(resources) > limit:
            resources = resources[:limit]
            result_text = f"在站点 {site_display} 找到 {len(resources)} 个资源（已限制显示前 {limit} 个）：\n\n"
        else:
            result_text = f"在站点 {site_display} 找到 {len(resources)} 个资源：\n\n"

        for i, resource in enumerate(resources):
            if not isinstance(resource, dict):
                logger.warning(f"资源数据不是字典类型: {type(resource)}")
                continue

            # 提取基本信息
            title = resource.get("title", "未知标题")
            description = resource.get("description", "")

            # 处理大小显示
            size_bytes = resource.get("size", 0)
            if isinstance(size_bytes, (int, float)) and size_bytes > 0:
                if size_bytes < 1024:
                    size = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size = f"{size_bytes/1024:.2f} KB"
                elif size_bytes < 1024 * 1024 * 1024:
                    size = f"{size_bytes/(1024*1024):.2f} MB"
                else:
                    size = f"{size_bytes/(1024*1024*1024):.2f} GB"
            else:
                size = "未知大小"

            # 提取分辨率（从标题中解析）
            resolution = "未知分辨率"
            if title:
                import re
                res_pattern = (
                    r'(4K|1080[pi]|720[pi]|2160[pi]|UHD|'
                    r'MINIBD1080P|BD1080P|HD1080P|BD720P|HD720P)'
                )
                res_match = re.search(res_pattern, title, re.IGNORECASE)
                if res_match:
                    resolution = res_match.group(1)

            # 种子统计信息
            seeders = resource.get("seeders", 0)
            peers = resource.get("peers", 0)
            grabs = resource.get("grabs", 0)

            # 免费信息
            freedate = resource.get("freedate", "")
            freedate_diff = resource.get("freedate_diff", "")
            volume_factor = resource.get("volume_factor", "")
            upload_factor = resource.get("uploadvolumefactor", 1.0)
            download_factor = resource.get("downloadvolumefactor", 1.0)

            # 质量标签
            labels = resource.get("labels", [])
            labels_str = "、".join(labels) if labels else "无标签"

            # H&R状态
            hit_and_run = resource.get("hit_and_run", False)

            # IMDB ID
            imdbid = resource.get("imdbid", "")

            # 页面链接
            page_url = resource.get("page_url", "")

            # 提取视频编码（从标题和描述中解析）
            video_encode = "未知编码"
            video_keywords = ["H264", "H.264", "x264", "H265", "H.265", "x265", "HEVC", "AVC", "VP9", "AV1"]
            for keyword in video_keywords:
                if keyword.lower() in title.lower() or (description and keyword.lower() in description.lower()):
                    video_encode = keyword
                    break

            # 提取音频编码（从标题和描述中解析）
            audio_encode = "未知音频"
            audio_keywords = ["DTS", "DTS-HD", "DTS-X", "Dolby", "AC3", "AAC", "FLAC", "TrueHD", "Atmos", "DTS-HD MA"]
            for keyword in audio_keywords:
                if keyword.lower() in title.lower() or (description and keyword.lower() in description.lower()):
                    audio_encode = keyword
                    break

            # 提取资源类型（从标题和描述中解析）
            resource_type = "未知来源"
            type_keywords = ["BluRay", "Blu-ray", "WEB-DL", "WEBRip", "HDTV", "DVDRip", "BDRip", "Remux", "UHD"]
            for keyword in type_keywords:
                if keyword.lower() in title.lower() or (description and keyword.lower() in description.lower()):
                    resource_type = keyword
                    break

            # 提取制作组/字幕组（从标题中解析@后面的内容）
            resource_team = ""
            if "@" in title:
                import re
                team_match = re.search(r'@([^@\s]+)', title)
                if team_match:
                    resource_team = team_match.group(1)

            # 提取字幕信息
            subtitle_info = "无字幕信息"
            if description:
                subtitle_keywords = [
                    "中字", "中文字幕", "简体", "繁体",
                    "双语", "特效字幕", "SUP", "SRT", "ASS"
                ]
                subtitle_matches = []
                for keyword in subtitle_keywords:
                    if keyword in description:
                        subtitle_matches.append(keyword)

                if subtitle_matches:
                    subtitle_info = "、".join(subtitle_matches)

            # 提取音轨信息
            audio_info = "未知音轨"
            if description:
                audio_keywords = ["国语", "粤语", "英语", "双语", "多语", "国英双语", "中英双语"]
                audio_matches = []
                for keyword in audio_keywords:
                    if keyword in description:
                        audio_matches.append(keyword)

                if audio_matches:
                    audio_info = "、".join(audio_matches)

            # 格式化资源信息
            result_text += f"{i+1}. {title}\n"
            result_text += f"   大小: {size} | 分辨率: {resolution}\n"
            result_text += f"   做种: {seeders} | 下载: {peers} | 完成: {grabs}\n"

            # 添加描述信息
            if description:
                # 截取描述的前100个字符
                desc_preview = description[:100] + "..." if len(description) > 100 else description
                result_text += f"   描述: {desc_preview}\n"

            # 添加详细的编码和格式信息
            result_text += f"   视频编码: {video_encode} | 音频编码: {audio_encode}\n"
            result_text += f"   资源类型: {resource_type}"
            if resource_team:
                result_text += f" | 制作组: {resource_team}"
            result_text += "\n"
            result_text += f"   字幕: {subtitle_info} | 音轨: {audio_info}\n"

            if labels_str != "无标签":
                result_text += f"   质量标签: {labels_str}\n"

            # 免费信息和流量优惠
            free_info = []
            if freedate:
                free_info.append(f"免费至: {freedate}")
            if freedate_diff:
                free_info.append(f"剩余: {freedate_diff}")
            if volume_factor:
                free_info.append(f"流量: {volume_factor}")
            elif download_factor != 1.0 or upload_factor != 1.0:
                # 如果没有volume_factor但有具体的上传下载系数，显示详细信息
                factor_info = []
                if download_factor != 1.0:
                    factor_info.append(f"下载: {download_factor}x")
                if upload_factor != 1.0:
                    factor_info.append(f"上传: {upload_factor}x")
                if factor_info:
                    free_info.append(f"系数: {' '.join(factor_info)}")

            if free_info:
                result_text += f"   优惠: {' | '.join(free_info)}\n"

            if hit_and_run:
                result_text += "   H&R: 是\n"

            if imdbid:
                result_text += f"   IMDB: {imdbid}\n"

            if page_url:
                result_text += f"   详情页: {page_url}\n"

            # 生成资源标识符并缓存（注意：不暴露enclosure中的敏感信息）
            # 创建一个安全的资源信息副本，移除敏感字段
            safe_resource = resource.copy()
            # 移除包含passkey的下载链接
            safe_resource.pop("enclosure", None)
            # 移除其他可能包含敏感信息的字段
            safe_resource.pop("site_cookie", None)
            safe_resource.pop("site_ua", None)
            safe_resource.pop("site_proxy", None)

            resource_id = resource_cache.generate_resource_id(safe_resource)
            # 存储完整的资源信息（包含敏感信息）用于后续下载
            resource_cache.store_resource(resource_id, resource)

            result_text += f"   资源标识符: {resource_id}\n\n"

        return result_text

    async def _fuzzy_search_media_resources(self, arguments: dict) -> list[types.TextContent]:
        """
        模糊搜索媒体资源，不需要精确的媒体名称
        参数:
            - keyword: 电影名称关键词
            - page: 页码(可选)，默认为0
            - sites: 站点ID列表(可选)，多个站点ID用逗号分隔
            - detailed: 是否显示详细信息(可选)，默认为False
            - limit: 最大返回结果数量(可选)，默认为50
        """
        keyword = arguments.get("keyword")
        if not keyword:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供搜索关键词"
                )
            ]

        # 获取其他可选参数
        page = arguments.get("page", 0)
        sites = arguments.get("sites")
        detailed = arguments.get("detailed", False)

        # 强制要求提供sites参数
        if not sites:
            return [
                types.TextContent(
                    type="text",
                    text="错误：请提供sites参数，指定1-3个站点ID进行搜索，避免token超限。可通过get-sites工具获取站点列表。"
                )
            ]

        limit = int(arguments.get("limit", 50))  # 默认限制为10个结果

        try:
            logger.info(f"开始模糊搜索资源，关键词：{keyword}")

            # 构建请求参数
            params = {
                "keyword": keyword,
                "page": page
            }

            if sites:
                params["sites"] = sites

            # 调用模糊搜索API
            response = await self._make_request(
                method="GET",
                endpoint="/api/v1/search/title",
                params=params
            )

            # 检查是否有错误
            is_error_response = (
                isinstance(response, dict) and
                not response.get("success", False)
            )

            if is_error_response:
                error_msg = response.get("message", "未知错误")
                return [
                    types.TextContent(
                        type="text",
                        text=f"模糊搜索资源失败: {error_msg}"
                    )
                ]

            # 获取搜索结果
            torrents = response.get("data", [])

            # 使用公共方法格式化结果
            result_text = self._format_search_results(
                torrents, keyword, detailed=detailed, limit=limit)

            return [
                types.TextContent(
                    type="text",
                    text=result_text
                )
            ]

        except Exception as e:
            logger.error(f"模糊搜索资源时出错: {str(e)}")
            return [
                types.TextContent(
                    type="text",
                    text=f"模糊搜索资源时出错: {str(e)}"
                )
            ]

    async def _get_downloaders(
        self, _: dict = None
    ) -> list[types.TextContent]:
        """
        获取可用的下载器列表工具
        参数:
            - _: 工具参数（当前未使用）
        """
        try:
            # 获取下载器列表
            downloaders = await self._make_request(
                method="GET",
                endpoint="/api/v1/download/clients"
            )

            # 格式化下载器信息
            result_text = "可用的下载器列表：\n\n"

            if not downloaders:
                # 如果没有找到下载器，显示默认下载器
                result_text += "没有找到可用的下载器，使用默认下载器：\n\n"
            else:
                # 显示找到的下载器
                for i, downloader in enumerate(downloaders):
                    name = downloader.get("name", "未知")
                    type_name = downloader.get("type", "未知")
                    result_text += f"{i+1}. name: {name}, type: {type_name}\n"
            return [
                types.TextContent(
                    type="text",
                    text=result_text
                )
            ]

        except Exception as e:
            logger.error(f"获取下载器列表时出错: {str(e)}")
            return [
                types.TextContent(
                    type="text",
                    text=f"获取下载器列表时出错: {str(e)}"
                )
            ]

    @property
    def tool_info(self) -> list[types.Tool]:
        """返回工具的描述信息"""
        return [
            types.Tool(
                name="search-media-resources",
                description="通过keyword参数或mediaid参数搜索媒体资源，支持按名称、年份、清晰度等条件搜索，返回资源标识符。",
                inputSchema={
                    "type": "object",
                    "required": ["sites"],
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": "媒体名称关键词，与mediaid二选一"
                        },
                        "mediaid": {
                            "type": "string",
                            "description": "媒体ID，格式为'tmdb:123'或'douban:456'，与keyword二选一，优先使用mediaid"
                        },
                        "year": {
                            "type": "string",
                        },
                        "resolution": {
                            "type": "string",
                            "description": "期望的清晰度，如 1080p, 2160p, 4K 等"
                        },
                        "media_type": {
                            "type": "string",
                            "description": "媒体类型，默认为'电影'，可选'电视剧'"
                        },
                        "sites": {
                            "type": "string",
                            "description": "站点ID列表，多个站点ID用逗号分隔，是数字ID不是站点名称，若没有站点ID可以通过工具get-sites获取"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "最大返回结果数量，默认为50，设置为较小的值可以减少返回的资源数量"
                        }
                    },
                },
            ),
            types.Tool(
                name="fuzzy-search-media-resources",
                description="模糊搜索媒体资源，当精确搜索无法识别媒体信息时使用此工具，返回资源标识符。",
                inputSchema={
                    "type": "object",
                    "required": ["keyword", "sites"],
                    "properties": {
                        "keyword": {
                            "type": "string",
                        },
                        "page": {
                            "type": "integer",
                        },
                        "sites": {
                            "type": "string",
                            "description": "站点数字ID列表，多个站点ID用逗号分隔，可通过工具get-sites获取"
                        },
                        "detailed": {
                            "type": "boolean",
                            "description": "是否显示详细信息，默认为false"
                        },
                        "limit": {
                            "type": "integer",
                        }
                    },
                },
            ),
            types.Tool(
                name="search-site-resources",
                description="在指定站点直接搜索资源，使用关键词搜索，无需媒体ID，返回资源标识符。",
                inputSchema={
                    "type": "object",
                    "required": ["site_id", "keyword"],
                    "properties": {
                        "site_id": {
                            "type": "string",
                            "description": "站点ID，数字ID，可通过get-sites工具获取"
                        },
                        "keyword": {
                            "type": "string",
                            "description": "搜索关键词"
                        },
                        "cat": {
                            "type": "string",
                            "description": "资源分类代码：501=电影，502=剧集，503=纪录片，504=动画，505=综艺"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "最大返回结果数量，默认为50"
                        }
                    },
                },
            ),
            types.Tool(
                name="get-downloaders",
                description="获取可用的下载器列表",
                inputSchema={
                    "type": "object",
                    "properties": {},
                },
            ),
            types.Tool(
                name="download-torrent",
                description="通过资源下载链接或资源标识符下载资源。torrent_url和resource_id二选一",
                inputSchema={
                    "type": "object",
                    "required": ["media_type"],
                    "properties": {
                        "torrent_url": {
                            "type": "string",
                            "description": "资源下载链接"
                        },
                        "resource_id": {
                            "type": "string",
                            "description": "资源标识符"
                        },
                        "downloader": {
                            "type": "string",
                            "description": "下载器名称"
                        },
                        "save_path": {
                            "type": "string",
                            "description": "保存路径"
                        },
                        "media_type": {
                            "type": "string",
                            "description": "电影 or 电视剧"
                        }
                    },
                },
            )
        ]
