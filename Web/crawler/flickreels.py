# -*- coding: utf-8 -*-
"""FlickReels 站点爬虫

职责：动态抓取源站页面并解析为结构化数据，供视图渲染。
当前支持：
    - 短剧播放页 (playlist episode page)

说明：
    1. 源站的视频地址（m3u8）带有时效签名（约 2 小时过期），因此每次请求都重新
       抓取（视图侧做 5 分钟短缓存），保证播放地址始终有效。
    2. "锁定集数"（需要下载 App 才能观看）时，源站 SSR 会输出一个提示遮罩，里面是
       提示文案 + 二维码（img）+ 品牌徽标。本爬虫会把二维码与徽标替换为"下载 App"
       按钮；按钮地址使用占位符 __APP_DOWNLOAD_URL__，由模板渲染时替换为母版
       template.html 中定义的统一下载链接。
"""
import hashlib
import os
import re
from urllib.parse import quote

import requests
from lxml import html as LH, etree

# 统一下载链接占位符：模板渲染时会被替换为 {{ app_download_url }}
APP_URL_PLACEHOLDER = '__APP_DOWNLOAD_URL__'

# "下载 App"按钮文案（按语言）。可自行调整。
APP_DOWNLOAD_LABEL = {
    'en': 'Download APP',
    'tc': '下載APP',
    'ja': 'アプリをダウンロード',
    'ko': '앱 다운로드',
    'es': 'Descargar APP',
    'id': 'Unduh APP',
    'de': 'APP herunterladen',
    'th': 'ดาวน์โหลดแอป',
    'fr': "Télécharger l'APP",
    'pt': 'Baixar APP',
}

# ============================================================
# 「下载/看剧送钱」促销文案（按语言）
# 奖励基准：4000 卢比（印度），按汇率换算为各语言对应货币（近似值，可直接改）。
# 三处共用：播放页顶部横幅、App 页顶部横幅、播放页"下载弹框"（锁定遮罩）标题。
# ============================================================
REWARD_COPY = {
    'en': {'amount': '$48',       'title': 'Download & Get {amount} Free!',
           'sub': 'Watch short dramas and earn money',      'cta': 'Download Now'},
    'tc': {'amount': 'NT$1,500',  'title': '下載即送 {amount}！',
           'sub': '看短劇還能領現金',                        'cta': '立即下載'},
    'ja': {'amount': '7,000円',   'title': 'ダウンロードで{amount}プレゼント！',
           'sub': '短編ドラマを見て稼ごう',                  'cta': '今すぐダウンロード'},
    'ko': {'amount': '65,000원',  'title': '다운로드하면 {amount} 지급!',
           'sub': '숏드라마 보며 용돈 벌기',                 'cta': '지금 다운로드'},
    'es': {'amount': '45 €',      'title': '¡Descarga y recibe {amount} gratis!',
           'sub': 'Gana dinero viendo series cortas',       'cta': 'Descargar ahora'},
    'id': {'amount': 'Rp760.000', 'title': 'Unduh dan dapat {amount} gratis!',
           'sub': 'Nonton drama pendek sambil dapat uang',  'cta': 'Unduh Sekarang'},
    'de': {'amount': '45 €',      'title': 'Herunterladen und {amount} gratis!',
           'sub': 'Geld verdienen mit Kurzdramen',          'cta': 'Jetzt herunterladen'},
    'th': {'amount': '฿1,700',    'title': 'ดาวน์โหลดรับ {amount} ฟรี!',
           'sub': 'ดูซีรีส์สั้นแล้วรับเงิน',                   'cta': 'ดาวน์โหลดเลย'},
    'fr': {'amount': '45 €',      'title': 'Téléchargez et recevez {amount} offerts !',
           'sub': "Gagnez de l'argent en regardant des séries", 'cta': 'Télécharger'},
    'pt': {'amount': 'R$260',     'title': 'Baixe e ganhe {amount} grátis!',
           'sub': 'Ganhe dinheiro assistindo dramas',       'cta': 'Baixar agora'},
}


def reward_copy(locale=''):
    """返回该语言的促销文案（标题中的 {amount} 已替换为对应货币金额）"""
    data = REWARD_COPY.get(locale or 'en') or REWARD_COPY['en']
    amount = data['amount']
    return {
        'amount': amount,
        'title': data['title'].format(amount=amount),
        'sub': data['sub'],
        'cta': data['cta'],
    }


# ============================================================
# 「点赞」文案（按语言）
# 播放页播放器右上角显示点赞按钮，点赞数由剧集 id 派生（1 万 ~ 100 万）；
# 点击点赞会弹出"需先下载 APP"的提示，引导下载。
# ============================================================
LIKE_COPY = {
    'en': {'hint': 'Please download the APP to like this episode', 'cta': 'Download APP'},
    'tc': {'hint': '需要先下載 APP 才能點讚', 'cta': '下載APP'},
    'ja': {'hint': 'いいねするにはアプリのダウンロードが必要です', 'cta': 'アプリをダウンロード'},
    'ko': {'hint': '좋아요를 누르려면 앱을 먼저 다운로드해야 합니다', 'cta': '앱 다운로드'},
    'es': {'hint': 'Descarga la APP para dar me gusta a este episodio', 'cta': 'Descargar APP'},
    'id': {'hint': 'Unduh APP untuk menyukai episode ini', 'cta': 'Unduh APP'},
    'de': {'hint': 'Bitte lade die APP herunter, um zu liken', 'cta': 'APP herunterladen'},
    'th': {'hint': 'ต้องดาวน์โหลดแอปก่อนจึงจะกดถูกใจได้', 'cta': 'ดาวน์โหลดแอป'},
    'fr': {'hint': "Téléchargez l'APP pour aimer cet épisode", 'cta': "Télécharger l'APP"},
    'pt': {'hint': 'Baixe o APP para curtir este episódio', 'cta': 'Baixar APP'},
}


