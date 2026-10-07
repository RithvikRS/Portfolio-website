const menuButton = document.querySelector('.menu-toggle');
const navigation = document.querySelector('#primary-nav');
if (menuButton && navigation) {
  menuButton.hidden = false;
  const closeMenu = () => {
    menuButton.setAttribute('aria-expanded', 'false');
    navigation.classList.remove('is-open');
  };
  menuButton.addEventListener('click', () => {
    const open = menuButton.getAttribute('aria-expanded') !== 'true';
    menuButton.setAttribute('aria-expanded', String(open));
    navigation.classList.toggle('is-open', open);
  });
  navigation.addEventListener('click', event => { if (event.target.closest('a')) closeMenu(); });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') {
      closeMenu(); menuButton.focus();
    }
  });
  document.addEventListener('click', event => { if (!event.target.closest('.site-header')) closeMenu(); });
  const mobile = window.matchMedia('(max-width: 860px)');
  mobile.addEventListener('change', closeMenu);
  document.documentElement.classList.add('has-js');
}

const sectionLinks = [...document.querySelectorAll('[data-section]')];
if ('IntersectionObserver' in window && sectionLinks.length) {
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        for (const link of sectionLinks) {
          if (link.dataset.section === entry.target.id) link.setAttribute('aria-current', 'location');
          else link.removeAttribute('aria-current');
        }
      } else {
        sectionLinks.find(link => link.dataset.section === entry.target.id)?.removeAttribute('aria-current');
      }
    }
  }, { rootMargin: '-20% 0px -55% 0px', threshold: 0 });
  sectionLinks.forEach(link => { const section = document.getElementById(link.dataset.section); if (section) observer.observe(section); });
}

const projectTools = document.querySelector('.project-tools');
if (projectTools) {
  const cards = [...document.querySelectorAll('.archive-card')];
  const filterButtons = [...document.querySelectorAll('[data-filter]')];
  const search = projectTools.querySelector('input');
  const count = document.querySelector('.project-count');
  const empty = document.querySelector('.empty-state');
  let category = 'All work';
  function filterProjects() {
    const query = search.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const card of cards) {
      const matches = (category === 'All work' || card.dataset.category === category) && card.textContent.toLocaleLowerCase().includes(query);
      card.hidden = !matches;
      if (matches) visible++;
    }
    count.textContent = `${visible} ${visible === 1 ? 'project' : 'projects'}${query || category !== 'All work' ? ' found' : ''}`;
    empty.hidden = visible !== 0;
    filterButtons.forEach(button => {
      const active = button.dataset.filter === category;
      button.classList.toggle('is-active', active);
      button.setAttribute('aria-pressed', String(active));
    });
  }
  filterButtons.forEach(button => button.addEventListener('click', () => { category = button.dataset.filter; filterProjects(); }));
  search.addEventListener('input', filterProjects);
  document.querySelector('[data-reset-filters]').addEventListener('click', () => {
    category = 'All work'; search.value = ''; filterProjects(); search.focus();
  });
  function revealLinkedProject() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const card = cards.find(item => item.id === id);
    if (card) {
      category = 'All work'; search.value = ''; filterProjects();
      card.querySelector('details').open = true;
      requestAnimationFrame(() => card.scrollIntoView({ block: 'start' }));
    }
  }
  projectTools.hidden = false;
  revealLinkedProject();
  window.addEventListener('hashchange', revealLinkedProject);
}

document.querySelectorAll('[data-year]').forEach(element => { element.textContent = String(new Date().getFullYear()); });

