#!/usr/bin/env python3
"""Public read-only search plus a closed, private plugin subtitle protocol.

The native CLI alone owns OAuth. A loopback relay maps a single donor request
onto search, archive preview, or a download into plugin-controlled staging.
Provider locators enter the private protocol on stdin, never command arguments.
"""

import argparse
import contextlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEARCH_PATH = "/subs/v2/searchsub"
TRANSPORT_PATH = "/zvideo/search/local"
USERINFO_PATH = "/account/oauth2/userinfo"


class ExtensionError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        raise ExtensionError("E_PARAM", "字幕搜索参数无效；请使用 --params '{\"q\":\"片名或媒体ID\"}'")


def parse_search(args):
    """Return None for unchanged legacy commands; fail closed on new inputs."""
    value_options = {"--profile", "--timeout", "--host", "--mode", "--credential-store", "--local-root"}
    pos = 0
    while pos < len(args) and args[pos].startswith("-"):
        flag = args[pos].split("=", 1)[0]
        if flag in value_options:
            pos += 1 if "=" in args[pos] else 2
        elif flag == "--clear-host":
            pos += 1
        else:
            return None
    command = args[pos:]
    named = command[:2] == ["media", "subtitle-search"]
    raw = len(command) >= 3 and command[0] == "raw" and command[2] == SEARCH_PATH
    if not (named or raw):
        return None
    if raw and command[1] != "POST":
        raise ExtensionError("E_POLICY", "字幕搜索只允许 POST /subs/v2/searchsub")
    parser = SafeParser(add_help=False)
    parser.add_argument("--profile", default="default")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--params", required=True)
    parser.add_argument("--summary", action="store_true")
    parser.add_argument("--dedicated-profile", action="store_true")
    options = parser.parse_args(args[:pos] + command[2 if named else 3:])
    import re
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", options.profile):
        raise ExtensionError("E_PARAM", "profile 名称无效")
    if not 2 <= options.timeout <= 300:
        raise ExtensionError("E_PARAM", "timeout 必须在 2 到 300 秒之间")
    try:
        params = json.loads(options.params)
    except (ValueError, TypeError):
        raise ExtensionError("E_PARAM", "params 必须是 JSON 对象") from None
    if not isinstance(params, dict) or set(params) != {"q"}:
        raise ExtensionError("E_POLICY", "字幕搜索仅接受 q 参数")
    query = params["q"]
    if not isinstance(query, str) or not query.strip() or len(query) > 200 or any(ord(c) < 32 for c in query):
        raise ExtensionError("E_PARAM", "q 必须是 1 到 200 字符的搜索词")
    options.query = query.strip()
    if options.dedicated_profile and options.profile != "zvideohelper":
        raise ExtensionError("E_POLICY", "专用模式仅允许 zvideohelper profile")
    return options


def validate_upstream(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ExtensionError("E_POLICY", "字幕扩展需要已验证的局域网 NAS 地址")
    try:
        ip = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        raise ExtensionError("E_POLICY", "字幕扩展仅连接局域网 IP 地址") from None
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    private_networks = [ipaddress.ip_network(value) for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")]
    if not any(ip.version == network.version and ip in network for network in private_networks):
        raise ExtensionError("E_POLICY", "字幕扩展拒绝非局域网 NAS 地址")
    if parsed.port not in {None, 5055}:
        raise ExtensionError("E_POLICY", "字幕扩展只连接 NAS 的 5055 端口")
    return url.rstrip("/")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_handler(upstream, query, timeout, route_log, operation_path=SEARCH_PATH, operation_params=None):
    class RelayHandler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Request paths, headers and bodies must never enter logs.

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            path = urllib.parse.urlsplit(self.path)
            target = path.path
            is_search = target == TRANSPORT_PATH and self.command == "POST" and not path.query
            is_userinfo = target == USERINFO_PATH and self.command in {"GET", "POST"}
            if not (is_search or is_userinfo):
                self.send_error(403, "Route not allowed")
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 65536:
                    raise ValueError()
                body = self.rfile.read(length)
                if is_search:
                    values = urllib.parse.parse_qs(body.decode("utf-8"), strict_parsing=True)
                    if values != {"q": [query]}:
                        raise ValueError()
                    target = operation_path
                    if operation_params is not None:
                        body = urllib.parse.urlencode(operation_params).encode()
                elif path.query:
                    target += "?" + path.query
            except (ValueError, UnicodeError):
                self.send_error(400, "Invalid request")
                return
            headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "connection", "content-length", "transfer-encoding", "proxy-authorization"}}
            request = urllib.request.Request(upstream + target, data=body if self.command == "POST" else None, headers=headers, method=self.command)
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirects())
            try:
                response = opener.open(request, timeout=timeout)
            except urllib.error.HTTPError as error:
                response = error
            except Exception:
                self.send_error(502, "NAS request failed")
                return
            with response:
                payload = response.read(16 * 1024 * 1024 + 1)
                if len(payload) > 16 * 1024 * 1024:
                    self.send_error(502, "NAS response too large")
                    return
                route_log.append({"method": self.command, "path": target.split("?", 1)[0], "http": response.code})
                self.send_response(response.code)
                self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

    return RelayHandler


