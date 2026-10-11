# 项目URL配置
from django.urls import path
from django.views.generic import TemplateView

from Web.views import request

# 多语言首页：源站每个语言一个独立 URL（英文为根路径）
LOCALES = ['ja', 'ko', 'es', 'id', 'de', 'th', 'tc', 'fr', 'pt']

urlpatterns = [
    path('', request.index, name='home'),
    path('index/', request.index, name='index'),
]

# 各语言首页路由，如 /ja/、/ko/ ...
urlpatterns += [
    path(f'{loc}/', TemplateView.as_view(template_name=f'locales/{loc}.html'), name=f'locale_{loc}')
    for loc in LOCALES
]

# 短剧播放页：/playlist/<slug>/<id>/episode-<n>（英文）及各语言前缀版本
urlpatterns += [
    path('playlist/<str:slug>/<int:drama_id>/episode-<int:episode>',
         request.play, name='play'),
]
urlpatterns += [
    path(f'{loc}/playlist/<str:slug>/<int:drama_id>/episode-<int:episode>',
         request.play, {'locale': loc}, name=f'play_{loc}')
    for loc in LOCALES
]

# 短剧详情页 / 剧集列表页：源站为 /movie/<slug>-<id>、/episodes-list/<slug>-<id>，
# 本站无这两页，统一 301 到该剧第 1 集播放页
_DETAIL_PREFIXES = ('movie', 'episodes-list')
urlpatterns += [
    path(f'{p}/<str:slug_id>', request.drama_detail, name=p.replace('-', '_'))
    for p in _DETAIL_PREFIXES
]
urlpatterns += [
    path(f'{loc}/{p}/<str:slug_id>', request.drama_detail, {'locale': loc},
         name=f'{p.replace("-", "_")}_{loc}')
    for loc in LOCALES for p in _DETAIL_PREFIXES
]

# 短剧浏览页：/classify 及 /classify/<分类>/<id>/<页>（英文）与各语言前缀版本
urlpatterns += [
    path('classify/', request.classify, name='classify'),
    path('classify/<path:rest>', request.classify, name='classify_rest'),
]
urlpatterns += [
    path(f'{loc}/classify/', request.classify, {'locale': loc}, name=f'classify_{loc}')
    for loc in LOCALES
]
urlpatterns += [
    path(f'{loc}/classify/<path:rest>', request.classify, {'locale': loc}, name=f'classify_rest_{loc}')
    for loc in LOCALES
]

# App 下载页：/app 及各语言前缀版本
urlpatterns += [
    path('app/', request.app, name='app'),
]
urlpatterns += [
    path(f'{loc}/app/', request.app, {'locale': loc}, name=f'app_{loc}')
    for loc in LOCALES
]

# 搜索页：/search（英文）与各语言前缀版本，关键词通过 ?drama= 传入
urlpatterns += [path(s, request.search) for s in ('search', 'search/')]
urlpatterns += [
    path(f'{loc}/{s}', request.search, {'locale': loc})
    for loc in LOCALES for s in ('search', 'search/')
]

# More 专题页：/more/<板块>/<id>[/<页码>]（英文）与各语言前缀版本
urlpatterns += [
    path('more/<str:slug>/<int:section_id>', request.more, name='more'),
    path('more/<str:slug>/<int:section_id>/<int:page>', request.more, name='more_page'),
]
urlpatterns += [
    path(f'{loc}/more/<str:slug>/<int:section_id>', request.more, {'locale': loc}, name=f'more_{loc}')
    for loc in LOCALES
]
urlpatterns += [
    path(f'{loc}/more/<str:slug>/<int:section_id>/<int:page>', request.more, {'locale': loc}, name=f'more_page_{loc}')
    for loc in LOCALES
]