const motionPreference = window.matchMedia('(prefers-reduced-motion: reduce)');
const motionToggle = document.querySelector('.motion-toggle');
let motionPaused = false;
let printing = false;
let syncMotionEffects = () => {};
const motionEase = 'cubic-bezier(.22,1,.36,1)';
try { motionPaused = localStorage.getItem('portfolio-motion') === 'off'; } catch { /* Storage is optional. */ }
const motionEnabled = () => !motionPaused && !motionPreference.matches && !printing;
const activeAnimations = new Map();
const cancelAnimations = () => {
  for (const animation of activeAnimations.keys()) animation.cancel();
  activeAnimations.clear();
};
const animate = (element, frames, options) => {
  if (!element || !motionEnabled() || typeof element.animate !== 'function') return;
  const animation = element.animate(frames, options);
  activeAnimations.set(animation, element);
  const cleanup = () => activeAnimations.delete(animation);
  animation.finished.then(cleanup, cleanup);
};
function updateMotion() {
  const enabled = motionEnabled();
  document.documentElement.classList.toggle('motion-off', !enabled);
  if (motionToggle) {
    motionToggle.hidden = false;
    motionToggle.textContent = enabled ? 'Motion on' : 'Motion off';
    motionToggle.setAttribute('aria-pressed', String(enabled));
    motionToggle.setAttribute('aria-label', 'Website animations');
    motionToggle.disabled = motionPreference.matches;
    motionToggle.title = motionPreference.matches ? 'Reduced motion follows your device setting' : 'Toggle website animations';
  }
  if (!enabled) {
    cancelAnimations();
  }
  syncMotionEffects();
}
motionToggle?.addEventListener('click', () => {
  motionPaused = !motionPaused;
  try { localStorage.setItem('portfolio-motion', motionPaused ? 'off' : 'on'); } catch { /* Storage is optional. */ }
  updateMotion();
});
motionPreference.addEventListener('change', updateMotion);
window.addEventListener('beforeprint', () => { printing = true; updateMotion(); });
window.addEventListener('afterprint', () => { printing = false; updateMotion(); });
window.addEventListener('pageshow', event => { if (event.persisted) cancelAnimations(); });
document.addEventListener('focusin', event => {
  for (const [animation, element] of activeAnimations) {
    if (element.contains(event.target)) animation.cancel();
  }
});
updateMotion();

const dialog = document.querySelector('.contact-dialog');
if (dialog && typeof dialog.showModal === 'function') {
  const form = dialog.querySelector('form');
  const status = dialog.querySelector('.form-status');
  const submit = form.querySelector('[type="submit"]');
  const submitLabel = submit.querySelector('.submit-label');
  const success = dialog.querySelector('.form-success');
  const fields = ['name', 'email', 'subject', 'message', 'website'];
  let opener;
  let available = false;
  let sending = false;
  let sent = false;
  let requestId;
  let availabilityCheck = 0;
  const setStatus = (message, error = false) => {
    status.textContent = message;
    status.classList.toggle('is-error', error);
  };
  async function checkAvailability() {
    const check = ++availabilityCheck;
    available = false;
    submit.disabled = true;
    setStatus('Checking message availability…');
    try {
      const response = await fetch(form.dataset.endpoint, { headers: { Accept: 'application/json' }, signal: AbortSignal.timeout(8000) });
      const result = await response.json();
      if (check !== availabilityCheck) return;
      available = response.ok && result.available === true;
    } catch { if (check !== availabilityCheck) return; }
    submit.disabled = !available;
    setStatus(available ? '' : 'Messaging is temporarily unavailable. Please connect on LinkedIn.', !available);
  }
  document.querySelectorAll('[data-open-contact]').forEach(button => {
    button.hidden = false;
    button.addEventListener('click', () => {
      opener = button;
      dialog.showModal();
      document.body.classList.add('dialog-open');
      (sent ? success : form.elements.name).focus({ preventScroll: true });
      animate(dialog, [{ opacity: 0, transform: 'translate3d(0,10px,0)' }, { opacity: 1, transform: 'translate3d(0,0,0)' }], { duration: 420, easing: motionEase });
      if (!sending && !sent) checkAvailability();
    });
  });
  dialog.querySelectorAll('.dialog-close, [data-close-contact]').forEach(button => button.addEventListener('click', () => dialog.close()));
  dialog.addEventListener('keydown', event => {
    if (event.key !== 'Tab') return;
    const controls = [...dialog.querySelectorAll('button, a[href], input, textarea, [tabindex]')]
      .filter(element => !element.disabled && element.tabIndex >= 0 && element.getClientRects().length);
    const first = controls[0];
    const last = controls.at(-1);
    if (event.shiftKey && (document.activeElement === first || document.activeElement === success)) {
      event.preventDefault(); last?.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault(); first?.focus();
    }
  });
  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
  dialog.addEventListener('close', () => {
    document.body.classList.remove('dialog-open');
    opener?.focus({ preventScroll: true });
  });
  form.addEventListener('input', () => {
    requestId = undefined;
    dialog.querySelector('.message-count').textContent = `${form.elements.message.value.length.toLocaleString()} / 5,000`;
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (sending || !available || !form.reportValidity()) return;
    requestId ||= crypto.randomUUID();
    const payload = Object.fromEntries(fields.map(name => [name, form.elements[name].value]));
    payload.requestId = requestId;
    sending = true;
    submit.disabled = true;
    submitLabel.textContent = 'Sending…';
    form.setAttribute('aria-busy', 'true');
    fields.forEach(name => { form.elements[name].readOnly = true; });
    setStatus('Sending your message…');
    try {
      const response = await fetch(form.dataset.endpoint, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
        body: JSON.stringify(payload), signal: AbortSignal.timeout(45000)
      });
      const result = await response.json();
      if (!response.ok || result.ok !== true) {
        setStatus(result.error || 'Delivery could not be confirmed. Please try again later or connect on LinkedIn.', true);
        return;
      }
      sent = true;
      form.reset();
      form.hidden = true;
      dialog.querySelector('.form-heading').hidden = true;
      dialog.setAttribute('aria-labelledby', 'form-success-title');
      dialog.setAttribute('aria-describedby', 'form-success-description');
      success.hidden = false;
      if (dialog.open) success.focus({ preventScroll: true });
      animate(success.querySelector('.success-mark'), [{ opacity: 0, transform: 'scale(.9)' }, { opacity: 1, transform: 'scale(1)' }], { duration: 520, easing: motionEase });
    } catch {
      setStatus('Delivery could not be confirmed. Your draft is still here. Please try again later or connect on LinkedIn.', true);
    } finally {
      sending = false;
      form.removeAttribute('aria-busy');
      fields.forEach(name => { form.elements[name].readOnly = false; });
      submitLabel.textContent = 'Send message';
      submit.disabled = !available;
    }
  });
}