def like_count(drama_id):
    """点赞数：由剧集 id 派生（同一部剧显示恒定），范围 1 万 ~ 100 万"""
    h = int(hashlib.md5(f'flickreels-like-{int(drama_id)}'.encode()).hexdigest(), 16)
    return 10000 + h % (1000000 - 10000 + 1)


# ============================================================
# 免费集数策略：只有前 FREE_EPISODES 集对外开放，
# 第 FREE_EPISODES+1 集起一律锁定（不下发播放地址，提示下载 App）。
# 想调整免费集数，只改这一个数字即可。
# ============================================================
FREE_EPISODES = 1

# 锁定集提示文案（按语言）
LOCK_HINT = {
    'en': 'Please download the APP to watch this episode',
    'tc': '需要下載 APP 才能觀看這集',
    'ja': 'このエピソードを見るにはアプリのダウンロードが必要です',
    'ko': '이 에피소드를 보려면 앱을 다운로드해야 합니다',
    'es': 'Descarga la APP para ver este episodio',
    'id': 'Unduh APP untuk menonton episode ini',
    'de': 'Bitte lade die APP herunter, um diese Episode anzusehen',
    'th': 'ต้องดาวน์โหลดแอปก่อนจึงจะดูตอนนี้ได้',
    'fr': "Téléchargez l'APP pour regarder cet épisode",
    'pt': 'Baixe o APP para assistir a este episódio',
}


