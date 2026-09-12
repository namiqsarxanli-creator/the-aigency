(() => {
  const stage = document.querySelector('.ocean-stage');
  if (!stage || matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  const swimmers = [];

  function buildSwimmer(selector, kind) {
    const shell = stage.querySelector(selector);
    const image = shell?.querySelector('img');
    if (!shell || !image) return;
    const canvas = document.createElement('canvas');
    canvas.className = 'ocean-creature-canvas';
    canvas.setAttribute('aria-hidden', 'true');
    shell.appendChild(canvas);

    const prepare = () => {
      const maxWidth = kind === 'whale' ? 1280 : 960;
      canvas.width = Math.min(image.naturalWidth, maxWidth);
      canvas.height = Math.round(canvas.width * image.naturalHeight / image.naturalWidth);
      shell.classList.add('canvas-ready');
      swimmers.push({ kind, image, canvas, context: canvas.getContext('2d', { alpha: true }), pointerX: 0, pointerY: 0, targetX: 0, targetY: 0 });
    };
    if (image.complete && image.naturalWidth) prepare();
    else image.addEventListener('load', prepare, { once: true });
  }

  buildSwimmer('.whale-swim', 'whale');
  buildSwimmer('.manta-swim', 'manta');

  function drawWhale(swimmer, time) {
    const { context: ctx, canvas, image } = swimmer;
    const width = canvas.width;
    const height = canvas.height;
    const slices = 92;
    const sliceWidth = width / slices;
    const sourceWidth = image.naturalWidth / slices;
    const breath = Math.sin(time * 0.72) * 1.6;
    ctx.clearRect(0, 0, width, height);

    for (let index = 0; index < slices; index += 1) {
      const progress = index / (slices - 1);
      const tail = Math.pow(Math.max(0, (progress - 0.42) / 0.58), 1.65);
      const body = Math.pow(progress, 1.15);
      const propulsion = Math.sin(time * 1.72 + progress * 7.4) * tail * 27;
      const current = Math.sin(time * 0.58 + progress * 2.5) * body * 5;
      const y = propulsion + current + breath * (0.2 + body * 0.8);
      const stretch = 1 + Math.cos(time * 1.72 + progress * 7.4) * tail * 0.018;
      ctx.drawImage(image, index * sourceWidth, 0, sourceWidth + 1.5, image.naturalHeight, index * sliceWidth - 0.5, y - height * (stretch - 1) / 2, sliceWidth + 1.5, height * stretch);
    }
  }

  function drawManta(swimmer, time) {
    const { context: ctx, canvas, image } = swimmer;
    const width = canvas.width;
    const height = canvas.height;
    const slices = 88;
    const sliceWidth = width / slices;
    const sourceWidth = image.naturalWidth / slices;
    const wingBeat = Math.sin(time * 2.35);
    const recovery = Math.sin(time * 1.16 + 0.8) * 2.5;
    ctx.clearRect(0, 0, width, height);

    for (let index = 0; index < slices; index += 1) {
      const progress = index / (slices - 1);
      const distanceFromBody = Math.min(1, Math.abs(progress - 0.61) / 0.61);
      const wing = Math.pow(distanceFromBody, 1.45);
      const ripple = Math.sin(time * 2.35 - progress * 1.5);
      const y = wingBeat * wing * 25 + ripple * wing * 6 + recovery * progress;
      const stretch = 1 - wingBeat * wing * 0.035;
      ctx.drawImage(image, index * sourceWidth, 0, sourceWidth + 1.5, image.naturalHeight, index * sliceWidth - 0.5, y - height * (stretch - 1) / 2, sliceWidth + 1.5, height * stretch);
    }
  }

  addEventListener('pointermove', event => {
    const x = event.clientX / innerWidth - 0.5;
    const y = event.clientY / innerHeight - 0.5;
    swimmers.forEach(swimmer => {
      const strength = swimmer.kind === 'whale' ? 18 : -28;
      swimmer.targetX = x * strength;
      swimmer.targetY = y * strength * 0.67;
    });
  }, { passive: true });

  function animate(now) {
    const time = now / 1000;
    swimmers.forEach(swimmer => {
      swimmer.pointerX += (swimmer.targetX - swimmer.pointerX) * 0.035;
      swimmer.pointerY += (swimmer.targetY - swimmer.pointerY) * 0.035;
      swimmer.canvas.style.transform = `translate3d(${swimmer.pointerX}px, ${swimmer.pointerY}px, 0)`;
      if (swimmer.kind === 'whale') drawWhale(swimmer, time);
      else drawManta(swimmer, time);
    });
    requestAnimationFrame(animate);
  }

  requestAnimationFrame(animate);
})();
