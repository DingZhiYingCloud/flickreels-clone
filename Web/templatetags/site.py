# -*- coding: utf-8 -*-
"""自定义模板过滤器：统一下载链接处理"""
from django import template

from Web.crawler.flickreels import APP_URL_PLACEHOLDER

register = template.Library()


@register.filter
def app_link(html, url):
    """把抓取到的 HTML 中的下载占位符替换为全站统一下载链接

    用法：{{ body_html|app_link:app_download_url|safe }}
    """
    if not html:
        return html
    return html.replace(APP_URL_PLACEHOLDER, url or '#')
