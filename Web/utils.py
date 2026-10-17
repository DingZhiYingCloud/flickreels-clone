# -*- coding: utf-8 -*-
"""统一下载链接 / 数据统计的读取入口

真正的地址配置在 Web/download_links.py：
- GLOBAL_URL：全局默认下载链接
- BY_LOCALE：按语言单独指定的下载链接（未配置的语言回退到 GLOBAL_URL）
"""
from Web import download_links


def pick_download_url(locale=''):
    """该语言应使用的下载链接（语言单独配置 > 全局默认）"""
    return download_links.app_download_url(locale)


def download_urls():
    """当前可用的下载链接（全局 + 各语言配置，去重）"""
    urls = [download_links.GLOBAL_URL] + list(download_links.BY_LOCALE.values())
    return [u for u in dict.fromkeys(urls) if u]


def stats_url():
    """数据统计埋点地址（未配置返回空串）"""
    return download_links.stats_url()
