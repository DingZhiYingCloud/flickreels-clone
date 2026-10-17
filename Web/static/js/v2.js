/* ==========================================================================
   V2：手机端竖屏视频流
   - 一屏一支，上下滑动切换（CSS scroll-snap）
   - 进入哪一支就播哪一支，并预取后面 2 支的播放地址
   - 点屏幕播放/暂停；点赞/查看更多集数 → 引导下载 App
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
  var emptyText = feed.dataset.empty || '';
  var moreText = feed.dataset.more || 'More';
  var ctaUrl = feed.dataset.ctaUrl || '#';
  var ctaText = feed.dataset.ctaText || '';

  var nextPage = parseInt(feed.dataset.next, 10) || 2;
  var loadingMore = false;
  var exhausted = false;
  var muted = true;
  var currentIndex = -1;

  var THUMB_SVG =
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M1 21h4V9H1v12zm22-11c0-1.1-.9-2-2-2h-6.31' +
    'l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10c0 1.1.9 2 2 2h9' +
    'c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z"/></svg>';

  var LOCK_SVG =
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2a5 5 0 0 0-5 5v3H6a2 2 0 0 0-2 2v8' +
    'a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8a2 2 0 0 0-2-2h-1V7a5 5 0 0 0-5-5zm-3 8V7a3 3 0 0 1 6 0v3H9z"/></svg>';

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

  /* ---------------- 弹层 ---------------- */
  var likeModal = document.getElementById('like-modal');
  var epSheet = document.getElementById('ep-sheet');
  var sheetBody = document.getElementById('sheet-body');

  function openLikeModal() {
    if (likeModal) likeModal.hidden = false;
  }
  function closeLayer(el) {
    if (el) el.hidden = true;
  }

  [likeModal, epSheet].forEach(function (layer) {
    if (!layer) return;
    layer.addEventListener('click', function (e) {
      var t = e.target;
      if (t && t.hasAttribute && t.hasAttribute('data-close')) closeLayer(layer);
    });
  });

  if (sheetBody) {
    sheetBody.addEventListener('click', function (e) {
      var item = e.target.closest ? e.target.closest('[data-ep]') : null;
      if (item) openLikeModal();
    });
  }

  /* ---------------- 播放/暂停提示 ---------------- */
  var playHint = document.getElementById('play-hint');

  function currentSlide() {
    var list = slides();
    return list[currentIndex] || list[0] || null;
  }

  function updatePlayHint() {
    var s = currentSlide();
    var v = s ? s.querySelector('video') : null;
    if (playHint) playHint.classList.toggle('is-show', !!v && v.paused);
  }

  function togglePlay() {
    var s = currentSlide();
    var v = s ? s.querySelector('video') : null;
    if (!v) return;
    if (v.paused) {
      var p = v.play();
      if (p && p.catch) p.catch(function () {});
    } else {
      v.pause();
    }
    updatePlayHint();
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
        if (d.episodes) slide.dataset.episodes = d.episodes;
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
      updatePlayHint();
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
    updatePlayHint();
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

  /* ---------------- 查看更多集数（全部上锁） ---------------- */
  function openEpisodes() {
    if (!epSheet || !sheetBody) return;
    var slide = currentSlide();
    if (!slide) return;

    function render() {
      var total = parseInt(slide.dataset.episodes || '0', 10) || 0;
      if (!total) {
        toast(emptyText);
        return;
      }
      var html = '';
      for (var i = 1; i <= total; i++) {
        html += '<button class="ep-item" type="button" data-ep="' + i + '">'
          + LOCK_SVG + '<span>' + i + '</span></button>';
      }
      sheetBody.innerHTML = html;
      epSheet.hidden = false;
    }

    if (slide.dataset.episodes) render();
    else ensureLoaded(slide).then(render);
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
      '<div class="meta-actions">' +
      '<a class="cta" href="' + esc(ctaUrl) + '" target="_blank" rel="noopener">' + esc(ctaText) + '</a>' +
      '<button class="more-btn" type="button" data-more>' + esc(moreText) + '</button>' +
      '</div></div>' +
      '<div class="actions">' +
      '<button class="like" type="button" data-like aria-label="like">' + THUMB_SVG + '</button>' +
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
    var t = e.target;
    var like = t.closest ? t.closest('[data-like]') : null;
    if (like) {
      e.preventDefault();
      openLikeModal();
      return;
    }
    var more = t.closest ? t.closest('.more-btn[data-more]') : null;
    if (more) {
      e.preventDefault();
      openEpisodes();
      return;
    }
    if (t.closest && t.closest('a')) return;  // 下载按钮等链接正常跳转
    togglePlay();                              // 其余区域：点击屏幕播放/暂停
  });

  /* ---------------- 启动 ---------------- */
  var list = slides();
  list.forEach(observe);
  if (list.length) {
    currentIndex = 0;
    onEnter(0);
  }
})();
