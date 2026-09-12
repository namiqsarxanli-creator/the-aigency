/* Fon videolarını GEC yükləyir — panel keçidlərindəki gecikmənin kök səbəbi bu idi.
 *
 * PROBLEM (canlı tapıntı): hər səhifədə 12–40 MB-lıq CloudFront fon videosu `autoplay` ilə
 * dərhal yüklənməyə başlayırdı. Server cavabı 8–28 ms olsa da, brauzer video baytlarını
 * çəkərkən səhifə "gec açılırdı", animasiyalar gec görünürdü.
 *
 * HƏLL: `<video data-src="...">` — mənbə YALNIZ video ekrana yaxınlaşanda təyin olunur.
 * Eyni yanaşma `control-room-space.js`-də artıq işləyirdi; bu fayl onu bütün panellərə yayır.
 *
 * SƏHNƏ QRUPLARI (məs. sales.html-dəki fon seçimi): eyni anda 4 video ekranda olur, amma
 * yalnız `.active` olanı yüklənir — qalanları istifadəçi həmin səhnəyə keçəndə (class dəyişəndə).
 */
(function () {
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');

  function load(video) {
    if (!video || video.dataset.lazyLoaded || !video.dataset.src) return;
    video.dataset.lazyLoaded = '1';
    video.src = video.dataset.src;
    video.load();
    if (video.autoplay && !(reduce && reduce.matches)) video.play().catch(function () {});
  }
  // Səhifəyə məxsus skriptlər (məs. sales-lumora.js) lazım olsa özləri də çağıra bilsin.
  window.lazyVideoLoad = load;

  function isSceneMember(v) {
    return v.hasAttribute('data-scene-video') || v.hasAttribute('data-media');
  }

  var videos = [].slice.call(document.querySelectorAll('video[data-src]'));
  if (!videos.length) return;

  if (!('IntersectionObserver' in window)) {
    videos.forEach(load);
    return;
  }

  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      var v = entry.target;
      if (!entry.isIntersecting) {
        if (v.dataset.lazyLoaded) v.pause();
        return;
      }
      if (!isSceneMember(v) || v.classList.contains('active')) load(v);
      if (v.dataset.lazyLoaded && v.autoplay && !(reduce && reduce.matches)) {
        v.play().catch(function () {});
      }
    });
  }, { rootMargin: '200px' });

  videos.forEach(function (v) { io.observe(v); });

  // Səhnə dəyişəndə yeni aktiv video yüklənsin (sales.html-dəki "Golden Hour / Still Water" düymələri).
  if ('MutationObserver' in window) {
    var mo = new MutationObserver(function (mutations) {
      mutations.forEach(function (m) {
        if (m.target.classList && m.target.classList.contains('active')) load(m.target);
      });
    });
    videos.filter(isSceneMember).forEach(function (v) {
      mo.observe(v, { attributes: true, attributeFilter: ['class'] });
    });
  }
})();
