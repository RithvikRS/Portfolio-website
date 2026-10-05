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

document.querySelectorAll('.copy-email').forEach(button => {
  button.hidden = false;
  button.addEventListener('click', async () => {
    const status = document.querySelector('.copy-status');
    try {
      await navigator.clipboard.writeText(button.dataset.email);
      status.textContent = 'Email address copied.';
    } catch {
      status.textContent = `Copy this address: ${button.dataset.email}`;
    }
  });
});
document.querySelectorAll('[data-year]').forEach(element => { element.textContent = String(new Date().getFullYear()); });
