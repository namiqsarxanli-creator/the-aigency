(() => {
  const hero = document.querySelector('.production-hero');
  if (!hero) return;
  const video = hero.querySelector('video');
  const buttons = [...hero.querySelectorAll('.production-scenes button')];
  const pause = hero.querySelector('.production-pause');
  const note = hero.querySelector('.production-media-note');
  const heading = hero.querySelector('.production-heading');
  const kicker = hero.querySelector('[data-production-kicker]');
  const title = hero.querySelector('[data-production-title]');
  const link = hero.querySelector('[data-production-link]');
  const sources = [
    '/static/media/campaigns/scene-01.mp4',
    '/static/media/campaigns/scene-02.mp4',
    '/static/media/campaigns/scene-03.mp4'
  ];
  // Poster kadrı: video yüklənənə qədər ekran boş qalmasın. Server sürəti məhdud olduğu üçün
  // 2 MB-lıq video bir neçə saniyə çəkir — poster (≈30 KB) dərhal görünür.
  const posters = [
    '/static/media/campaigns/scene-01.jpg',
    '/static/media/campaigns/scene-02.jpg',
    '/static/media/campaigns/scene-03.jpg'
  ];
  const copy = [
    ['KAMPANİYALAR / THE AIGENCY', 'FİKİRDƏN<br>KAMPANİYAYA.', 'Planını qur. Hekayəni başlat. ↗'],
    ['STRATEGİYA / İCRA', 'PLANLA.<br>YAYIMLA. ÖLÇ.', '7 günlük axını yarat. ↗'],
    ['NƏTİCƏ / DAVAM', 'BİR MESAJ.<br>BÜTÖV SİSTEM.', 'Kampaniyalarını kəşf et. ↗']
  ];
  let index = 0, stopped = matchMedia('(prefers-reduced-motion: reduce)').matches, visible = true;
  function sync() {
    pause.textContent = stopped ? 'Videonu oynat ▷' : 'Videonu dayandır Ⅱ';
    if (stopped || !visible || document.hidden) video.pause();
    else video.play().catch(() => { stopped = true; pause.textContent = 'Videonu oynat ▷'; });
  }
  function select(i) {
    index = i; note.hidden = true; video.classList.remove('is-ready');
    buttons.forEach((button, j) => button.setAttribute('aria-pressed', String(j === i)));
    heading.classList.add('is-changing');
    window.setTimeout(() => {
      kicker.textContent = copy[i][0]; title.innerHTML = copy[i][1]; link.textContent = copy[i][2];
      heading.classList.remove('is-changing');
    }, 260);
    video.poster = posters[i]; video.src = sources[i]; video.load();
  }
  video.addEventListener('loadeddata', () => { video.classList.add('is-ready'); sync(); });
  video.addEventListener('error', () => { note.hidden = false; });
  buttons.forEach((button, i) => button.addEventListener('click', () => select(i)));
  pause.addEventListener('click', () => { stopped = !stopped; sync(); });
  document.addEventListener('visibilitychange', sync);
  new IntersectionObserver(entries => { visible = entries[0].isIntersecting; sync(); }, {threshold: .1}).observe(hero);
  setInterval(() => { if (!stopped && visible && !document.hidden && video.readyState >= 2) select((index + 1) % sources.length); }, 14000);
  const planner = document.querySelector('.cp-page');
  planner.id = 'campaignPlanner';
  document.querySelectorAll('.cp-list a').forEach(a => { a.hash = 'campaignPlanner'; });
  if (location.search || location.hash === '#campaignPlanner') requestAnimationFrame(() => planner.scrollIntoView());
  select(0);
})();
