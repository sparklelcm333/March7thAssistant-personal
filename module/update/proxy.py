"""传输配置：更新下载的代理获取与规范化。

手动配置优先于系统代理；供 requests 下载（download.py）与遥测等外部复用。
"""

from __future__ import annotations

import re
import urllib.request
from urllib.parse import urlsplit, urlunsplit


_PROXY_SCHEME_RE = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.-]*://')


def normalize_proxy_url(proxy: str | None) -> str | None:
    """规范化代理地址，缺少协议时默认按 http 处理。"""
    if proxy is None:
        return None

    proxy = str(proxy).strip()
    if not proxy:
        return None

    if not _PROXY_SCHEME_RE.match(proxy):
        proxy = f'http://{proxy}'

    return proxy


def redact_proxy_url(proxy: str | None) -> str | None:
    """脱敏代理地址中的认证信息，避免日志输出凭据。"""
    if not proxy:
        return None

    parts = urlsplit(proxy)
    if parts.username is None:
        return proxy

    host = parts.hostname or ''
    if host and ':' in host and not host.startswith('['):
        host = f'[{host}]'
    if parts.port is not None:
        host = f'{host}:{parts.port}'

    userinfo = '***:***' if parts.password is not None else '***'
    netloc = f'{userinfo}@{host}' if host else userinfo
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def format_proxy_mapping(proxies: dict[str, str] | None) -> str | None:
    """将代理映射格式化为适合日志输出的文本（认证信息已脱敏）。"""
    if not proxies:
        return None

    return ', '.join(
        f'{scheme}={redact_proxy_url(proxy)}'
        for scheme, proxy in sorted(proxies.items())
    )


def get_manual_update_download_proxy() -> str | None:
    """获取手动配置的更新下载代理。"""
    from module.config import cfg

    return normalize_proxy_url(getattr(cfg, 'update_download_proxy', None))


def get_system_download_proxies() -> dict[str, str]:
    """获取并规范化系统代理配置（仅 http/https——requests/aiohttp 均不支持 ftp 代理）。"""
    raw_proxies = urllib.request.getproxies() or {}
    proxies: dict[str, str] = {}

    all_proxy = normalize_proxy_url(raw_proxies.get('all'))
    if all_proxy is not None:
        return {'http': all_proxy, 'https': all_proxy}

    for scheme in ('http', 'https'):
        proxy = normalize_proxy_url(raw_proxies.get(scheme))
        if proxy is not None:
            proxies[scheme] = proxy

    return proxies


def get_update_download_requests_proxies() -> dict[str, str] | None:
    """获取 requests 使用的更新下载代理，手动配置优先于系统代理。"""
    manual_proxy = get_manual_update_download_proxy()
    if manual_proxy is not None:
        return {'http': manual_proxy, 'https': manual_proxy}

    proxies = get_system_download_proxies()
    requests_proxies = {
        scheme: proxies[scheme] for scheme in ('http', 'https') if scheme in proxies
    }

    if 'http' not in requests_proxies and 'https' in requests_proxies:
        requests_proxies['http'] = requests_proxies['https']
    if 'https' not in requests_proxies and 'http' in requests_proxies:
        requests_proxies['https'] = requests_proxies['http']

    return requests_proxies or None


def get_update_requests_proxy_description() -> str | None:
    """获取 requests 更新流量使用的代理描述文本。"""
    manual_proxy = get_manual_update_download_proxy()
    if manual_proxy is not None:
        redacted = redact_proxy_url(manual_proxy)
        return f'手动代理: http={redacted}, https={redacted}'

    requests_proxies = get_update_download_requests_proxies()
    if not requests_proxies:
        return None

    mapping = format_proxy_mapping(requests_proxies)
    return f'系统代理: {mapping}' if mapping else None
