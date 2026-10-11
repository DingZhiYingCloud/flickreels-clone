/* 首页交互脚本：Hero 轮播（自动播放/箭头/拖拽滑动）、语言下拉、搜索框清空 */
(function () {
  'use strict';

  /* ============ 语言下拉（桌面端与移动端各有一份，需全部绑定） ============ */
  function closeAllLang() {
    document.querySelectorAll('.lang-dropdown').forEach(function (d) {
      d.style.display = 'none';
    });
  }

  function initLangDropdown() {
    document.querySelectorAll('.langs-set').forEach(function (set) {
      var trigger = set.firstElementChild;
      var dropdown = set.querySelector('.lang-dropdown');
      if (!trigger || !dropdown) return;
      trigger.style.cursor = 'pointer';
      trigger.setAttribute('role', 'button');
      trigger.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        var isOpen = dropdown.style.display === 'block';
        closeAllLang();
        dropdown.style.display = isOpen ? 'none' : 'block';
      });
    });
    document.addEventListener('click', closeAllLang);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeAllLang();
    });
  }

  /* ============ 搜索框：清空按钮 + 回车跳转搜索页 ============ */
  function siteLocalePrefix() {
    var m = location.pathname.match(/^\/(ja|ko|es|id|de|th|tc|fr|pt)(\/|$)/);
    return m ? '/' + m[1] : '';
  }

  function initSearch() {
    document.querySelectorAll('.search-clear').forEach(function (box) {
      var input = box.parentElement.querySelector('input');
      if (!input) return;
      var sync = function () {
        box.style.display = input.value ? 'block' : 'none';
      };
      input.addEventListener('input', sync);
      box.addEventListener('click', function () {
        input.value = '';
        sync();
        input.focus();
      });
      // 回车：跳转到搜索页（关键词与源站一致，用 drama 参数）
      input.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter') return;
        var q = (input.value || '').trim();
        if (!q) return;
        e.preventDefault();
        location.href = siteLocalePrefix() + '/search?drama=' + encodeURIComponent(q);
      });
      sync();
    });
  }

  /* ============ 轮播：自动播放 + 左右箭头 + 拖拽/触摸滑动 + 无限循环 ============ */
  function initCarousels() {
    document.querySelectorAll('.swiper').forEach(function (root) {
      var track = root.querySelector('[class*="swiper-track"]');
      if (!track || track.dataset.carouselReady) return;
      var viewport = track.parentElement;
      if (!viewport) return;

      var originals = Array.prototype.slice.call(track.children);
      var n = originals.length;
      if (n < 2) return;
      track.dataset.carouselReady = '1';

      // 首尾各克隆一份，用于无缝无限循环
      var pre = document.createDocumentFragment();
      originals.forEach(function (s) { pre.appendChild(s.cloneNode(true)); });
      track.insertBefore(pre, track.firstChild);
      originals.forEach(function (s) { track.appendChild(s.cloneNode(true)); });

      // 移除源站用于初始定位的类，改由 JS 控制 transform
      track.classList.remove('swiper-track--pc-init', 'swiper-track--mobile-loop-init');
      track.style.transition = 'none';
      track.style.willChange = 'transform';
      if (!viewport.style.cursor) viewport.style.cursor = 'grab';

      var cur = n;         // 当前居中 slide 在 track.children 中的索引
      var offset = 0;      // 当前 translateX(px)
      var dragging = false, startX = 0, startOffset = 0, moved = 0;
      var timer = null;

      function children() { return track.children; }

      function apply() {
        track.style.transform = 'translateX(' + offset + 'px)';
      }

      function animate(on) {
        track.style.transition = on
          ? 'transform .45s cubic-bezier(.22,.61,.36,1)'
          : 'none';
      }

      // 将第 i 个 slide 居中（基于实时位置测算位移，兼容不同断点/内边距）
      function centerOn(i, withAnim) {
        var target = children()[i];
        if (!target) return;
        var vp = viewport.getBoundingClientRect();
        var tr = target.getBoundingClientRect();
        offset += (vp.left + vp.width / 2) - (tr.left + tr.width / 2);
        animate(withAnim);
        apply();
        cur = i;
      }

      // 循环边界处理：动画结束后若处于克隆区，瞬移回真实区
      track.addEventListener('transitionend', function () {
        if (cur < n) { animate(false); centerOn(cur + n, false); }
        else if (cur >= 2 * n) { animate(false); centerOn(cur - n, false); }
        animate(false);
      });

      function step() {
        var st = getComputedStyle(track);
        var gap = parseFloat(st.columnGap || st.gap) || 0;
        var w = children()[0].getBoundingClientRect().width;
        return w + gap;
      }

      function go(dir) {
        centerOn(cur + dir, true);
      }

      // 箭头
      root.querySelectorAll('svg').forEach(function (svg) {
        var use = svg.querySelector('use');
        if (!use) return;
        var href = use.getAttribute('xlink:href') || use.getAttribute('href') || '';
        var btn = svg.parentElement;
        if (!btn) return;
        btn.style.cursor = 'pointer';
        btn.dataset.carouselArrow = '1';   // 供拖拽逻辑识别，避免抢事件
        if (href.indexOf('left1') >= 0) {
          btn.addEventListener('click', function (e) { e.stopPropagation(); go(-1); startAuto(); });
        } else if (href.indexOf('right1') >= 0) {
          btn.addEventListener('click', function (e) { e.stopPropagation(); go(1); startAuto(); });
        }
      });

      // 拖拽 / 触摸滑动
      viewport.addEventListener('pointerdown', function (e) {
        if (e.button !== undefined && e.button !== 0) return;
        // 点在左右切换箭头上时不进入拖拽、不捕获指针，否则 click 会被吞掉
        if (e.target && e.target.closest && e.target.closest('[data-carousel-arrow]')) return;
        dragging = true;
        moved = 0;
        startX = e.clientX;
        startOffset = offset;
        animate(false);
        stopAuto();
        viewport.style.cursor = 'grabbing';
        try { viewport.setPointerCapture(e.pointerId); } catch (err) {}
      });

      viewport.addEventListener('pointermove', function (e) {
        if (!dragging) return;
        var dx = e.clientX - startX;
        moved = Math.max(moved, Math.abs(dx));
        offset = startOffset + dx;
        apply();
      });

      function endDrag() {
        if (!dragging) return;
        dragging = false;
        viewport.style.cursor = 'grab';
        var dx = offset - startOffset;
        var steps = 0;
        // 拖动超过 40px 即视为翻页意图，至少移动一屏
        if (Math.abs(dx) > 40) {
          steps = Math.round(-dx / step());
          if (steps === 0) steps = dx < 0 ? 1 : -1;
        }
        animate(true);
        centerOn(cur + steps, true);
        startAuto();
      }
      viewport.addEventListener('pointerup', endDrag);
      viewport.addEventListener('pointercancel', endDrag);
      viewport.addEventListener('pointerleave', endDrag);

      // 拖拽后抑制误触发的链接点击
      track.addEventListener('click', function (e) {
        if (moved > 6) { e.preventDefault(); e.stopPropagation(); }
      }, true);

      // 自动播放
      function startAuto() { stopAuto(); timer = setInterval(function () { go(1); }, 4500); }
      function stopAuto() { if (timer) { clearInterval(timer); timer = null; } }
      viewport.addEventListener('mouseenter', stopAuto);
      viewport.addEventListener('mouseleave', startAuto);
      document.addEventListener('visibilitychange', function () {
        if (document.hidden) { stopAuto(); } else { startAuto(); }
      });

      // 初始化：无动画居中到第一个真实 slide（与源站初始位置一致）
      track.style.transform = 'translateX(0px)';
      offset = 0;
      centerOn(n, false);
      startAuto();

      // 视口尺寸变化（换断点/旋转屏幕）时重新居中
      var resizeTimer = null;
      window.addEventListener('resize', function () {
        if (resizeTimer) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
          animate(false);
          centerOn(cur, false);
        }, 150);
      });
    });
  }

  function boot() {
    initLangDropdown();
    initSearch();
    initCarousels();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