// One frame scheduler owns the illustration transform. Time-based damping stays
// consistent across refresh rates and stops once the illustration settles.
const progress = document.querySelector('.reading-progress');
const heroArt = document.querySelector('.hero-art');
const diagram = heroArt?.querySelector('.system-diagram');
const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
let motionFrame = 0;
let lastFrameTime = 0;
let scrollDistance = 1;
let heroBounds;
const current = { x: 0, y: 0, travel: 0 };
const target = { x: 0, y: 0, travel: 0 };
const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
function scheduleMotion() {
  if (!motionFrame && motionEnabled() && !document.hidden) motionFrame = requestAnimationFrame(renderMotion);
}
function renderMotion(time) {
  motionFrame = 0;
  if (!motionEnabled() || document.hidden) return;
  if (progress) progress.style.transform = `scaleX(${clamp(window.scrollY / scrollDistance, 0, 1)})`;
  if (!diagram || !heroBounds) return;
  const visible = heroBounds.top - window.scrollY < window.innerHeight && heroBounds.bottom > window.scrollY;
  if (!visible) {
    current.x = current.y = current.travel = target.x = target.y = target.travel = 0;
    diagram.style.removeProperty('transform');
    diagram.style.removeProperty('will-change');
    lastFrameTime = 0;
    return;
  }
  // Keep the scroll movement small, especially on narrow screens.
  target.travel = clamp((window.scrollY - Math.max(0, heroBounds.top - 100)) / heroBounds.height, 0, 1) * (window.innerWidth < 600 ? 9 : 18);
  const elapsed = lastFrameTime ? Math.min(time - lastFrameTime, 64) : 16.67;
  lastFrameTime = time;
  const blend = 1 - Math.exp(-elapsed / 100);
  let moving = false;
  for (const key of Object.keys(current)) {
    current[key] += (target[key] - current[key]) * blend;
    if (Math.abs(target[key] - current[key]) < .015) current[key] = target[key];
    else moving = true;
  }
  diagram.style.transform = `perspective(900px) translate3d(0,${current.travel.toFixed(3)}px,0) rotateX(${current.x.toFixed(3)}deg) rotateY(${current.y.toFixed(3)}deg)`;
  if (moving) {
    diagram.style.willChange = 'transform';
    scheduleMotion();
  } else {
    diagram.style.removeProperty('will-change');
    lastFrameTime = 0;
  }
}
function measureMotion() {
  scrollDistance = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
  if (heroArt) {
    const bounds = heroArt.getBoundingClientRect();
    heroBounds = { left: bounds.left, top: bounds.top + window.scrollY, bottom: bounds.bottom + window.scrollY, width: bounds.width, height: bounds.height };
  }
  scheduleMotion();
}
syncMotionEffects = () => {
  cancelAnimationFrame(motionFrame);
  motionFrame = lastFrameTime = 0;
  current.x = current.y = current.travel = target.x = target.y = target.travel = 0;
  diagram?.style.removeProperty('transform');
  diagram?.style.removeProperty('will-change');
  if (motionEnabled() && !document.hidden) measureMotion();
};
window.addEventListener('scroll', scheduleMotion, { passive: true });
window.addEventListener('resize', measureMotion);
window.addEventListener('pageshow', syncMotionEffects);
document.addEventListener('visibilitychange', syncMotionEffects);
finePointer.addEventListener('change', syncMotionEffects);
if ('ResizeObserver' in window) new ResizeObserver(measureMotion).observe(document.body);
heroArt?.addEventListener('pointermove', event => {
  if (!motionEnabled() || !finePointer.matches || event.pointerType === 'touch' || !heroBounds) return;
  target.x = -clamp((event.clientY + window.scrollY - heroBounds.top) / heroBounds.height - .5, -.5, .5) * 4;
  target.y = clamp((event.clientX - heroBounds.left) / heroBounds.width - .5, -.5, .5) * 4;
  scheduleMotion();
});
heroArt?.addEventListener('pointerleave', () => { target.x = target.y = 0; scheduleMotion(); });
measureMotion();

