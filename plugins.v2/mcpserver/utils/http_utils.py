import logging
import json
from typing import Optional, Dict, Any

# 尝试导入依赖，如果失败则使用模拟对象
HTTPX_AVAILABLE = False
ANYIO_AVAILABLE = False

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    # 创建httpx模拟对象
    class MockHttpx:
        class AsyncClient:
            def __init__(self, **kwargs):
                pass
            async def request(self, *args, **kwargs):
                raise RuntimeError("httpx未安装，无法发送HTTP请求")
            async def aclose(self):
                pass
        class HTTPStatusError(Exception):
            def __init__(self, message, request=None, response=None):
                super().__init__(message)
                self.response = response
        class RequestError(Exception):
            pass
    httpx = MockHttpx()

try:
    import anyio
    ANYIO_AVAILABLE = True
except ImportError:
    # 创建anyio模拟对象
    class MockAnyio:
        @staticmethod
        async def sleep(seconds):
            import asyncio
            await asyncio.sleep(seconds)
    anyio = MockAnyio()

logger = logging.getLogger(__name__)

# HTTP客户端管理
_http_client = None

# 配置


class Config:
    BASE_URL = "http://localhost:3001"  # 基础URL，不要在这里添加/api/v1前缀
    MAX_RETRIES = 3
    RETRY_DELAY = 1  # 基础重试延迟（秒）
    REQUEST_TIMEOUT = 600  # 请求超时时间（秒）

    def set_moviepilot_port(self, port: int):
        """设置MoviePilot端口号"""
        self.BASE_URL = f"http://localhost:{port}"
        logger.info(f"MoviePilot端口号已设置为: {port}, BASE_URL: {self.BASE_URL}")


config = Config()


def set_moviepilot_port(port: int):
    """设置MoviePilot端口号的全局函数"""
    config.set_moviepilot_port(port)


async def get_http_client():
    """获取或创建HTTP客户端"""
    global _http_client
    if _http_client is None:
        # 增加超时时间，避免长时间请求导致连接断开
        _http_client = httpx.AsyncClient(
            timeout=config.REQUEST_TIMEOUT
        )
    return _http_client


async def close_http_client():
    """关闭HTTP客户端"""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None


async def make_request(
    method: str,
    endpoint: str,
    access_token: Optional[str] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    retry_count: int = 0,
) -> Dict[str, Any]:
    """发送请求到MoviePilot API，支持重试机制

    Args:
        method: HTTP请求方法 (GET, POST, etc.)
        endpoint: API端点路径
        access_token: MoviePilot access token
        params: URL查询参数
        data: 表单数据
        json_data: JSON请求体
        retry_count: 当前重试次数

    Returns:
        Dict[str, Any]: API响应数据或错误信息
    """
    logger.debug(f"[make_request] 开始处理请求")
    logger.debug(f"[make_request] 方法: {method}")
    logger.debug(f"[make_request] 端点: {endpoint}")
    logger.debug(f"[make_request] 访问令牌: {'已提供' if access_token else '未提供'}")
    logger.debug(f"[make_request] 查询参数: {params}")
    logger.debug(f"[make_request] 表单数据: {data}")
    logger.debug(f"[make_request] JSON数据: {json_data}")
    logger.debug(f"[make_request] 重试次数: {retry_count}")
    logger.debug(f"[make_request] BASE_URL: {config.BASE_URL}")

    # 处理认证：支持 MoviePilot 登录 access token（Bearer）和 API 令牌（X-API-KEY）。
    headers = {}
    if access_token:
        if access_token.startswith("apikey:"):
            headers["X-API-KEY"] = access_token.removeprefix("apikey:")
            logger.debug("[make_request] 设置X-API-KEY头")
        else:
            headers["Authorization"] = f"Bearer {access_token}"
            logger.debug("[make_request] 设置Authorization头")
    else:
        logger.warning("[make_request] 未提供access_token，请求可能会失败")

    try:
        # 获取HTTP客户端
        logger.debug(f"[make_request] 获取HTTP客户端...")
        client = await get_http_client()
        url = f"{config.BASE_URL.rstrip('/')}{endpoint}"
        logger.debug(f"[make_request] 完整URL: {url}")

        # 记录请求信息
        logger.info(f"发送请求: {method} {url}")
        logger.debug(f"[make_request] 请求头: {headers}")
        if params:
            logger.info(f"查询参数: {params}")
        if json_data:
            logger.info(f"请求体: {json_data}")

        # 发送请求
        logger.debug(f"[make_request] 发送HTTP请求...")
        response = await client.request(
            method,
            url,
            params=params,
            data=data,
            json=json_data,
            headers=headers,
        )

        logger.debug(f"[make_request] 收到响应")
        logger.debug(f"[make_request] 响应状态码: {response.status_code}")
        logger.debug(f"[make_request] 响应头: {dict(response.headers)}")
        logger.debug(f"[make_request] 响应内容长度: {len(response.content) if response.content else 0}")

        response.raise_for_status()
        logger.debug(f"[make_request] 状态码检查通过")

        # 处理响应
        if not response.content:
            logger.debug(f"[make_request] 响应内容为空，返回空字典")
            return {}

        content_type = response.headers.get("content-type", "")
        logger.debug(f"[make_request] 响应内容类型: {content_type}")

        if "application/json" in content_type:
            try:
                logger.debug(f"[make_request] 解析JSON响应...")
                json_result = response.json()
                logger.debug(f"[make_request] JSON解析成功: {json_result}")
                return json_result
            except Exception as e:
                logger.error(f"[make_request] 解析JSON响应失败: {str(e)}")
                logger.debug(f"[make_request] 原始响应文本: {response.text}")
                return {"error": f"解析响应失败: {str(e)}", "content": response.text}

        logger.debug(f"[make_request] 返回文本响应")
        return {"content": response.text}

    except httpx.HTTPStatusError as e:
        # 处理HTTP错误
        error_content = e.response.text
        try:
            error_content = json.loads(e.response.text)
        except Exception:
            pass

        # 处理401错误（未授权）
        if e.response.status_code == 401 and retry_count < config.MAX_RETRIES:
            logger.warning(
                f"Token可能已过期 (重试 {retry_count + 1}/{config.MAX_RETRIES})"
            )
            await anyio.sleep(config.RETRY_DELAY * (retry_count + 1))
            return await make_request(
                method=method,
                endpoint=endpoint,
                access_token=access_token,
                params=params,
                data=data,
                json_data=json_data,
                retry_count=retry_count + 1
            )

        status_code = e.response.status_code
        reason = e.response.reason_phrase
        error_msg = f"HTTP {status_code}: {reason}"
        logger.error(f"请求失败: {error_msg}")
        return {
            "error": error_msg,
            "details": error_content
        }

    except httpx.RequestError as e:
        # 处理网络错误
        if retry_count < config.MAX_RETRIES:
            logger.warning(
                f"请求失败 (重试 {retry_count + 1}/{config.MAX_RETRIES}): {str(e)}"
            )
            await anyio.sleep(config.RETRY_DELAY * (retry_count + 1))
            return await make_request(
                method=method,
                endpoint=endpoint,
                access_token=access_token,
                params=params,
                data=data,
                json_data=json_data,
                retry_count=retry_count + 1
            )

        error_msg = f"网络错误: {str(e)}"
        logger.error(f"请求失败: {error_msg}")
        return {"error": error_msg}

    except Exception as e:
        logger.error(f"请求处理过程中发生错误: {str(e)}", exc_info=True)
        return {"error": f"系统错误: {str(e)}"}
