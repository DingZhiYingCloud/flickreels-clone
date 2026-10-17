# -*- coding: utf-8 -*-
"""自定义模板标签/过滤器：统一下载链接与统计埋点"""
from django import template

from Web.crawler.flickreels import APP_URL_PLACEHOLDER
from Web.utils import pick_download_url, stats_url

register = template.Library()


@register.filter
def app_link(html, url):
    """把抓取到的 HTML 中的下载占位符替换为全站统一下载链接

    用法：{{ body_html|app_link:app_download_url|safe }}
    """
    if not html:
        return html
    return html.replace(APP_URL_PLACEHOLDER, url or '#')


@register.simple_tag(takes_context=True)
def app_download_url(context):
    """全站统一下载链接（按当前页面语言自动选择：语言配置 > 全局默认）

    用法：{% app_download_url as app_download_url %}
    """
    try:
        request = context['request']
    except KeyError:
        request = None
    path = (request.path if request is not None else '') or ''
    # 路径首段即语言代码（如 /tc/playlist/... → tc；根路径 → ''）
    locale = path.strip('/').split('/')[0]
    return pick_download_url(locale)


@register.simple_tag
def app_stats_url():
    """数据统计（安装统计）埋点地址

    用法：{% app_stats_url as app_stats_url %}
    """
    return stats_url()