// Animate visible content without hiding it in CSS: no-JS, print, and failures
// leave the portfolio readable. Reveal sections just before they enter view.
if ('IntersectionObserver' in window && typeof Element.prototype.animate === 'function') {
  const isLinkedTarget = element => {
    let target;
    try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch { return false; }
    return target && (element.contains(target) || target.contains(element));
  };
  const reveal = (element, delay = 0, duration = 760) => animate(element, [
    { opacity: 0, transform: 'translate3d(0,12px,0)' },
    { opacity: 1, transform: 'translate3d(0,0,0)' }
  ], { duration, delay, easing: motionEase, fill: 'backwards' });
  const freshVisit = !location.hash && window.scrollY < 10;
  const startupElements = new Set();
  const introduce = (element, delay, duration = 800) => {
    if (!element) return;
    startupElements.add(element);
    reveal(element, delay, duration);
  };
  if (freshVisit) {
    // The name leads, then the headline lines and supporting details follow.
    // No overlay or scroll lock: links can be used throughout the introduction.
    introduce(document.querySelector('.brand'), 0, 650);
    animate(navigation, [{ opacity: 0 }, { opacity: 1 }], { delay: 160, duration: 650, easing: motionEase, fill: 'backwards' });
    animate(menuButton, [{ opacity: 0 }, { opacity: 1 }], { delay: 160, duration: 650, easing: motionEase, fill: 'backwards' });
    introduce(document.querySelector('.hero-copy > .eyebrow'), 100, 700);
    introduce(document.querySelector('.hello'), 180, 750);
    document.querySelectorAll('.headline-text').forEach((line, index) => {
      animate(line, [
        { opacity: 0, transform: 'translate3d(0,105%,0)' },
        { opacity: 1, transform: 'translate3d(0,0,0)' }
      ], { delay: 240 + index * 140, duration: 1000, easing: motionEase, fill: 'backwards' });
    });
    introduce(document.querySelector('.hero-description'), 480);
    introduce(document.querySelector('.hero-actions'), 600);
    // Inner pages use the same rhythm without replaying a full-page transition.
    const intro = document.querySelector('.page-intro');
    if (intro) {
      startupElements.add(intro);
      [...intro.children].forEach((element, index) => introduce(element, 100 + index * 90));
    }
  }
  let heroRevealed = !freshVisit;
  const revealHero = () => {
    if (!heroArt || heroRevealed) return;
    heroRevealed = true;
    animate(heroArt, [{ opacity: 0 }, { opacity: 1 }], { duration: 1000, delay: 260, easing: motionEase, fill: 'backwards' });
    animate(heroArt.querySelector('.diagram-stage'), [
      { transform: 'translate3d(0,20px,0) scale(.94)' },
      { transform: 'translate3d(0,0,0) scale(1)' }
    ], { duration: 1150, delay: 300, easing: motionEase, fill: 'backwards' });
  };
  const entranceTargets = [...document.querySelectorAll([
    '.hero-art', '.section-heading', '.about-copy',
    '.section-title-row', '.experience-item', '.project-card', '.skill-column',
    '.credential-row', '.education-main', '.community-grid > div', '.contact-inner > div',
    '.page-intro', '.recognition-card', '.education-history > article'
  ].join(','))];
  // Stagger siblings in the same row, with no separate animations on their tags.
  const positions = new Map();
  for (const element of entranceTargets) {
    const siblings = entranceTargets.filter(target => target.parentElement === element.parentElement);
    positions.set(element, Math.min(siblings.indexOf(element), 2));
  }
  const entrances = new IntersectionObserver(entries => {
    for (const { target, isIntersecting } of entries) {
      if (!isIntersecting) continue;
      entrances.unobserve(target);
      if (startupElements.has(target) || isLinkedTarget(target) || target.contains(document.activeElement)) continue;
      if (target === heroArt) { revealHero(); continue; }
      reveal(target, positions.get(target) * 60);
    }
  }, { threshold: 0, rootMargin: '0px 0px 80px 0px' });
  entranceTargets.forEach(element => entrances.observe(element));
}
