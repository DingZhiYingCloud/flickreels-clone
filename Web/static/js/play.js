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

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPlayer);
  } else {
    initPlayer();
  }
})();
