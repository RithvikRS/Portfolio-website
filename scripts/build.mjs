import { readFile, writeFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const p = JSON.parse(await readFile(new URL('data/portfolio.json', root), 'utf8'));
const e = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const arrow = '<span aria-hidden="true">↗</span>';
const external = (url, label, cls = 'text-link') => `<a class="${cls}" href="${e(url)}" target="_blank" rel="noopener noreferrer">${label} ${arrow}</a>`;
const tags = items => `<ul class="tags">${items.map(item => `<li>${e(item)}</li>`).join('')}</ul>`;
const cv = (cls = 'button button-outline', label = 'Download CV') => `<a class="${cls}" href="${e(p.cv)}" download>${label} <span aria-hidden="true">↓</span></a>`;

function header(page) {
  return `<a class="skip-link" href="#main">Skip to content</a>
  <header class="site-header"><div class="shell header-inner">
    <a class="brand" href="index.html" aria-label="Rithvik — home"><span class="brand-mark" aria-hidden="true">r<span>.</span></span><span>rithvik<span class="brand-dot">.</span></span></a>
    <button class="menu-toggle" aria-expanded="false" aria-controls="primary-nav" hidden>Menu <span aria-hidden="true">☰</span></button>
    <nav id="primary-nav" aria-label="Main navigation">
      <a href="index.html#about" ${page === 'home' ? 'data-section="about"' : ''}>About</a>
      <a href="index.html#experience" ${page === 'home' ? 'data-section="experience"' : ''}>Experience</a>
      <a href="${page === 'home' ? '#projects' : 'Projects.html'}" ${page === 'projects' ? 'aria-current="page"' : page === 'home' ? 'data-section="projects"' : ''}>Projects</a>
      <a href="Awards.html" ${page === 'awards' ? 'aria-current="page"' : ''}>Credentials</a>
      <a href="#contact">Contact</a>
      ${cv('nav-cv')}
    </nav>
  </div></header>`;
}

function footer() {
  return `<section class="contact-section" id="contact" aria-labelledby="contact-title"><div class="shell contact-inner">
    <div><p class="eyebrow light">Have something in mind?</p><h2 id="contact-title">Let’s build something<br><span>that matters.</span></h2><p>For engineering opportunities, collaborations,<br class="desktop-break"> or a conversation about what comes next.</p></div>
    <div class="contact-actions"><a class="email-link" href="mailto:${e(p.email)}">${e(p.email)} ${arrow}</a><div class="contact-links">${external(p.linkedin, 'LinkedIn')}${external(p.github, 'GitHub')}<button class="copy-email" data-email="${e(p.email)}" hidden>Copy email <span aria-hidden="true">⧉</span></button></div><p class="copy-status" role="status" aria-live="polite"></p></div>
  </div></section>
  <footer class="site-footer shell"><p>© <span data-year>${new Date().getFullYear()}</span> ${e(p.name)}</p><p>Built with care. Always evolving.</p><a href="#top">Back to top <span aria-hidden="true">↑</span></a></footer>`;
}

function document(page, title, description, body) {
  body = body.replaceAll('<br>', '<br> ');
  const file = { home: '', projects: 'Projects.html', awards: 'Awards.html', error: '404.html' }[page];
  return `<!doctype html>
<html lang="en" id="top">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#f7f8f2">
  <meta name="description" content="${e(description)}">
  <title>${e(title)}</title>
  <link rel="icon" href="images/favicon.svg" type="image/svg+xml">
  <link rel="canonical" href="${e(p.siteUrl + file)}">
  ${page === 'error' ? '<meta name="robots" content="noindex">' : ''}
  <meta property="og:type" content="website">
  <meta property="og:title" content="${e(title)}">
  <meta property="og:description" content="${e(description)}">
  <meta property="og:url" content="${e(p.siteUrl + file)}">
  <meta name="twitter:card" content="summary">
  <link rel="stylesheet" href="css/site.css">
  <script src="js/site.js" defer></script>
  ${page === 'home' ? `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@type': 'Person', name: p.name, url: p.siteUrl, jobTitle: p.role, worksFor: { '@type': 'Organization', name: p.company }, sameAs: [p.linkedin, p.github] }).replace(/</g, '\\u003c')}</script>` : ''}
</head>
<body data-page="${page}">${header(page)}${body}${footer()}</body>
</html>
`;
}

const diagram = `<div class="hero-art" role="img" aria-label="Three connected layers representing application development, cloud infrastructure, and machine learning.">
  <div class="art-topline"><span class="small-dot"></span> A connected approach <span class="art-index">01—03</span></div>
  <svg class="system-diagram" viewBox="0 0 480 430" fill="none" aria-hidden="true">
    <defs><pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse"><circle cx="1" cy="1" r="1" fill="#b4cfbe" opacity=".24"/></pattern></defs>
    <rect width="480" height="430" fill="url(#grid)"/>
    <path d="M240 71V361M86 180V299M395 180V299" stroke="#b2cebf" stroke-dasharray="3 7" opacity=".65"/>
    <g class="diagram-layer layer-bottom"><path d="m79 287 161-82 161 82v19l-161 82-161-82z" fill="#284c40" stroke="#8cbaa3"/><path d="m79 287 161 82 161-82M240 369v19" stroke="#8cbaa3"/><path d="m105 286 135-67 135 67-135 68z" fill="#315a48" stroke="#618d74"/><path d="m183 282 57-29 57 29-57 29z" stroke="#d5e2b6"/><path d="M210 269v27m30-43v58m30-44v29m-73 0 56-29m-28 43 56-29" stroke="#8cb68c"/><circle cx="240" cy="282" r="5" fill="#e0e99d"/></g>
    <g class="diagram-layer layer-middle"><path d="m79 205 161-82 161 82v19l-161 82-161-82z" fill="#52725b" stroke="#bdd0a8"/><path d="m79 205 161 82 161-82M240 287v19" stroke="#bdd0a8"/><path d="m106 204 134-67 134 67-134 68z" fill="#607d61" stroke="#97b285"/><path d="m182 202 57-29 61 30-58 30z" fill="#829a6e" stroke="#cad7a5"/><path d="m202 202 37-18 39 19-37 18z" fill="#b7c58b"/><path d="m181 188 58-29 62 30m-120 27 60 31 59-29" stroke="#dce6b7" stroke-dasharray="3 5"/></g>
    <g class="diagram-layer layer-top"><path d="m79 124 161-82 161 82v19l-161 82-161-82z" fill="#ced8b5" stroke="#f1f3d9"/><path d="m79 124 161 82 161-82M240 206v19" stroke="#f1f3d9"/><path d="m107 123 133-67 133 67-133 68z" fill="#e5e8c8" stroke="#f7f7e8"/><path d="m180 111 37 18-20 10-37-18z" fill="#779573"/><path d="m229 86 73 36-30 15-73-36z" fill="#9cab81"/><path d="m225 148 52-26 28 14-52 26z" fill="#779573"/><path d="m294 139 30-15 14 7-30 15z" fill="#b7c398"/></g>
    <path d="M402 123h24m-24 82h24m-24 82h24" stroke="#bdcea9"/><circle cx="427" cy="123" r="3" fill="#e5e8c8"/><circle cx="427" cy="205" r="3" fill="#bdcea9"/><circle cx="427" cy="287" r="3" fill="#bdcea9"/>
    <text x="32" y="408" fill="#b8ccbd" font-size="10" font-family="monospace" letter-spacing="2">APPLICATION → CLOUD → INTELLIGENCE</text>
  </svg>
  <div class="art-bottomline"><span>Different layers.<br><strong>One complete picture.</strong></span><span class="art-plus" aria-hidden="true">+</span></div>
</div>`;

function projectVisual(kind) {
  if (kind === 'road') return `<div class="project-visual visual-road" aria-hidden="true"><div class="road-lane"></div><div class="car car-one"><span></span></div><div class="car car-two"><span></span></div><div class="scan scan-one"><span>STATION A</span></div><div class="scan scan-two"><span>STATION B</span></div><span class="visual-caption">CAPTURE → MATCH → CALCULATE</span></div>`;
  if (kind === 'vision') return `<div class="project-visual visual-vision" aria-hidden="true"><div class="vision-grid"></div><div class="face-outline"><div class="face-mask"></div></div><div class="focus-frame"></div><span class="vision-label">VISION + SENSING</span><span class="visual-caption">THE DIGITAL MEETS THE PHYSICAL</span></div>`;
  return `<div class="project-visual visual-movies" aria-hidden="true"><div class="movie-window"><div class="movie-top"><i></i><i></i><i></i><span>DISCOVER</span></div><div class="movie-feature"><span>▷</span></div><div class="movie-posters"><i></i><i></i><i></i><i></i></div></div><div class="chat-bubble">Let’s talk movies <span>↗</span></div><span class="visual-caption">FIND A FILM. START A CONVERSATION.</span></div>`;
}

function projectCard(project, index, archive = false) {
  return `<article class="project-card${archive ? ' archive-card' : ''}" ${archive ? `id="${e(project.id)}" data-category="${e(project.category)}"` : ''}>
    ${!archive ? `<a class="visual-link" href="Projects.html#${e(project.id)}" tabindex="-1" aria-hidden="true">${projectVisual(project.visual)}</a>` : ''}
    <div class="project-content"><div class="project-meta"><span>${e(project.type)}</span><span>${String(index + 1).padStart(2, '0')}</span></div>
    <h3>${archive ? e(project.name) : `<a href="Projects.html#${e(project.id)}">${e(project.name)} ${arrow}</a>`}</h3><p>${e(project.summary)}</p>${tags(project.tags)}
    ${archive ? `<details><summary>Project overview <span aria-hidden="true">+</span></summary><p>${e(project.details)}</p>${project.url ? external(project.url, 'View source on GitHub') : ''}</details>` : ''}</div>
  </article>`;
}

function certRows(items) {
  return items.map(c => `<article class="credential-row"><span class="credential-mark" aria-hidden="true">${e(c.mark)}</span><div><h3>${e(c.name)}</h3><p>${e(c.issuer)}</p></div><span class="credential-date">Issued ${e(c.date)}</span></article>`).join('');
}

function home() {
  return `<main id="main">
  <section class="hero shell" aria-labelledby="hero-title"><div class="hero-copy"><p class="eyebrow"><span class="status-dot"></span> Software engineer · ${e(p.location)}</p><p class="hello">Hi, I’m ${e(p.shortName)}.</p><h1 id="hero-title">${p.headline.split('\n').map((line, i) => i ? `<span>${e(line)}</span>` : e(line)).join('<br>')}</h1><p class="hero-description">${e(p.intro)}</p><div class="hero-actions"><a class="button button-primary" href="#projects">Explore my work <span aria-hidden="true">↘</span></a>${cv()}</div><div class="current-role"><span class="role-line"></span><div><span>Currently at ${e(p.company)}</span><p>${e(p.role)}</p></div></div></div>${diagram}</section>
  <div class="expertise-band"><div class="shell"><span class="band-label">Connecting the dots</span><span>Full-stack development</span><span class="band-plus" aria-hidden="true">+</span><span>Cloud-native systems</span><span class="band-plus" aria-hidden="true">+</span><span>Applied machine learning</span></div></div>
  <section class="section shell about-section" id="about" aria-labelledby="about-title"><div class="section-heading"><p class="eyebrow">01 / A little context</p><h2 id="about-title">An engineer.<br>A curious mind.<br><span class="muted">A bigger picture.</span></h2></div><div class="about-copy"><p class="large-copy">${e(p.about)}</p><p>My foundation is in Computer Science at VIT, with a specialization in Bioinformatics. That mix of disciplines still shapes how I approach problems: understand the system, connect ideas, and build something useful.</p><div class="about-facts"><div><strong>Since 2022</strong><span>Engineering at Accenture</span></div><div><strong>VIT ’22</strong><span>Computer Science graduate</span></div></div><a class="text-link" href="Awards.html#recognition">A few milestones along the way ${arrow}</a></div></section>
  <section class="section section-tinted" id="experience" aria-labelledby="experience-title"><div class="shell experience-layout"><div class="section-heading"><p class="eyebrow">02 / The journey so far</p><h2 id="experience-title">Building.<br>Learning.<br><span class="muted">Moving forward.</span></h2><p>From developing features to designing<br class="desktop-break"> the systems behind them.</p>${cv('text-link', 'The full story in my CV')}</div><div class="timeline">${p.experience.map(job => `<article class="experience-item"><div class="experience-top"><span class="company-name">${e(job.company)}</span>${job.current ? '<span class="current-badge">Current</span>' : ''}<span class="experience-date">${e(job.dates)}</span></div><h3>${e(job.role)}</h3><p>${e(job.description)}</p>${tags(job.tags)}</article>`).join('')}</div></div></section>
  <section class="section shell" id="projects" aria-labelledby="projects-title"><span id="work" class="anchor-alias"></span><div class="section-title-row"><div><p class="eyebrow">03 / Selected work</p><h2 id="projects-title">Ideas turned into <span class="serif-word">projects.</span></h2></div><a class="text-link" href="Projects.html">All projects ${arrow}</a></div><p class="section-intro">A few explorations in computer vision, machine learning, and the web.<br class="desktop-break"> Earlier independent work that helped shape how I build today.</p><div class="project-grid">${p.projects.filter(project => project.featured).map((project, i) => projectCard(project, i)).join('')}</div></section>
  <section class="section shell skills-section" id="skills" aria-labelledby="skills-title"><div class="section-title-row"><div><p class="eyebrow">04 / Tools of the trade</p><h2 id="skills-title">Across the stack.</h2></div><p>A connected set of skills.<br>One problem-solving mindset.</p></div><div class="skills-grid">${p.skills.map((skill, i) => `<article class="skill-column"><span class="skill-number">0${i + 1}</span><h3>${e(skill.name)}</h3><p>${e(skill.description)}</p>${tags(skill.items)}</article>`).join('')}</div></section>
  <section class="section section-tinted" id="credentials" aria-labelledby="credentials-title"><div class="shell credentials-layout"><div class="section-heading"><p class="eyebrow">05 / Always learning</p><h2 id="credentials-title">Curiosity,<br><span class="serif-word">with credentials.</span></h2><p>Continuing to grow across cloud,<br class="desktop-break"> infrastructure, and AI.</p><a class="text-link" href="Awards.html">All credentials & recognition ${arrow}</a></div><div class="credential-list">${certRows(p.certifications.slice(0, 4))}</div></div></section>
  <section class="section shell education-section" id="education" aria-labelledby="education-title"><p class="eyebrow">06 / Foundations</p><div class="education-main"><div><h2 id="education-title">${e(p.education[0].school)}</h2><p class="degree">${e(p.education[0].degree)} · ${e(p.education[0].detail)}</p></div><span class="education-date">${e(p.education[0].dates)}</span></div><div class="community-grid">${p.community.map(c => `<div><span class="eyebrow">Community</span><h3>${e(c.name)}</h3><p>${e(c.role)} <span>· ${e(c.dates)}</span></p></div>`).join('')}</div></section>
  </main>`;
}

function projects() {
  return `<main id="main" class="shell archive-main"><section class="page-intro"><a class="back-link" href="index.html">← Back to home</a><p class="eyebrow">Projects / The collection</p><h1>Learning by <span class="serif-word">building.</span></h1><p>Experiments, applications, and earlier independent work.<br class="desktop-break"> A collection of the problems I’ve explored along the way.</p>${external(p.github, 'Find me on GitHub')}</section>
    <section aria-label="Project collection"><div class="project-tools" hidden><div class="filters" role="group" aria-label="Filter projects">${['All work', 'Machine learning', 'Web applications', 'Applications'].map((c, i) => `<button class="filter-button${i === 0 ? ' is-active' : ''}" data-filter="${e(c)}" aria-pressed="${i === 0}">${e(c)}</button>`).join('')}</div><label class="search-box"><span class="sr-only">Search projects</span><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="6" stroke="currentColor" stroke-width="1.5"/><path d="m15 15 5 5" stroke="currentColor" stroke-width="1.5"/></svg><input type="search" placeholder="Search projects" autocomplete="off"></label></div><p class="project-count" role="status" aria-live="polite">${p.projects.length} projects</p><div class="archive-grid">${p.projects.map((project, i) => projectCard(project, i, true)).join('')}</div><div class="empty-state" hidden><h2>No projects found.</h2><p>Try a different search or category.</p><button class="button button-outline" data-reset-filters>Reset filters</button></div></section></main>`;
}

function awards() {
  return `<main id="main" class="shell archive-main"><section class="page-intro"><a class="back-link" href="index.html">← Back to home</a><p class="eyebrow">Credentials / Recognition</p><h1>A habit of <span class="serif-word">learning.</span></h1><p>Professional certifications, academic milestones,<br class="desktop-break"> and a few memorable moments along the way.</p>${external(p.linkedin, 'View LinkedIn profile')}</section>
  <section class="archive-section" aria-labelledby="cert-title"><div class="section-title-row"><h2 id="cert-title">Professional certifications</h2><span class="eyebrow">Cloud · Development · AI</span></div><p class="section-intro">Issue dates are shown as recorded in my CV.</p><div class="credential-list full-credentials">${certRows(p.certifications)}</div></section>
  <section class="archive-section" id="recognition" aria-labelledby="recognition-title"><p class="eyebrow">Milestones</p><h2 id="recognition-title">Honors & recognition</h2><div class="recognition-grid">${p.awards.map((award, i) => `<article class="recognition-card"><span class="recognition-index" aria-hidden="true">${i === 0 ? '✳' : '0' + (i + 1)}</span><p class="eyebrow">${e(award.issuer)}</p><h3>${e(award.name)}</h3><p>${e(award.description)}</p>${i === 0 ? '<a class="text-link" href="images/Rithu_PresidentAward.jpg" target="_blank" rel="noopener noreferrer">View the award <span aria-hidden="true">↗</span></a>' : ''}</article>`).join('')}</div></section>
  <section class="archive-section" aria-labelledby="education-history-title"><p class="eyebrow">Education</p><h2 id="education-history-title">Where it started.</h2><div class="education-history">${p.education.map(school => `<article><span>${e(school.dates)}</span><div><h3>${e(school.school)}</h3><p>${e(school.degree)}${school.detail ? ' · ' + e(school.detail) : ''}</p></div></article>`).join('')}</div></section>
  <section class="archive-section"><details class="learning-details"><summary>Earlier coursework & certifications <span aria-hidden="true">+</span></summary><p>Additional learning from my original portfolio.</p><ul>${p.earlierLearning.map(c => `<li>${e(c)}</li>`).join('')}</ul></details></section></main>`;
}

const pages = {
  'index.html': document('home', `${p.name} — Software Engineer`, 'Software engineer at Accenture in Bengaluru. Full-stack development, AWS, cloud-native systems, and applied machine learning.', home()),
  'Projects.html': document('projects', `Projects — ${p.shortName}`, 'Explore Rithvik’s projects in computer vision, machine learning, and web applications.', projects()),
  'Awards.html': document('awards', `Credentials & Recognition — ${p.shortName}`, 'Rithvik’s professional certifications, education, and academic recognition.', awards())
};
const error = document('error', `Page not found — ${p.shortName}`, 'Find your way back to Rithvik’s portfolio.', `<main id="main" class="shell error-main"><p class="eyebrow">404 / A small detour</p><h1>This page took<br>a different path.</h1><p>Let’s get you back to the work.</p><a class="button button-primary" href="index.html">Back to home <span aria-hidden="true">↗</span></a></main>`);
// Absolute base keeps assets and navigation working for nested missing URLs on GitHub Pages.
pages['404.html'] = error.replace('<head>', `<head>\n  <base href="${e(p.siteUrl)}">`);
pages['error.html'] = error;
for (const [file, html] of Object.entries(pages)) await writeFile(new URL(file, root), html.replace(/[\t ]+$/gm, ''));
await writeFile(new URL('sitemap.xml', root), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${['', 'Projects.html', 'Awards.html'].map(file => `<url><loc>${e(p.siteUrl + file)}</loc></url>`).join('')}</urlset>\n`);
console.log(`Built ${Object.keys(pages).length} pages from data/portfolio.json.`);