@contextlib.contextmanager
def relay(upstream, query, timeout, route_log, operation_path=SEARCH_PATH, operation_params=None):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(upstream, query, timeout, route_log, operation_path, operation_params))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "http://127.0.0.1:%d" % server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def cli_json(command, timeout, env=None):
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise ExtensionError("E_NETWORK", "字幕接口请求超时") from None
    try:
        document = json.loads(result.stdout if result.returncode == 0 else result.stderr)
    except ValueError:
        raise ExtensionError("E_API", "原 CLI 未返回可解析的 JSON") from None
    if not isinstance(document, dict):
        raise ExtensionError("E_API", "原 CLI 返回结构无效")
    return result.returncode, document


def search(binary, options):
    if options.dedicated_profile:
        return dedicated_search(binary, options)
    # Only the existing executable accesses Keychain and refresh credentials.
    code, doctor = cli_json([binary, "--profile", options.profile, "--timeout", str(options.timeout), "doctor"], options.timeout + 25)
    if code or not doctor.get("ok"):
        return code or 1, doctor
    transport = doctor.get("data", {}).get("transport", {})
    if transport.get("kind") != "lan":
        raise ExtensionError("E_POLICY", "当前扩展只验证了局域网模式；需要 NAS 在局域网可达")
    upstream = validate_upstream(transport.get("base_url", ""))
    route_log = []
    with tempfile.TemporaryDirectory(prefix="zspace-subtitle-") as isolated_home:
        env = dict(os.environ, ZSPACE_CLI_HOME=isolated_home)
        with relay(upstream, options.query, options.timeout, route_log) as local_url:
            command = [binary, "--profile", options.profile, "--timeout", str(options.timeout), "--credential-store", "keyring", "--host", local_url, "--mode", "lan", "raw", "POST", TRANSPORT_PATH, "--params", json.dumps({"q": options.query}, ensure_ascii=False)]
            code, result = cli_json(command, options.timeout * 3 + 25, env)
    if code == 0 and result.get("ok") and not any(entry["path"] == SEARCH_PATH for entry in route_log):
        raise ExtensionError("E_API", "未观察到实际字幕搜索请求，不能报告成功")
    result["extension"] = {"name": "subtitle-search", "read_only": True, "transport": "original-cli-oauth-lan", "requests": route_log}
    return code, result