class FlickReelsCrawler:
    """FlickReels 内容爬虫"""

    BASE = 'https://www.flickreels.net'
    HEADERS = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                       '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'),
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
    }

    def __init__(self, timeout=15):
        self.timeout = timeout

    # ------------------------------------------------------------------ 基础
    def get(self, path):
        """按路径或完整 URL 发起 GET，返回响应文本"""
        url = path if path.startswith('http') else self.BASE + path
        resp = requests.get(url, headers=self.HEADERS, timeout=self.timeout)
        resp.raise_for_status()
        return resp.text

    # ------------------------------------------------------------ 播放页解析
    @staticmethod
    def build_play_path(locale, slug, drama_id, episode):
        """拼装源站播放页路径，如 /tc/playlist/<slug>/11796/episode-1"""
        prefix = f'/{locale}' if locale else ''
        return f'{prefix}/playlist/{quote(slug)}/{int(drama_id)}/episode-{int(episode)}'

    def fetch_play(self, locale, slug, drama_id, episode):
        """抓取并解析播放页"""
        raw = self.get(self.build_play_path(locale, slug, drama_id, episode))
        return self.parse_play(raw, locale, drama_id, episode)

    def parse_play(self, raw, locale='', drama_id=None, episode=None):
        """把播放页 HTML 解析为渲染所需的数据字典"""
        doc = LH.fromstring(raw)

        title = (doc.findtext('.//title') or '').strip()
        html_lang = self._meta_html_lang(raw) or 'zh-CN'
        description = self._meta(doc, name='description')
        og_title = self._meta(doc, prop='og:title') or title
        og_description = self._meta(doc, prop='og:description') or description
        og_image = self._meta(doc, prop='og:image')
        hls_url = self._extract_hls(raw)
        poster = self._extract_poster(doc)
        # 锁定判定：默认只放开前 FREE_EPISODES 集，其余强制锁定（引导下载 App）；
        # 源站本身不提供播放地址的集数同样锁定。
        over_free = episode is not None and int(episode) > FREE_EPISODES
        locked = over_free or (not hls_url)
        if locked:
            hls_url = ''  # 锁定集不下发播放地址，避免被绕过

        self._clean(doc, hls_url, locked, locale, poster=poster)
        self._inject_banner(doc, locale)
        self._inject_like(doc, locale, drama_id)

        body = doc.body
        if body is None:
            raise ValueError('播放页缺少 body')
        inner = LH.tostring(body, encoding='unicode')
        inner = re.sub(r'^\s*<body[^>]*>', '', inner)
        inner = re.sub(r'</body>\s*$', '', inner)

        return {
            'title': title,
            'html_lang': html_lang,
            'description': description,
            'og_title': og_title,
            'og_description': og_description,
            'og_image': og_image or poster,
            'hls_url': hls_url,
            'poster': poster,
            'is_locked': locked,
            'body_html': inner,
        }

    # ------------------------------------------------------------ 浏览页解析
    @staticmethod
    def build_classify_path(locale, rest=''):
        """拼装源站浏览页路径，如 /tc/classify 或 /tc/classify/<genre>/<id>/<page>"""
        prefix = f'/{locale}' if locale else ''
        suffix = '/' + quote(rest, safe='/') if rest else ''
        return f'{prefix}/classify{suffix}'

    def fetch_classify(self, locale, rest=''):
        """抓取并解析浏览页（全部短剧 / 分类筛选 / 分页）"""
        raw = self.get(self.build_classify_path(locale, rest))
        page = 1
        segs = [s for s in (rest or '').split('/') if s]
        if segs and segs[-1].isdigit():
            page = int(segs[-1])
        url_fn = self._classify_url_fn(locale, rest)
        return self.parse_listing(
            raw, locale, doc_transform=lambda d: self._linkify_pagination(d, url_fn, page))

    @staticmethod
    def _classify_url_fn(locale, rest):
        """浏览页翻页地址生成器（与源站 URL 规则一致）

        - 全部短剧：第 1 页 /classify，第 N 页 /classify/N
        - 分类筛选：/classify/<分类>/<id>/<页码>（页码始终存在）
        """
        prefix = f'/{locale}' if locale else ''
        segs = [s for s in (rest or '').split('/') if s]
        if segs and segs[-1].isdigit():
            segs = segs[:-1]
        sub = '/' + quote('/'.join(segs), safe='/') if segs else ''
        base = f'{prefix}/classify{sub}'
        if segs:
            return lambda p: f'{base}/{p}'
        return lambda p: base if p <= 1 else f'{base}/{p}'

    def parse_listing(self, raw, locale='', doc_transform=None):
        """把列表类页面（浏览页 / 搜索页 / More 专题页）解析为渲染所需数据

        doc_transform: 可选，接收已清理的 DOM，用于页面类型特有的改造（如分页改链接）。
        """
        doc = LH.fromstring(raw)

        title = (doc.findtext('.//title') or '').strip()
        html_lang = self._meta_html_lang(raw) or 'zh-CN'
        description = self._meta(doc, name='description')
        og_title = self._meta(doc, prop='og:title') or title
        og_description = self._meta(doc, prop='og:description') or description
        og_image = self._meta(doc, prop='og:image')

        self._clean(doc, '', False, locale)
        self._fill_lazy_images(doc, raw)
        if doc_transform:
            doc_transform(doc)

        body = doc.body
        if body is None:
            raise ValueError('浏览页缺少 body')
        inner = LH.tostring(body, encoding='unicode')
        inner = re.sub(r'^\s*<body[^>]*>', '', inner)
        inner = re.sub(r'</body>\s*$', '', inner)

        return {
            'title': title,
            'html_lang': html_lang,
            'description': description,
            'og_title': og_title,
            'og_description': og_description,
            'og_image': og_image,
            'body_html': inner,
        }

    # ------------------------------------------------------------ V2 竖屏视频流
    # 手机端 V2 首页 = 抖音式全屏竖屏流：每部剧只放第 1 集（免费集），上滑切换下一部剧。
    @staticmethod
    def _listing_cards(doc):
        """从列表页抽取短剧卡片：[{slug, drama_id, title, poster}]（按剧集 id 去重）"""
        items, seen = [], set()
        for a in doc.xpath('//a[contains(@href,"/playlist/")]'):
            m = re.search(r'/playlist/(?P<slug>[^/]+)/(?P<id>\d+)/episode-\d+',
                          a.get('href') or '')
            if not m:
                continue
            drama_id = int(m.group('id'))
            if drama_id in seen:
                continue
            imgs = a.xpath('.//img')
            poster = ''
            for im in reversed(imgs):  # 优先取非模糊的清晰图（模糊预览图带 blur 参数）
                src = im.get('src') or ''
                if src and 'blur' not in src:
                    poster = src
                    break
            if not poster:
                for im in imgs:
                    if im.get('src'):
                        poster = im.get('src')
                        break
            title = ''
            for im in imgs:
                title = (im.get('alt') or '').strip()
                if title:
                    break
            seen.add(drama_id)
            items.append({
                'slug': m.group('slug'),
                'drama_id': drama_id,
                'title': title or m.group('slug').replace('-', ' '),
                'poster': poster,
            })
        return items

    def fetch_feed(self, locale='', page=1):
        """V2 竖屏流数据：抓取浏览页列表（每部剧对应第 1 集）"""
        page = max(1, int(page))
        rest = '' if page <= 1 else str(page)
        raw = self.get(self.build_classify_path(locale, rest))
        doc = LH.fromstring(raw)
        self._fill_lazy_images(doc, raw)
        items = self._listing_cards(doc)
        for it in items:
            it['play_path'] = self.build_play_path(locale, it['slug'], it['drama_id'], 1)
            it['likes'] = like_count(it['drama_id'])
        return {'items': items, 'page': page, 'next': page + 1}

    def fetch_ep1_video(self, locale, slug, drama_id):
        """V2：取某部剧第 1 集的播放地址、封面与总集数（轻量解析，不做整页清理）"""
        raw = self.get(self.build_play_path(locale, slug, drama_id, 1))
        doc = LH.fromstring(raw)
        # 总集数：优先取剧集列表标题旁的 "N 集 / N Episodes" 数字，兜底取最大集号
        episodes = 0
        for a in doc.xpath('//a[contains(@href,"/episodes-list/")]'):
            m = re.search(r'(\d+)', a.text_content() or '')
            if m:
                episodes = int(m.group(1))
                break
        if not episodes:
            nums = [int(n) for n in re.findall(r'/episode-(\d+)', raw)]
            episodes = max(nums) if nums else 1
        return {
            'hls': self._extract_hls(raw),
            'poster': self._extract_poster(doc),
            'title': (doc.findtext('.//title') or '').strip(),
            'episodes': episodes,
        }

    # ------------------------------------------------------------ App 页解析
    @staticmethod
    def build_app_path(locale):
        """拼装源站 App 下载页路径，如 /tc/app"""
        prefix = f'/{locale}' if locale else ''
        return f'{prefix}/app'

    def fetch_app(self, locale=''):
        """抓取并解析 App 下载页"""
        raw = self.get(self.build_app_path(locale))
        return self.parse_app(raw, locale)

    def parse_app(self, raw, locale=''):
        """把 App 页 HTML 解析为渲染所需的数据字典"""
        doc = LH.fromstring(raw)

        title = (doc.findtext('.//title') or '').strip()
        html_lang = self._meta_html_lang(raw) or 'zh-CN'
        description = self._meta(doc, name='description')
        og_title = self._meta(doc, prop='og:title') or title
        og_description = self._meta(doc, prop='og:description') or description
        og_image = self._meta(doc, prop='og:image')

        self._clean(doc, '', False, locale)
        self._rewrite_app_ui(doc, locale)
        self._inject_banner(doc, locale)

        body = doc.body
        if body is None:
            raise ValueError('App 页缺少 body')
        inner = LH.tostring(body, encoding='unicode')
        inner = re.sub(r'^\s*<body[^>]*>', '', inner)
        inner = re.sub(r'</body>\s*$', '', inner)

        return {
            'title': title,
            'html_lang': html_lang,
            'description': description,
            'og_title': og_title,
            'og_description': og_description,
            'og_image': og_image,
            'body_html': inner,
        }

    def _rewrite_app_ui(self, doc, locale):
        """App 页：删除二维码与其说明文字，改为下载按钮（指向统一下载链接）"""
        # 1) 删除二维码区块（.app-code）及其紧邻的"扫描二维码..."说明
        for box in doc.xpath('//div[contains(@class,"app-code")]'):
            parent = box.getparent()
            if parent is None:
                continue
            nxt = box.getnext()
            parent.remove(box)
            if nxt is not None and isinstance(nxt.tag, str) and 'text-center' in (nxt.get('class') or ''):
                parent.remove(nxt)

        # 2) 移动端"下载 APP"按钮：div -> a（指向统一下载链接，保留原有属性/样式作用域）
        for btn in doc.xpath('//div[contains(@class,"download-btn")]'):
            a = etree.Element('a')
            for k, v in btn.attrib.items():
                a.set(k, v)
            a.set('href', APP_URL_PLACEHOLDER)
            a.set('target', '_blank')
            a.set('rel', 'noopener')
            a.set('style', (btn.get('style') or '') + ';text-decoration:none')
            for child in list(btn):
                a.append(child)
            btn.getparent().replace(btn, a)

        # 3) 桌面端二维码卡片内补一个下载按钮（替代原来的二维码）
        logos = doc.xpath('//img[contains(@class,"img-logo")]')
        if logos:
            label = APP_DOWNLOAD_LABEL.get(locale or 'en', APP_DOWNLOAD_LABEL['en'])
            btn_html = (
                f'<a href="{APP_URL_PLACEHOLDER}" target="_blank" rel="noopener" '
                'style="margin-top:30px;width:200px;height:48px;'
                'background:linear-gradient(270deg,#e58c00,#fcdb00);border-radius:1.66rem;'
                'display:flex;align-items:center;justify-content:center;font-weight:600;'
                'font-size:1rem;color:#333;text-decoration:none;cursor:pointer">'
                '<svg width="18" height="18" viewBox="0 0 14.375 14.688" fill="currentColor" '
                'aria-hidden="true" style="margin-right:.5rem;flex:none">'
                '<use xlink:href="#icon-download"></use></svg>'
                f'<span>{label}</span></a>'
            )
            logos[0].getparent().append(LH.fragment_fromstring(btn_html))

    # ------------------------------------------------------------ 搜索页解析
    @staticmethod
    def build_search_path(locale, drama=''):
        """拼装源站搜索页路径，如 /tc/search?drama=離婚"""
        prefix = f'/{locale}' if locale else ''
        suffix = f'?drama={quote(drama)}' if drama else ''
        return f'{prefix}/search{suffix}'

    def fetch_search(self, locale, drama=''):
        """抓取并解析搜索页"""
        raw = self.get(self.build_search_path(locale, drama))
        return self.parse_listing(raw, locale)

    # ------------------------------------------------------------ More 专题页
    @staticmethod
    def build_more_path(locale, slug, section_id, page=1):
        """拼装源站 More 专题页路径，如 /more/hot-picks/9236 或 /more/hot-picks/9236/2"""
        prefix = f'/{locale}' if locale else ''
        base = f'{prefix}/more/{quote(slug, safe="")}/{int(section_id)}'
        return f'{base}/{int(page)}' if int(page) > 1 else base

    def fetch_more(self, locale, slug, section_id, page=1):
        """抓取并解析 More 专题页（首页各板块 "More" 的落地页，支持分页）"""
        page = max(1, int(page))
        raw = self.get(self.build_more_path(locale, slug, section_id, page))
        base_url = (f'/{locale}' if locale else '') + f'/more/{quote(slug, safe="")}/{int(section_id)}'
        url_fn = lambda p: base_url if p <= 1 else f'{base_url}/{p}'

        return self.parse_listing(
            raw, locale, doc_transform=lambda d: self._linkify_pagination(d, url_fn, page))

    def _linkify_pagination(self, doc, page_url_fn, current_page):
        """把源站分页控件（Element/Vant，均为 JS 按钮）改成可跳转的链接。

        page_url_fn(p): 由页码生成跳转地址（各页面类型规则不同，由调用方提供）。
        """
        def to_link(el, page):
            a = etree.Element('a')
            for k, v in el.attrib.items():
                if k == 'type':          # button 的 type 属性对 a 标签无效
                    continue
                a.set(k, v)
            a.set('href', page_url_fn(page))
            a.set('style', (el.get('style') or '') + ';text-decoration:none;cursor:pointer')
            for child in list(el):
                a.append(child)
            if el.text and el.text.strip():
                a.text = el.text
            el.getparent().replace(el, a)

        # 桌面端：页码
        for li in doc.xpath('//ul[contains(@class,"el-pager")]/li[contains(@class,"number")]'):
            t = (li.text_content() or '').strip()
            if not t.isdigit() or 'is-active' in (li.get('class') or ''):
                continue
            to_link(li, int(t))
        # 桌面端：上一页 / 下一页
        for btn in doc.xpath('//button[contains(@class,"btn-prev") or contains(@class,"btn-next")]'):
            if btn.get('disabled') is not None:
                continue
            to_link(btn, current_page - 1 if 'btn-prev' in (btn.get('class') or '') else current_page + 1)
        # 移动端：上一页 / 下一页
        for li in doc.xpath('//li[contains(@class,"van-pagination__item--prev") or '
                            'contains(@class,"van-pagination__item--next")]'):
            cls = li.get('class') or ''
            if 'disabled' in cls:
                continue
            btn = li.xpath('.//button')
            if btn:
                to_link(btn[0], current_page - 1 if 'prev' in cls else current_page + 1)

    # ------------------------------------------------------------ 内部工具
    @staticmethod
    def _fill_lazy_images(doc, raw=''):
        """回填源站客户端懒加载的封面：

        1) 先按 alt 匹配同页已有图片；
        2) 再从 Nuxt 数据载荷中解析 playlet_id -> cover，按卡片链接里的剧集 id 精确回填。
        """
        def norm(s):
            return ' '.join((s or '').replace('\xa0', ' ').split()).lower()

        alt2src = {}
        for im in doc.xpath('//img'):
            src = im.get('src') or ''
            if 'farsunpteltd' in src and 'w_600' in src:
                alt2src[norm(im.get('alt'))] = src

        # 数据载荷：<playlet_id>,"<title>","<cover-url>" 连续出现
        id2cover = {}
        if raw:
            plain = raw.replace('\\u002F', '/').replace('\\/', '/')
            for m in re.finditer(r'(\d{4,}),"[^"]*","(https://[^"]+\.(?:jpg|png))"', plain):
                id2cover.setdefault(m.group(1), m.group(2))

        for im in doc.xpath('//img'):
            if (im.get('src') or '').strip():
                continue
            src = alt2src.get(norm(im.get('alt')))
            if not src:
                node, href = im, None
                for _ in range(8):
                    node = node.getparent()
                    if node is None or not isinstance(node.tag, str):
                        break
                    if node.tag == 'a' and node.get('href'):
                        href = node.get('href')
                        break
                ids = re.findall(r'/(\d+)(?:/|$)', href or '')
                cover = id2cover.get(ids[0]) if ids else None
                if cover:
                    src = cover + '?x-oss-process=image/resize,w_600,image/format,webp'
            if src:
                im.set('src', src)
                cls = im.get('class') or ''
                if 'full' in cls and 'loaded' not in cls:
                    im.set('class', (cls + ' loaded').strip())

    @staticmethod
    def _meta(doc, prop=None, name=None):
        if prop:
            els = doc.xpath(f'//meta[@property="{prop}"]')
        else:
            els = doc.xpath(f'//meta[@name="{name}"]')
        return (els[0].get('content') or '').strip() if els else ''

    @staticmethod
    def _meta_html_lang(raw):
        m = re.search(r'<html[^>]+lang="([^"]+)"', raw)
        return m.group(1) if m else ''

    @staticmethod
    def _extract_hls(raw):
        """从 Nuxt 数据载荷中提取 m3u8 播放地址（含时效签名）"""
        normalized = raw.replace('\\u002F', '/').replace('\\/', '/')
        urls = re.findall(r'https://[^"\s\\]+\.m3u8[^"\s\\]*', normalized)
        if not urls:
            return ''
        for u in urls:
            if '_hls_' in u:
                return u
        return urls[0]

    @staticmethod
    def _extract_poster(doc):
        v = doc.xpath('//video')
        return (v[0].get('poster') or '').strip() if v else ''

    # ------------------------------------------------------ 促销（送钱）横幅
    @staticmethod
    def _main_content(doc):
        """主内容区（顶部导航之下、底部推广条之上的容器）"""
        nodes = doc.xpath(
            '//div[contains(@class,"min-h-screen")]'
            '/div[contains(concat(" ",normalize-space(@class)," ")," flex-1 ")]')
        return nodes[0] if nodes else None

    @staticmethod
    def _reward_banner_html(locale):
        """促销横幅：左侧「标题 + 副标题」，右侧下载按钮（指向统一下载链接）"""
        r = reward_copy(locale)
        return (
            '<div style="position:relative;z-index:1000;margin:12px;padding:14px 16px;'
            'border-radius:14px;background:linear-gradient(90deg,#e58c00,#fcdb00);'
            'color:#1a1a1a;display:flex;align-items:center;gap:12px;flex-wrap:wrap">'
            '<div style="flex:1 1 200px;min-width:0">'
            f'<div style="font-weight:800;font-size:17px;line-height:1.25">{r["title"]}</div>'
            f'<div style="font-size:13px;opacity:.85;margin-top:2px">{r["sub"]}</div>'
            '</div>'
            f'<a href="{APP_URL_PLACEHOLDER}" target="_blank" rel="noopener" '
            'style="flex:none;background:#1a1a1a;color:#fcdb00;font-weight:700;font-size:14px;'
            'padding:10px 18px;border-radius:9999px;text-decoration:none;white-space:nowrap">'
            f'{r["cta"]}</a></div>'
        )

    def _inject_banner(self, doc, locale):
        """促销横幅插到主内容区之前（顶部导航之下、全宽；播放页 / App 页共用）"""
        main = self._main_content(doc)
        if main is None:
            return
        main.addprevious(LH.fragment_fromstring(self._reward_banner_html(locale)))

    # ------------------------------------------------------ 点赞（引导下载）
    @staticmethod
    def _like_html(drama_id):
        """信息面板里的「操作模块」：首个功能是点赞（爱心 + 数量）。
        后续新增功能（收藏 / 分享 / 评分…）直接往这个容器里加即可。"""
        n = like_count(drama_id or 0)
        return (
            '<div class="fr-actions" data-fr-actions '
            'style="display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:14px 0 2px">'
            '<button type="button" data-like-btn aria-label="like" '
            'style="display:flex;align-items:center;gap:6px;padding:7px 14px;'
            'border:1px solid #333;border-radius:9999px;background:#1f1f1f;color:#e5e5e5;'
            'font-size:13px;font-weight:600;cursor:pointer">'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="#ff4d6d" aria-hidden="true">'
            '<path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 '
            '3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5'
            'c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>'
            f'<span data-like-count>{n:,}</span></button>'
            '</div>'
        )

    @staticmethod
    def _like_modal_html(locale):
        """点击点赞后弹出的提示：需先下载 APP"""
        c = LIKE_COPY.get(locale or 'en') or LIKE_COPY['en']
        return (
            '<div data-like-modal style="display:none;position:fixed;inset:0;z-index:3000;'
            'background:rgba(0,0,0,.78);align-items:center;justify-content:center;padding:16px">'
            '<div style="width:min(330px,86vw);background:#1c1c1c;border-radius:16px;'
            'padding:26px 22px 14px;text-align:center;color:#fff">'
            f'<div style="font-size:16px;font-weight:700;line-height:1.55">{c["hint"]}</div>'
            f'<a href="{APP_URL_PLACEHOLDER}" target="_blank" rel="noopener" '
            'style="display:flex;align-items:center;justify-content:center;margin:20px auto 0;'
            'max-width:240px;height:46px;border-radius:9999px;'
            'background:linear-gradient(270deg,#e58c00,#fcdb00);color:#333;font-weight:700;'
            'font-size:15px;text-decoration:none">'
            f'{c["cta"]}</a>'
            '<button type="button" data-like-close style="margin-top:12px;border:0;'
            'background:none;color:#8a8a8a;font-size:18px;line-height:1.4;cursor:pointer">✕</button>'
            '</div></div>'
        )

    def _inject_like(self, doc, locale, drama_id):
        """播放页：在右侧信息面板（info-panel-scroll）里新增「操作模块」，
        首个功能为点赞按钮；点击后弹出"需先下载 APP"的提示弹窗。"""
        panels = doc.xpath('//div[contains(@class,"info-panel-scroll")]')
        if not panels or doc.body is None:
            return
        panel = panels[0]
        module = LH.fragment_fromstring(self._like_html(drama_id))
        # 放在标签行（row-scroll）之后，找不到就追加到面板末尾
        tags = panel.xpath('.//div[contains(concat(" ",normalize-space(@class)," ")," row-scroll ")]')
        if tags:
            tags[0].addnext(module)
        else:
            panel.append(module)
        doc.body.append(LH.fragment_fromstring(self._like_modal_html(locale)))

    def _clean(self, doc, hls_url, locked, locale, poster=''):
        """清理页面：去脚本/注释、站内链接改相对、播放器注入播放地址、
        统一下载位置（底部推广条 / 导航 App / 锁定遮罩）"""
        for s in doc.xpath('//script'):
            s.drop_tree()
        for node in list(doc.iter()):
            if not isinstance(node.tag, str) and node.tag is etree.Comment:
                try:
                    node.drop_tree()
                except Exception:
                    pass

        # 站内绝对链接 -> 相对路径
        for a in doc.xpath('//a'):
            href = a.get('href') or ''
            if href.startswith(self.BASE):
                a.set('href', href[len(self.BASE):] or '/')

        # 删除顶部导航 "Resources" 模块（英文站菜单）
        for box in doc.xpath('//*[contains(@class,"resources-menu")]'):
            parent = box.getparent()
            if parent is not None:
                parent.remove(box)

        # 源站 Nuxt 静态资源（_nuxt/xxx）-> 本地静态目录
        for im in doc.xpath('//img'):
            src = im.get('src') or ''
            if src.startswith('/_nuxt/'):
                im.set('src', '/static/images/' + os.path.basename(src))

        # 空结果占位图（源站 /_nuxt/no-message*.png）-> 用内置搜索图标代替
        for im in doc.xpath('//img[contains(@src,"no-message") or @alt="no-results"]'):
            cls = im.get('class') or ''
            svg = LH.fragment_fromstring(
                f'<svg class="{cls}" viewBox="0 0 20 20" fill="none" aria-hidden="true" '
                'style="color:#666"><use xlink:href="#icon-fdj"></use></svg>')
            im.getparent().replace(im, svg)

        # 播放器：改造为可用 hls.js 驱动、带原生控件的元素（仅可播放的集数）
        for v in doc.xpath('//video'):
            poster = v.get('poster') or ''
            v.attrib.clear()
            v.set('class', 'flick-video')
            v.set('controls', 'controls')
            v.set('playsinline', 'playsinline')
            v.set('preload', 'metadata')
            v.set('data-hls', hls_url)
            v.set('style', 'width:100%;height:100%;display:block;object-fit:contain;background:#000')
            if poster:
                v.set('poster', poster)

        # 播放页：源站把播放器容器设成 fixed（左侧固定，滚动页面时纹丝不动、还会盖住内容），
        # 这里把它改回普通文档流，让播放器随页面一起滚动。
        video_box_cls = {
            'fixed', 'top-35.5', 'z-100', 'lg:z-50', 'lg:fixed', 'lg:top-16.5',
            'lg:left-0', 'lg:right-119', 'lg:bottom-0', 'lg:h-auto', 'lg:mt-0',
            'lg:min-h-100', 'lg:w-auto',
        }
        for box in doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," h-90 ")'
                             ' and contains(@class,"bg-black")]'):
            kept = [c for c in (box.get('class') or '').split() if c not in video_box_cls]
            box.set('class', ' '.join(kept + ['relative', 'lg:flex-1',
                                              'lg:h-[calc(100vh-4.125rem)]']))
        # 该行容器不再固定高度/裁剪（否则内容会被裁掉、页面滚动也会异常）
        for row in doc.xpath('//div[contains(@class,"lg:h-[calc(100vh-4.125rem)]")'
                             ' and contains(@class,"lg:overflow-hidden")]'):
            row.set('class', ' '.join(
                c for c in (row.get('class') or '').split()
                if c not in ('lg:h-[calc(100vh-4.125rem)]', 'lg:overflow-hidden')))
        # 原本给 fixed 播放器占位的移动端空块，播放器回到文档流后不再需要
        for spacer in doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," h-90 ")'
                                ' and contains(@class,"lg:hidden")'
                                ' and contains(@class,"pointer-events-none")]'):
            spacer.getparent().remove(spacer)

        # 底部推广条右侧 CTA -> 指向统一下载链接（顶部导航 "App" 保持站内 /app 链接）
        self._rewrite_bottom_bar(doc)
        # 板块 "More"（源站为无跳转 div）-> 改成指向同板块的链接
        self._linkify_more(doc)
        # 锁定集：移除播放器，并确保有"下载 App"遮罩
        if locked:
            for v in doc.xpath('//video'):
                v.getparent().remove(v)
            # 源站自带遮罩则改造它，否则（源站本可播放、由我们强制锁定）注入一个
            if not self._rewrite_lock_overlay(doc, locale):
                self._inject_lock_overlay(doc, locale, poster)
        # 剧集列表：超出免费集数的项一律置灰 + 小锁角标（不论当前打开的是第几集）
        self._mark_locked_episodes(doc)

    @staticmethod
    def _rewrite_bottom_bar(doc):
        """底部推广条右侧按钮（原为无跳转的 div）改为下载链接"""
        for div in doc.xpath('//div[contains(@class,"max-w-36") and contains(@class,"rounded-full")]'):
            parent = div.getparent()
            if parent is None:
                continue
            a = etree.Element('a')
            a.set('href', APP_URL_PLACEHOLDER)
            a.set('target', '_blank')
            a.set('rel', 'noopener')
            a.set('class', (div.get('class') or '') + ' cursor-pointer')
            a.text = div.text
            parent.replace(div, a)

    @staticmethod
    def _linkify_more(doc):
        """把两处 "More" 改成可用链接：
        1) 板块标题右侧的 "More"（源站是无跳转的 div）-> 指向该板块
        2) "加载更多" 按钮（button.more-btn）-> 指向该板块的列表页
        """
        for div in doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," More ")]'):
            box = div
            href = None
            for _ in range(4):
                box = box.getparent()
                if box is None or not isinstance(box.tag, str):
                    break
                links = box.xpath('.//a[@href]')
                if links:
                    href = links[0].get('href')
                    break
            if not href:
                continue
            a = etree.Element('a')
            a.set('class', 'More')
            a.set('href', href)
            for child in list(div):
                a.append(child)
            if div.text and div.text.strip():
                a.text = div.text
            div.getparent().replace(div, a)

        for btn in doc.xpath('//button[contains(concat(" ",normalize-space(@class)," ")," more-btn ")]'):
            secs = btn.xpath('ancestor::div[contains(concat(" ",normalize-space(@class)," ")," column-list ")][1]')
            href = None
            if secs:
                links = secs[0].xpath('.//div[contains(@class,"column-title")]//a[@href]/@href')
                if links:
                    href = links[0]
            if not href:
                continue
            a = etree.Element('a')
            a.set('class', btn.get('class') or 'more-btn')
            a.set('href', href)
            a.text = btn.text
            btn.getparent().replace(btn, a)

    def _rewrite_lock_overlay(self, doc, locale):
        """锁定集遮罩：移除二维码与品牌徽标，替换为"下载 App"按钮。
        返回是否找到源站自带遮罩（False 表示需要自行注入）。"""
        overlays = doc.xpath('//div[contains(@class,"inset-0") and contains(@class,"bg-black/80")]')
        if not overlays:
            return False
        overlay = overlays[0]

        # 移除二维码区块（含空 src 图片的 h-[200px] 容器）
        for box in overlay.xpath('.//div[contains(@class,"h-[200px]")]'):
            box.getparent().remove(box)
        # 移除原 FlickReels 品牌徽标区块（w-[240px]）
        for box in overlay.xpath('.//div[contains(@class,"w-[240px]")]'):
            box.getparent().remove(box)

        # 下载按钮追加到内层容器（保留源站自身的提示文案，无需改动）
        inner = overlay.xpath('.//div[contains(@class,"w-[268px]")]')
        target = inner[0] if inner else overlay
        if inner:
            # 原容器为固定高度（含二维码占位），改为自适应
            target.set('style', (target.get('style') or '') + ';height:auto')

        # 促销标题（"送钱"钩子）置于弹框顶部
        r = reward_copy(locale)
        headline = (
            '<div style="text-align:center;margin-bottom:14px">'
            f'<div style="font-weight:800;font-size:20px;color:#fcdb00;line-height:1.25">'
            f'{r["title"]}</div>'
            f'<div style="font-size:13px;color:rgba(255,255,255,.7);margin-top:4px">'
            f'{r["sub"]}</div>'
            '</div>'
        )
        target.insert(0, LH.fragment_fromstring(headline))

        label = APP_DOWNLOAD_LABEL.get(locale or 'en', APP_DOWNLOAD_LABEL['en'])
        btn_html = (
            f'<a href="{APP_URL_PLACEHOLDER}" target="_blank" rel="noopener" '
            'style="margin:30px auto 0;width:240px;height:50px;'
            'background:linear-gradient(270deg,#e58c00,#fcdb00);border-radius:9999px;'
            'display:flex;align-items:center;justify-content:center;font-weight:600;'
            'font-size:.95rem;color:#333;text-decoration:none;cursor:pointer">'
            '<svg width="18" height="18" viewBox="0 0 14.375 14.688" fill="currentColor" '
            'aria-hidden="true" style="margin-right:.5rem;flex:none">'
            '<use xlink:href="#icon-download"></use></svg>'
            f'<span>{label}</span></a>'
        )
        target.append(LH.fragment_fromstring(btn_html))
        return True

    def _inject_lock_overlay(self, doc, locale, poster=''):
        """源站本可播放、但被我们强制锁定的集数：在播放器区域注入锁定遮罩
        （封面做背景 + 促销标题 + 提示文案 + 下载按钮）"""
        boxes = doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," h-90 ")'
                          ' and contains(@class,"bg-black")]')
        if not boxes:
            return
        r = reward_copy(locale)
        hint = LOCK_HINT.get(locale or 'en') or LOCK_HINT['en']
        label = APP_DOWNLOAD_LABEL.get(locale or 'en', APP_DOWNLOAD_LABEL['en'])
        bg = (f'background-image:url({poster});background-size:cover;'
              'background-position:center;') if poster else ''
        html = (
            f'<div style="position:absolute;inset:0;z-index:30;display:flex;'
            f'align-items:center;justify-content:center;{bg}">'
            '<div style="position:absolute;inset:0;background:rgba(0,0,0,.82)"></div>'
            '<div style="position:relative;width:268px;max-width:84%;padding:24px 18px;'
            'text-align:center;color:#fff;background:#1c1c1c;border-radius:14px">'
            f'<div style="font-weight:800;font-size:19px;color:#fcdb00;line-height:1.25">'
            f'{r["title"]}</div>'
            f'<div style="font-size:12px;color:rgba(255,255,255,.7);margin-top:4px">'
            f'{r["sub"]}</div>'
            f'<div style="font-size:15px;font-weight:600;line-height:1.5;margin-top:16px">'
            f'{hint}</div>'
            f'<a href="{APP_URL_PLACEHOLDER}" target="_blank" rel="noopener" '
            'style="margin:22px auto 0;width:240px;max-width:100%;height:50px;'
            'background:linear-gradient(270deg,#e58c00,#fcdb00);border-radius:9999px;'
            'display:flex;align-items:center;justify-content:center;font-weight:600;'
            'font-size:.95rem;color:#333;text-decoration:none">'
            '<svg width="18" height="18" viewBox="0 0 14.375 14.688" fill="currentColor" '
            'aria-hidden="true" style="margin-right:.5rem;flex:none">'
            '<use xlink:href="#icon-download"></use></svg>'
            f'<span>{label}</span></a>'
            '</div></div>'
        )
        boxes[0].append(LH.fragment_fromstring(html))

    # 剧集列表里锁定项的角标（与源站锁定集同款式：小锁）
    LOCK_BADGE_SVG = (
        '<svg class="svg-icon absolute left-0 top-0 w-[1em] h-[1em] text-[1em]" '
        'aria-hidden="true"><use xlink:href="#icon-unlock"></use></svg>'
    )

    def _mark_locked_episodes(self, doc, free=FREE_EPISODES):
        """剧集列表：把超出免费集数的项置灰并加小锁角标，避免访客误以为还能继续看"""
        for a in doc.xpath('//a[@data-episode-chapter-id]'):
            m = re.search(r'/episode-(\d+)/?$', a.get('href') or '')
            if not m or int(m.group(1)) <= free:
                continue
            if 'icon-unlock' in LH.tostring(a, encoding='unicode'):
                continue  # 源站已标记过
            cls = a.get('class') or ''
            if 'text-[#6D6D6E]!' not in cls:
                a.set('class', cls + ' text-[#6D6D6E]!')
            a.append(LH.fragment_fromstring(self.LOCK_BADGE_SVG))
