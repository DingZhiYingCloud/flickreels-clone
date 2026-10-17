# 项目URL配置
import re
from urllib.parse import quote

from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404, JsonResponse
from django.core.cache import cache

from Web.crawler.flickreels import FlickReelsCrawler, reward_copy, LIKE_COPY
from Web.utils import pick_download_url, stats_url


# ============ V2（手机端抖音式竖屏视频流） ============
# 手机 UA 访问首页渲染 V2，PC 端保持 V1；同一个 URL 两套页面，需 Vary: User-Agent。
V2_FEED_CACHE_TTL = 60 * 10
V2_EP1_CACHE_TTL = 60 * 5

MOBILE_UA_RE = re.compile(
    r'(iPhone|iPod|Android.+Mobile|Windows Phone|IEMobile|BlackBerry|Opera Mini)',
    re.I,
)

LOCALE_LANGS = {
    '': 'en-US', 'ja': 'ja-JP', 'ko': 'ko-KR', 'es': 'es-ES', 'id': 'id-ID',
    'de': 'de-DE', 'th': 'th-TH', 'tc': 'zh-TW', 'fr': 'fr-FR', 'pt': 'pt-BR',
}

# V2 文案（按钮文案复用 reward_copy 的"送钱"标题）
V2_COPY = {
    'en': {'hint': 'Watch all episodes in the APP', 'empty': 'No content yet, please retry later'},
    'tc': {'hint': '在 APP 內觀看全集', 'empty': '暫無內容，請稍後重試'},
    'ja': {'hint': 'アプリで全話視聴', 'empty': 'コンテンツがありません。後でもう一度お試しください'},
    'ko': {'hint': '앱에서 전체 회차 시청', 'empty': '콘텐츠가 없습니다. 잠시 후 다시 시도해 주세요'},
    'es': {'hint': 'Mira todos los episodios en la APP', 'empty': 'Sin contenido, inténtalo más tarde'},
    'id': {'hint': 'Tonton semua episode di APP', 'empty': 'Belum ada konten, coba lagi nanti'},
    'de': {'hint': 'Alle Folgen in der APP ansehen', 'empty': 'Noch keine Inhalte, bitte später erneut versuchen'},
    'th': {'hint': 'ดูทุกตอนได้ในแอป', 'empty': 'ยังไม่มีเนื้อหา โปรดลองใหม่ภายหลัง'},
    'fr': {'hint': "Regardez tous les épisodes dans l'APP", 'empty': 'Aucun contenu pour le moment, réessayez plus tard'},
    'pt': {'hint': 'Assista a todos os episódios no APP', 'empty': 'Sem conteúdo por enquanto, tente mais tarde'},
}


def is_mobile(request):
    """按 UA 判断是否为手机（iPad / Android 平板按桌面端处理）"""
    return bool(MOBILE_UA_RE.search(request.META.get('HTTP_USER_AGENT', '') or ''))


def index(request, locale=''):
    """首页：手机端 → V2 竖屏视频流；PC 端 → V1 静态首页"""
    if locale not in LOCALE_LANGS:
        locale = ''
    if is_mobile(request):
        return _render_v2(request, locale)
    template = f'locales/{locale}.html' if locale else 'index.html'
    resp = render(request, template, {})
    resp['Vary'] = 'User-Agent'
    return resp


def _feed_page(locale, page):
    """取一页视频流数据（每部剧的第 1 集）"""
    cache_key = f'v2feed:{locale}:{page}'
    data = cache.get(cache_key)
    if data is None:
        try:
            data = FlickReelsCrawler().fetch_feed(locale, page)
            cache.set(cache_key, data, V2_FEED_CACHE_TTL)
        except Exception:
            data = {'items': [], 'page': page, 'next': page + 1}
    return data


def _render_v2(request, locale=''):
    data = _feed_page(locale, 1)
    copy = V2_COPY.get(locale or 'en') or V2_COPY['en']
    resp = render(request, 'v2.html', {
        'items': data.get('items', []),
        'locale': locale,
        'html_lang': LOCALE_LANGS.get(locale, 'en-US'),
        'locale_prefix': f'/{locale}' if locale else '',
        'download_url': pick_download_url(),
        'stats_url': stats_url(),
        'v2_hint': copy['hint'],
        'v2_empty': copy['empty'],
        'like_hint': (LIKE_COPY.get(locale or 'en') or LIKE_COPY['en'])['hint'],
        'reward': reward_copy(locale),
        'next_page': data.get('next', 2),
    })
    resp['Vary'] = 'User-Agent'
    return resp


def api_feed(request):
    """V2 无限流接口：分页返回短剧列表（每部剧对应第 1 集）"""
    locale = request.GET.get('locale', '')
    if locale not in LOCALE_LANGS:
        locale = ''
    try:
        page = max(1, int(request.GET.get('page') or 1))
    except (TypeError, ValueError):
        page = 1
    data = _feed_page(locale, page)
    return JsonResponse({
        'items': data.get('items', []),
        'page': page,
        'next': data.get('next', page + 1),
    })


def api_ep1(request):
    """V2：按需解析某部剧第 1 集的 m3u8（前端懒加载 / 预取）"""
    locale = request.GET.get('locale', '')
    if locale not in LOCALE_LANGS:
        locale = ''
    slug = (request.GET.get('slug') or '').strip()
    try:
        drama_id = int(request.GET.get('id') or 0)
    except (TypeError, ValueError):
        drama_id = 0
    if not slug or drama_id <= 0:
        return JsonResponse({'hls': '', 'poster': '', 'title': ''}, status=400)
    cache_key = f'v2ep1:{locale}:{drama_id}'
    data = cache.get(cache_key)
    if data is None:
        try:
            data = FlickReelsCrawler().fetch_ep1_video(locale, slug, drama_id)
            cache.set(cache_key, data, V2_EP1_CACHE_TTL)
        except Exception:
            data = {'hls': '', 'poster': '', 'title': ''}
    return JsonResponse(data)


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
