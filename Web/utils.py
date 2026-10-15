# -*- coding: utf-8 -*-
"""统一下载链接 / 数据统计埋点

地址统一维护在项目根目录的 test.txt 里（其它文字行会被忽略），例如：

    ✅ 处理完成：xxxx
    🔗 下载链接：
    https://aaa.domain-a.com/XXXX
    https://bbb.domain-b.com/XXXX
    📊 安装数据统计：
    https://apkstats.com/c.php?id=XXXX

- 不含 apkstats 域名的 http(s) 地址 = 下载链接（全站按次随机挑一个使用）
- 含 apkstats 域名的地址 = 数据统计埋点地址
"""
import os
import random

from django.conf import settings

# 地址文件（项目根目录）
LINKS_FILE = os.path.join(str(settings.BASE_DIR), 'test.txt')

# 用于区分"统计埋点"与"下载链接"的域名关键字
STATS_HOST_KEYWORD = 'apkstats.com'

# 兜底：文件缺失或解析不到下载链接时使用
FALLBACK_DOWNLOAD_URL = 'https://example.com/app-download'

_cache = {'mtime': None, 'download': [], 'stats': ''}


def _read_links():
    """读取 test.txt（按文件修改时间做缓存，避免每次请求都读盘）"""
    try:
        mtime = os.path.getmtime(LINKS_FILE)
    except OSError:
        mtime = None
    if mtime is not None and _cache['mtime'] == mtime:
        return _cache['download'], _cache['stats']

    download, stats = [], ''
    if mtime is not None:
        try:
            with open(LINKS_FILE, encoding='utf-8') as f:
                for raw in f:
                    line = raw.strip()
                    if not line.startswith(('http://', 'https://')):
                        continue
                    url = line.split()[0].strip().strip('，,、;；')
                    if STATS_HOST_KEYWORD in url:
                        stats = url
                    else:
                        download.append(url)
        except OSError:
            pass

    _cache.update(mtime=mtime, download=download, stats=stats)
    return download, stats


def download_urls():
    """test.txt 中的全部下载链接"""
    return list(_read_links()[0])


def pick_download_url():
    """随机挑一个下载链接（每次页面渲染随机取一个，用于全站统一下载入口）"""
    urls = _read_links()[0]
    return random.choice(urls) if urls else FALLBACK_DOWNLOAD_URL


def stats_url():
    """数据统计（安装统计）埋点地址，没有配置时返回空串"""
    return _read_links()[1]
