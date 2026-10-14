/* 短剧播放页：使用 hls.js 驱动 m3u8 播放（Safari 走原生 HLS） */
(function () {
  'use strict';

  function initPlayer() {
    var video = document.querySelector('video[data-hls]');
    if (!video) return;
    var src = video.getAttribute('data-hls');
    if (!src) return;

    var Hls = window.Hls;
    if (Hls && Hls.isSupported()) {
      var hls = new Hls({ enableWorker: true });
      hls.loadSource(src);
      hls.attachMedia(video);
      hls.on(Hls.Events.ERROR, function (evt, data) {
        if (!data || !data.fatal) return;
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          hls.startLoad();          // 网络错误：尝试重新加载
        } else if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();  // 媒体错误：尝试恢复
        } else {
          hls.destroy();
        }
      });
      video._hls = hls;
    } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
      // Safari 等原生支持 HLS 的浏览器
      video.src = src;
    }
  }

  /* 点赞：点击后弹出"需先下载 APP 才能点赞"的提示弹窗 */
  function initLike() {
    var modal = document.querySelector('[data-like-modal]');
    if (!modal) return;
    var close = function () { modal.style.display = 'none'; };
    document.querySelectorAll('[data-like-btn]').forEach(function (btn) {
      btn.addEventListener('click', function () { modal.style.display = 'flex'; });
    });
    modal.addEventListener('click', function (e) {
      if (e.target === modal || (e.target.closest && e.target.closest('[data-like-close]'))) {
        close();
      }
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });
  }

  function boot() {
    initPlayer();
    initLike();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
