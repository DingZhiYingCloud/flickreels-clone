# 项目URL配置
import re
from urllib.parse import quote

from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404
from django.core.cache import cache

from Web.crawler.flickreels import FlickReelsCrawler





# 服务类名


def index(request):
    # 调用爬虫获取首页三大板块数据；抓取失败时降级为空数据，保证页面可访问
    try:
        data = {}# 服务类名
    except Exception:
        data = {} # 失败处理
    return render(request, 'index.html', data)


def error_404(request, exception=None):
    """404 错误页：访问不存在的路径或文件时返回（DEBUG=False 时生效）"""
    return render(request, '404.html', status=404)


def error_500(request, exception=None):
    """500 错误页：服务器内部错误时返回（DEBUG=False 时生效）"""
    return render(request, '500.html', status=500)


# ============ 短剧播放页 ============
# 数据动态抓取自源站播放页（标题/面包屑/标签/剧情/剧集列表/视频地址）。
# 源站视频地址为带时效签名的 m3u8（约 2 小时过期），故做短时缓存（5 分钟），
# 既减少抓取频次，又能保证播放地址不失效。
PLAY_CACHE_TTL = 60 * 5


def play(request, slug, drama_id, episode, locale=''):
    """短剧播放页：动态抓取源站内容并渲染"""
    cache_key = f'play:{locale}:{slug}:{drama_id}:{episode}'
    data = cache.get(cache_key)
    if data is None:
        try:
            data = FlickReelsCrawler().fetch_play(locale, slug, drama_id, episode)
            cache.set(cache_key, data, PLAY_CACHE_TTL)
        except Exception:
            # 抓取失败时降级，保证页面仍可访问
            data = {
                'title': '播放页 - 内容加载失败',
                'html_lang': 'zh-CN',
                'description': '',
                'og_title': '', 'og_description': '', 'og_image': '',
                'hls_url': '', 'poster': '',
                'body_html': '<div style="padding:40px;text-align:center;color:#979797">'
                             '内容加载失败，请稍后重试</div>',
            }
    return render(request, 'play.html', data)


# ============ 短剧详情页 / 剧集列表页的重定向 ============
# 源站每个短剧有独立的 /movie/<slug>-<id>（详情）与 /episodes-list/<slug>-<id>（剧集列表）页面；
# 本站没有这两个页面，统一 301 到该剧第 1 集播放页（播放页本身已含剧集列表），
# 避免首页/列表页/轮播卡片里大量此类链接点进去 404。


def drama_detail(request, slug_id, locale=''):
    """把 /movie|/episodes-list/<slug>-<id> 301 跳转到 /playlist/<slug>/<id>/episode-1"""
    m = re.match(r'^(?P<slug>.+)-(?P<drama_id>\d+)$', slug_id or '')
    if not m:
        raise Http404('无效的短剧详情地址')
    prefix = f'/{locale}' if locale else ''
    target = f'{prefix}/playlist/{quote(m.group("slug"))}/{m.group("drama_id")}/episode-1'
    return redirect(target, permanent=True)


# ============ 短剧浏览页 ============
# 数据动态抓取自源站浏览页（分类标签 / 短剧列表 / 分页），短时缓存 5 分钟。
CLASSIFY_CACHE_TTL = 60 * 5


def classify(request, rest='', locale=''):
    """短剧浏览页：动态抓取源站内容并渲染（全部短剧 / 按分类筛选）"""
    cache_key = f'classify:{locale}:{rest}'
    data = cache.get(cache_key)
    if data is None:
        try:
            data = FlickReelsCrawler().fetch_classify(locale, rest)
            cache.set(cache_key, data, CLASSIFY_CACHE_TTL)
        except Exception:
            data = {
                'title': '浏览页 - 内容加载失败',
                'html_lang': 'zh-CN',
                'description': '', 'og_title': '', 'og_description': '', 'og_image': '',
                'body_html': '<div style="padding:40px;text-align:center;color:#979797">'
                             '内容加载失败，请稍后重试</div>',
            }
    return render(request, 'classify.html', data)