def dedicated_search(binary, options):
    """Use only the plugin-owned NAS profile; the native CLI owns credentials.

    Linux file credentials stay in their original profile. Connection overrides
    are serialized and reset on entry and exit, including recovery after an
    interrupted previous search. No credential files are read or copied here.
    """
    import fcntl
    cli_home = os.environ.get("ZSPACE_CLI_HOME")
    if not cli_home:
        raise ExtensionError("E_POLICY", "专用模式需要独立的 CLI 数据目录")
    lock_path = Path(cli_home) / "subtitle-search.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with os.fdopen(os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        base = [binary, "--profile", "zvideohelper", "--timeout", str(options.timeout)]
        code, doctor = cli_json(base + ["--clear-host", "--mode", "auto", "doctor"], options.timeout + 25)
        if code or not doctor.get("ok"):
            return code or 1, doctor
        transport = doctor.get("data", {}).get("transport", {})
        if transport.get("kind") != "lan":
            raise ExtensionError("E_POLICY", "字幕搜索需要 NAS 局域网连接")
        upstream = validate_upstream(transport.get("base_url", ""))
        route_log = []
        try:
            with relay(upstream, options.query, options.timeout, route_log, getattr(options, "operation_path", SEARCH_PATH), getattr(options, "operation_params", None)) as local_url:
                code, result = cli_json(base + ["--host", local_url, "--mode", "lan", "raw", "POST", TRANSPORT_PATH, "--params", json.dumps({"q": options.query}, ensure_ascii=False)], options.timeout * 3 + 25)
        finally:
            reset_code, reset = cli_json(base + ["--clear-host", "--mode", "auto", "status"], 15)
            if reset_code or not reset.get("ok"):
                raise ExtensionError("E_IO", "字幕授权环境连接配置恢复失败，请重新检查授权状态")
        if code == 0 and result.get("ok") and not any(item["path"] == getattr(options, "operation_path", SEARCH_PATH) for item in route_log):
            raise ExtensionError("E_API", "未观察到实际字幕搜索请求")
        result["extension"] = {"name": "subtitle-search" if getattr(options,"operation_path",SEARCH_PATH) == SEARCH_PATH else "nas-subtitle", "read_only": getattr(options,"operation_path",SEARCH_PATH) != "/subs/v2/downloadsub", "transport": "native-cli-oauth-lan", "requests": route_log}
        return code, result


def summarize(result):
    summary = {k: result[k] for k in ("ok", "profile", "error", "extension") if k in result}
    data = result.get("data", {})
    if isinstance(data, dict):
        groups = data.get("subs", [])
        movies = []
        if isinstance(groups, list):
            for group in groups:
                if not isinstance(group, dict):
                    continue
                candidates = group.get("subs", [])
                if not isinstance(candidates, list):
                    continue
                movies.append({"name": group.get("name"), "douban_id": group.get("dbid"), "imdb_id": group.get("imdb"), "count": len(candidates), "sample": [{"title": item.get("sub_title"), "id": item.get("sub_id"), "has_download_url": bool(item.get("download_url"))} for item in candidates[:3] if isinstance(item, dict)]})
        summary["data"] = {"keys": list(data), "movies": movies, "candidate_count": sum(item["count"] for item in movies)}
    return summary


def main():
    if len(sys.argv) < 3 or sys.argv[1] != "--original-bin":
        raise ExtensionError("E_INSTALL", "缺少原 CLI 程序路径")
    binary = str(Path(sys.argv[2]).resolve())
    args = sys.argv[3:]
    if args[:1] == ["nas-subtitle-request"]:
        # Private plugin protocol. Provider locators arrive on stdin, never argv.
        operations = {"search": (SEARCH_PATH, {"q"}), "preview": ("/subs/v2/preview", {"sub_id", "download_url"}),
                      "download": ("/subs/v2/downloadsub", {"sub_id", "download_url", "sub_title", "file_name", "encrypted_path", "from"})}
        if len(args) != 2 or args[1] not in operations:
            raise ExtensionError("E_POLICY", "不支持的字幕操作")
        path, fields = operations[args[1]]
        try:
            params = json.loads(sys.stdin.read(65537))
        except ValueError:
            raise ExtensionError("E_PARAM", "字幕请求无效") from None
        if not isinstance(params, dict) or set(params) != fields or any(not isinstance(v, str) or len(v) > 8192 for v in params.values()):
            raise ExtensionError("E_POLICY", "字幕参数无效")
        if args[1] != "search" and (not params["sub_id"] or not params["download_url"].startswith("https://")):
            raise ExtensionError("E_POLICY", "字幕来源无效")
        if args[1] == "download" and (Path(params["sub_title"]).suffix.lower() not in {".srt", ".ass", ".ssa", ".vtt"} or params["encrypted_path"]):
            raise ExtensionError("E_POLICY", "仅支持文本字幕")
        options = argparse.Namespace(dedicated_profile=True, profile="zvideohelper", timeout=35, query="zvideohelper", summary=False,
                                     operation_path=path, operation_params=params)
    else:
        options = parse_search(args)
    if options is None:
        os.execv(binary, [binary] + args)
    code, result = search(binary, options)
    print(json.dumps(summarize(result) if options.summary else result, ensure_ascii=False), file=sys.stdout if code == 0 else sys.stderr)
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except ExtensionError as error:
        print(json.dumps({"ok": False, "error": {"code": error.code, "message": str(error)}}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2 if error.code == "E_PARAM" else 1)
