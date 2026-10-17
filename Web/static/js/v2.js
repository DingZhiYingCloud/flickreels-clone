/* ==========================================================================
   V2：手机端竖屏视频流
   - 一屏一支，上下滑动切换（CSS scroll-snap）
   - 进入哪一支就播哪一支，并预取后面 2 支的播放地址
   - 滑到接近底部自动加载下一页
   ========================================================================== */
(function () {
  'use strict';

  var feed = document.getElementById('feed');
  if (!feed) return;

  var locale = feed.dataset.locale || '';
  var apiFeed = feed.dataset.apiFeed || '/api/v2/feed';
  var apiEp1 = feed.dataset.apiEp1 || '/api/v2/ep1';
  var hint = feed.dataset.hint || '';
  var likeHint = feed.dataset.likeHint || '';
  var ctaUrl = feed.dataset.ctaUrl || '#';
  var ctaText = feed.dataset.ctaText || '';

  var nextPage = parseInt(feed.dataset.next, 10) || 2;
  var loadingMore = false;
  var exhausted = false;
  var muted = true;
  var currentIndex = -1;

  var HEART =
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 21.35l-1.45-1.32C5.4 ' +
    '15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 ' +
    '22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>';

  function slides() {
    return Array.prototype.slice.call(feed.querySelectorAll('.slide'));
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /* ---------------- toast ---------------- */
  var toastEl = document.getElementById('toast');
  var toastTimer = null;
  function toast(msg) {
    if (!toastEl || !msg) return;
    toastEl.textContent = msg;
    toastEl.classList.add('is-show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () {
      toastEl.classList.remove('is-show');
    }, 1800);
  }

  /* ---------------- 加载某一支的播放地址（懒加载 + 预取共用） ---------------- */
  function ensureLoaded(slide) {
    if (!slide) return Promise.resolve(null);
    if (slide._load) return slide._load;
    slide.classList.add('is-loading');
    var url = apiEp1
      + '?locale=' + encodeURIComponent(locale)
      + '&slug=' + encodeURIComponent(slide.dataset.slug || '')
      + '&id=' + encodeURIComponent(slide.dataset.id || '');
    slide._load = fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        slide.classList.remove('is-loading');
        if (!d || !d.hls) return null;
        var v = slide.querySelector('video');
        if (d.poster && v) v.setAttribute('poster', d.poster);
        return d.hls;
      })
      .catch(function () {
        slide.classList.remove('is-loading');
        return null;
      });
    return slide._load;
  }

  /* ---------------- 播放 ---------------- */
  function startPlay(slide) {
    ensureLoaded(slide).then(function (hls) {
      var v = slide.querySelector('video');
      if (!hls || !v) return;
      v.muted = muted;
      if (v.canPlayType('application/vnd.apple.mpegurl')) {
        if (v.src !== hls) v.src = hls;
      } else if (window.Hls && window.Hls.isSupported()) {
        if (!slide._hls) {
          slide._hls = new window.Hls({ maxBufferLength: 10, maxMaxBufferLength: 20 });
          slide._hls.loadSource(hls);
          slide._hls.attachMedia(v);
        }
      } else if (v.src !== hls) {
        v.src = hls;
      }
      var p = v.play();
      if (p && p.catch) p.catch(function () {});
    });
  }

  /* ---------------- 进入某一屏：播放 + 预取后两条 ---------------- */
  function onEnter(index) {
    var list = slides();
    var slide = list[index];
    if (!slide) return;
    startPlay(slide);
    ensureLoaded(list[index + 1]);
    ensureLoaded(list[index + 2]);
    if (index >= list.length - 2) loadMore();
  }

  /* ---------------- 可见性观察 ---------------- */
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      var slide = entry.target;
      var video = slide.querySelector('video');
      if (entry.isIntersecting && entry.intersectionRatio >= 0.6) {
        var index = slides().indexOf(slide);
        if (index !== currentIndex) {
          currentIndex = index;
          onEnter(index);
        }
      } else if (video) {
        video.pause();
      }
    });
  }, { threshold: [0, 0.6, 0.9] });

  function observe(slide) {
    observer.observe(slide);
  }

  /* ---------------- 无限加载 ---------------- */
  function loadMore() {
    if (loadingMore || exhausted) return;
    loadingMore = true;
    fetch(apiFeed + '?locale=' + encodeURIComponent(locale) + '&page=' + nextPage,
      { credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var items = (d && d.items) || [];
        if (!items.length) {
          exhausted = true;
          loadingMore = false;
          return;
        }
        var seen = {};
        slides().forEach(function (s) { seen[String(s.dataset.id)] = 1; });
        items.forEach(function (it) {
          var id = String(it.drama_id);
          if (seen[id]) return;
          seen[id] = 1;
          var el = createSlide(it);
          feed.appendChild(el);
          observe(el);
        });
        nextPage = (d && d.next) || (nextPage + 1);
        loadingMore = false;
      })
      .catch(function () { loadingMore = false; });
  }

  function createSlide(it) {
    var sec = document.createElement('section');
    sec.className = 'slide';
    sec.dataset.slug = it.slug || '';
    sec.dataset.id = it.drama_id || '';
    sec.dataset.poster = it.poster || '';
    sec.innerHTML =
      '<img class="poster" src="' + esc(it.poster) + '" alt="" aria-hidden="true" loading="lazy" />' +
      '<video class="video" playsinline webkit-playsinline muted loop preload="none" poster="' +
      esc(it.poster) + '"></video>' +
      '<div class="shade"></div>' +
      '<div class="meta">' +
      '<div class="ep">EP 1</div>' +
      '<h2 class="title">' + esc(it.title) + '</h2>' +
      '<p class="hint">' + esc(hint) + '</p>' +
      '<a class="cta" href="' + esc(ctaUrl) + '" target="_blank" rel="noopener">' + esc(ctaText) + '</a>' +
      '</div>' +
      '<div class="actions">' +
      '<button class="like" type="button" data-like aria-label="like">' + HEART + '</button>' +
      '<span class="like-count">' + esc(it.likes || '') + '</span>' +
      '<span class="spinner" aria-hidden="true"></span>' +
      '</div>';
    return sec;
  }

  /* ---------------- 交互 ---------------- */
  var soundBtn = document.querySelector('.sound');
  if (soundBtn) {
    soundBtn.addEventListener('click', function () {
      muted = !muted;
      slides().forEach(function (s) {
        var v = s.querySelector('video');
        if (v) v.muted = muted;
      });
      soundBtn.textContent = muted ? '🔇' : '🔊';
    });
  }

  feed.addEventListener('click', function (e) {
    var like = e.target.closest ? e.target.closest('[data-like]') : null;
    if (like) {
      e.preventDefault();
      toast(likeHint);
    }
  });

  /* ---------------- 启动 ---------------- */
  var list = slides();
  list.forEach(observe);
  if (list.length) {
    currentIndex = 0;
    onEnter(0);
  }
})();
