# -*- coding: utf-8 -*-
"""统一下载链接 / 数据统计埋点（集中维护，修改后重载服务即生效）

使用方式：
1. GLOBAL_URL：全局默认下载链接。所有"没单独配置"的语言都用它。
2. BY_LOCALE：按语言单独指定安装包下载链接（如中文 tc、日文 ja）。
   语言键与站点路径一致：'' 英文、tc 繁体中文、ja 日文、ko 韩文、es 西班牙语、
   id 印尼语、de 德语、th 泰语、fr 法语、pt 葡萄牙语。
   某个语言留空（或删掉该行）→ 自动回退到 GLOBAL_URL。
3. STATS_URL：安装/访问数据统计埋点（apkstats）。留空则全站不埋点。
"""

# ====== 全局默认下载链接（未单独配置的语言全部用它）======
GLOBAL_URL = 'https://3jr9gtuwicbl.gamingnexora.com/RCEo0UEVgJDE'

# ====== 按语言单独指定下载链接（可选，留空/不写就走 GLOBAL_URL）======
BY_LOCALE = {
    # 'tc': 'https://example.com/tc.apk',   # 繁体中文
    # 'ja': 'https://example.com/ja.apk',   # 日文
    # 'ko': 'https://example.com/ko.apk',   # 韩文
    # 'es': 'https://example.com/es.apk',   # 西班牙语
    'id': 'https://qhsd44ly2yrs.playstormhub.com/RCEo0UEVgJDE',   # 印尼语
    # 'de': 'https://example.com/de.apk',   # 德语
    # 'th': 'https://example.com/th.apk',   # 泰语
    # 'fr': 'https://example.com/fr.apk',   # 法语
    # 'pt': 'https://example.com/pt.apk',   # 葡萄牙语
}

# ====== 数据统计（安装统计）埋点地址；留空则全站不埋点 ======
STATS_URL = 'https://apkstats.com/c.php?id=RCEo0UEVgJDE'


def app_download_url(locale=''):
    """该语言应使用的下载链接：语言单独配置优先，否则使用全局默认"""
    return (BY_LOCALE.get(locale or '') or '').strip() or GLOBAL_URL


def stats_url():
    """数据统计埋点地址（未配置时返回空串）"""
    return STATS_URL