# ============ App 下载页 ============
# 数据动态抓取自源站 App 页；其中二维码与其说明会被替换为统一下载按钮。
APP_CACHE_TTL = 60 * 30


def app(request, locale=''):
    """App 下载页：动态抓取源站内容并渲染"""
    cache_key = f'app:{locale}'
    data = cache.get(cache_key)
    if data is None:
        try:
            data = FlickReelsCrawler().fetch_app(locale)
            cache.set(cache_key, data, APP_CACHE_TTL)
        except Exception:
            data = {
                'title': 'App 下载页 - 内容加载失败',
                'html_lang': 'zh-CN',
                'description': '', 'og_title': '', 'og_description': '', 'og_image': '',
                'body_html': '<div style="padding:40px;text-align:center;color:#979797">'
                             '内容加载失败，请稍后重试</div>',
            }
    return render(request, 'app.html', data)


# ============ 搜索页 ============
# 数据动态抓取自源站搜索页；关键词通过 drama 查询参数传入（与源站一致）。
SEARCH_CACHE_TTL = 60 * 10


def search(request, locale=''):
    """搜索短剧页：动态抓取源站搜索结果并渲染"""
    drama = (request.GET.get('drama') or '').strip()
    cache_key = f'search:{locale}:{drama}'
    data = cache.get(cache_key)
    if data is None:
        try:
            data = FlickReelsCrawler().fetch_search(locale, drama)
            cache.set(cache_key, data, SEARCH_CACHE_TTL)
        except Exception:
            data = {
                'title': '搜索 - 内容加载失败',
                'html_lang': 'zh-CN',
                'description': '', 'og_title': '', 'og_description': '', 'og_image': '',
                'body_html': '<div style="padding:40px;text-align:center;color:#979797">'
                             '内容加载失败，请稍后重试</div>',
            }
    return render(request, 'search.html', data)


# ============ More 专题页 ============
# 首页各板块（Hot Picks / 7-Day Star ...）右侧 "More" 的落地页，动态抓取源站内容。
MORE_CACHE_TTL = 60 * 10


def more(request, slug, section_id, page=1, locale=''):
    """More 专题页：动态抓取源站板块落地页并渲染（支持分页）"""
    page = max(1, int(page))
    cache_key = f'more:{locale}:{slug}:{section_id}:{page}'
    data = cache.get(cache_key)
    if data is None:
        try:
            data = FlickReelsCrawler().fetch_more(locale, slug, section_id, page)
            cache.set(cache_key, data, MORE_CACHE_TTL)
        except Exception:
            data = {
                'title': 'More - 内容加载失败',
                'html_lang': 'zh-CN',
                'description': '', 'og_title': '', 'og_description': '', 'og_image': '',
                'body_html': '<div style="padding:40px;text-align:center;color:#979797">'
                             '内容加载失败，请稍后重试</div>',
            }
    return render(request, 'more.html', data)


# ============ Sitemap（站点地图） ============
# 站点内容由爬虫实时获取，因此 sitemap 分为两部分：
#   1. 静态固定 URL：单（与 index.html 硬编码xxxx保持一致，改动需同步）
#   2. 动态 URL：调用爬虫抓取首页，提取xxxx生成详情页链接（爬虫失败时自动降级为仅静态 URL）
# 生成结果缓存 6 小时，避免每次请求 sitemap 都触发源站爬虫。
SITEMAP_STATIC_URLS = [
]
SITEMAP_CACHE_KEY = 'sitemap_urls'
SITEMAP_CACHE_TTL = 60 * 60 * 6  # 6 小时


def sitemap(request):
    """sitemap.xml：静态 URL + 爬虫实时xxxx详情 URL，缓存 6 小时"""

    return HttpResponse('\n', content_type='application/xml')
