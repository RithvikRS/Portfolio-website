import { readFile, writeFile } from 'node:fs/promises';

const root = new URL('../', import.meta.url);
const p = JSON.parse(await readFile(new URL('data/portfolio.json', root), 'utf8'));
if (process.env.SITE_URL) {
  const site = new URL(process.env.SITE_URL);
  if (!['http:', 'https:'].includes(site.protocol)) throw new Error('SITE_URL must use HTTP or HTTPS.');
  p.siteUrl = site.href.endsWith('/') ? site.href : `${site.href}/`;
}
const e = value => String(value ?? '').replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
const arrowIcon = (direction = 'up-right') => {
  const paths = { 'up-right': 'M6 18 18 6M6 6h12v12', 'down-right': 'M6 6l12 12M6 18h12V6', down: 'M12 4v16m-6-6 6 6 6-6', up: 'M12 20V4m-6 6 6-6 6 6' };
  return `<span class="arrow-icon" data-direction="${direction}" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="${paths[direction]}"/></svg></span>`;
};
const arrow = arrowIcon();
const external = (url, label, cls = 'text-link') => `<a class="${cls}" href="${e(url)}" target="_blank" rel="noopener noreferrer">${label} ${arrow}</a>`;
const tags = items => `<ul class="tags">${items.map(item => `<li>${e(item)}</li>`).join('')}</ul>`;
function skillTags(items) {
  return `<ul class="tags skill-tags">${items.map(item => `<li>${e(item)}</li>`).join('')}</ul>`;
}
function projectSkills(project) {
  return `<div class="project-skills"><div class="project-skill-group"><p class="project-skills-label">Applied skills</p>${tags(project.skills)}</div>${project.technologies.length ? `<div class="project-skill-group"><p class="project-skills-label">Tools</p>${tags(project.technologies)}</div>` : ''}</div>`;
}
const credly = () => external(p.credly, '<span class="credly-mark" aria-hidden="true">C</span> View badges on Credly', 'text-link credly-link');
const cv = (cls = 'button button-outline', label = 'Download CV') => `<a class="${cls}" href="${e(p.cv)}" download>${label} ${arrowIcon('down')}</a>`;

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
    <div><p class="eyebrow light">Let’s connect</p><h2 id="contact-title">Good work starts<br><span>with a conversation.</span></h2><p>Get in touch about software engineering roles,<br class="desktop-break"> technical collaborations, or an idea you’re exploring.</p></div>
    <div class="contact-actions"><button class="button contact-button" type="button" data-open-contact aria-haspopup="dialog" hidden>Send a message ${arrow}</button><div class="contact-links">${external(p.linkedin, 'LinkedIn')}${external(p.github, 'GitHub')}</div><noscript><p>Please get in touch through LinkedIn.</p></noscript></div>
  </div></section>
  <footer class="site-footer shell"><p>© <span data-year>${new Date().getFullYear()}</span> ${e(p.name)}</p><p>Software engineer · Bengaluru, India</p><div class="footer-controls"><button type="button" class="motion-toggle" aria-pressed="true" hidden>Motion on</button><a href="#top">Back to top ${arrowIcon('up')}</a></div></footer>
  <dialog class="contact-dialog" aria-labelledby="form-title" aria-describedby="form-intro">
    <button type="button" class="dialog-close" aria-label="Close contact form">×</button>
    <div class="form-heading"><p class="eyebrow">Start a conversation</p><h2 id="form-title">What’s on your <span class="serif-word">mind?</span></h2><p id="form-intro">Tell me a little about your opportunity or idea.</p></div>
    <form class="contact-form" data-endpoint="${e(p.contact.endpoint)}">
      <div class="form-row"><div class="form-field"><label for="contact-name">Your name</label><input id="contact-name" name="name" autocomplete="name" required minlength="2" maxlength="80" placeholder="Alex Morgan"></div><div class="form-field"><label for="contact-email">Your email</label><input id="contact-email" name="email" type="email" autocomplete="email" required maxlength="254" placeholder="alex@example.com"></div></div>
      <div class="form-field"><label for="contact-subject">Subject <span>(optional)</span></label><input id="contact-subject" name="subject" maxlength="120" placeholder="An engineering opportunity"></div>
      <div class="form-field"><label for="contact-message">Message</label><textarea id="contact-message" name="message" required minlength="10" maxlength="5000" rows="5" placeholder="What would you like to work on together?"></textarea><span class="message-count" aria-hidden="true">0 / 5,000</span></div>
      <div class="form-trap" aria-hidden="true"><label for="contact-website">Leave this empty</label><input id="contact-website" name="website" tabindex="-1" autocomplete="off"></div>
      <p class="form-privacy">Your details are used to respond to your message.</p>
      <div class="form-actions"><button type="submit" class="button button-primary" disabled><span class="submit-label">Send message</span>${arrow}</button>${external(p.linkedin, 'Or connect on LinkedIn')}</div>
      <p class="form-status" role="status" aria-live="polite" aria-atomic="true">Checking message availability…</p>
    </form>
    <div class="form-success" hidden tabindex="-1"><div class="success-mark" aria-hidden="true">✓</div><h3 id="form-success-title">Thanks for reaching out.</h3><p id="form-success-description">Your message has been accepted for email delivery. I’ll reply to the address you provided.</p><button type="button" class="button button-outline" data-close-contact>Back to the portfolio</button></div>
  </dialog>`;
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
  ${page === 'home' ? `<script type="application/ld+json">${JSON.stringify({ '@context': 'https://schema.org', '@type': 'Person', name: p.name, url: p.siteUrl, jobTitle: p.role, worksFor: { '@type': 'Organization', name: p.company }, sameAs: [p.linkedin, p.github, p.credly] }).replace(/</g, '\\u003c')}</script>` : ''}
</head>
<body data-page="${page}"><div class="reading-progress" aria-hidden="true"></div>${header(page)}${body}${footer()}</body>
</html>
`;
}

const diagram = `<div class="hero-art" role="img" aria-label="Three layers, from top to bottom: Application, AI, Cloud.">
  <div class="art-topline"><span class="small-dot"></span> Areas I work in</div>
  <div class="diagram-stage"><div class="system-diagram" aria-hidden="true">
    <div class="diagram-layer layer-top">
      <svg class="layer-surface" viewBox="9 0 282 144" fill="none"><path d="M10 66 150 6 290 66v10L150 136 10 76z" fill="#93a57b"/><path d="M10 66 150 6 290 66 150 126z" fill="#e5e8c8" stroke="#d8e6aa"/><path d="m50 66 100-43 100 43-100 43z" stroke="#779573"/></svg>
      <span class="layer-label">Application</span>
    </div>
    <div class="diagram-layer layer-middle">
      <svg class="layer-surface" viewBox="9 0 282 144" fill="none"><path d="M10 66 150 6 290 66v10L150 136 10 76z" fill="#3c5d43"/><path d="M10 66 150 6 290 66 150 126z" fill="#6f8a62" stroke="#bdd0a8"/><path d="m50 66 100-43 100 43-100 43z" stroke="#cbd7ad"/></svg>
      <span class="layer-label">AI</span>
    </div>
    <div class="diagram-layer layer-bottom">
      <svg class="layer-surface" viewBox="9 0 282 144" fill="none"><path d="M10 66 150 6 290 66v10L150 136 10 76z" fill="#183629"/><path d="M10 66 150 6 290 66 150 126z" fill="#315a48" stroke="#8cbaa3"/><path d="m50 66 100-43 100 43-100 43zM83 80 183 37M117 94 217 51M83 52 183 95M117 38 217 81" stroke="#8cb68c"/></svg>
      <span class="layer-label">Cloud</span>
    </div>
  </div></div>
  <div class="art-bottomline"><span>Across the stack<br><strong>Application, AI, Cloud.</strong></span></div>
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
    <h3>${archive ? e(project.name) : `<a href="Projects.html#${e(project.id)}">${e(project.name)} ${arrow}</a>`}</h3><p>${e(project.summary)}</p>${projectSkills(project)}
    ${archive ? `<details><summary>How it works <span aria-hidden="true">+</span></summary><p>${e(project.details)}</p></details>${project.url ? `<div class="project-source">${external(project.url, 'View source on GitHub')}</div>` : ''}` : ''}</div>
  </article>`;
}

function certRows(items) {
  return items.map(c => `<article class="credential-row"><span class="credential-mark" aria-hidden="true">${e(c.mark)}</span><div><h3>${e(c.name)}</h3><p>${e(c.issuer)}</p></div><span class="credential-date">Issued ${e(c.date)}</span></article>`).join('');
}

function home() {
  const headlineLines = p.headline.split('\n');
  return `<main id="main">
  <section class="hero shell" aria-labelledby="hero-title"><div class="hero-copy"><p class="eyebrow"><span class="status-dot"></span> Software engineer · ${e(p.location)}</p><p class="hello">Hi, I’m ${e(p.shortName)}.</p><h1 id="hero-title" class="role-headline">${headlineLines.map((line, i) => `<span class="headline-line${i === headlineLines.length - 1 ? ' headline-accent' : ''}"><span class="headline-text">${e(line)}</span></span>`).join(' ')}</h1><p class="hero-description">${e(p.intro)}</p><div class="hero-actions"><a class="button button-primary" href="#projects">Explore my work ${arrowIcon('down-right')}</a>${cv()}</div></div>${diagram}</section>
  <div class="expertise-band"><div class="shell"><span class="band-label">Areas of focus</span><span>Full-stack development</span><span class="band-plus" aria-hidden="true">+</span><span>Cloud-native systems</span><span class="band-plus" aria-hidden="true">+</span><span>Applied machine learning</span></div></div>
  <section class="section shell about-section" id="about" aria-labelledby="about-title"><div class="section-heading"><p class="eyebrow">01 / About me</p><h2 id="about-title">From applications<br>to <span class="muted">infrastructure.</span></h2></div><div class="about-copy"><p class="large-copy">${e(p.about)}</p><p>I studied Computer Science at VIT, specializing in Bioinformatics. Alongside my professional work, I’ve explored computer vision, recommendation systems, and web applications through independent projects.</p><div class="about-facts"><div><strong>Since 2022</strong><span>Engineering at Accenture</span></div><div><strong>VIT ’22</strong><span>Computer Science graduate</span></div></div><a class="text-link" href="Awards.html#recognition">Education & recognition ${arrow}</a></div></section>
  <section class="section section-tinted" id="experience" aria-labelledby="experience-title"><div class="shell experience-layout"><div class="section-heading"><p class="eyebrow">02 / Professional experience</p><h2 id="experience-title">Engineering at<br><span class="muted">Accenture.</span></h2><p>Developing applications, supporting operations,<br class="desktop-break"> and bringing ML workflows into production.</p>${cv('text-link', 'Download my CV')}</div><div class="experience-body"><div class="timeline">${p.experience.map(job => `<article class="experience-item"><div class="experience-top"><span class="company-name">${e(job.company)}</span>${job.current ? '<span class="current-badge">Current</span>' : ''}<span class="experience-date">${e(job.dates)}</span></div><h3>${e(job.role)}</h3><p>${e(job.description)}</p>${tags(job.tags)}</article>`).join('')}</div><a class="text-link recognition-link" href="Awards.html#recognition">View honors & recognition ${arrow}</a></div></div></section>
  <section class="section shell" id="projects" aria-labelledby="projects-title"><span id="work" class="anchor-alias"></span><div class="section-title-row"><div><p class="eyebrow">03 / Selected work</p><h2 id="projects-title">Selected <span class="serif-word">projects.</span></h2></div><a class="text-link" href="Projects.html">All projects ${arrow}</a></div><p class="section-intro">Independent work in computer vision, machine learning, and web development.<br class="desktop-break"> Each project shows the problem, the approach, and the skills involved.</p><div class="project-grid">${p.projects.filter(project => project.featured).map((project, i) => projectCard(project, i)).join('')}</div></section>
  <section class="section section-tinted skills-section" id="skills" aria-labelledby="skills-title"><div class="shell"><div class="section-title-row"><div><p class="eyebrow">04 / Technical toolkit</p><h2 id="skills-title">Skills in practice.</h2></div><p>Professional experience and independent projects.</p></div><div class="skills-grid">${p.skills.map((skill, i) => `<article class="skill-column"><span class="skill-number">0${i + 1}</span><h3>${e(skill.name)}</h3><p>${e(skill.description)}</p>${skillTags(skill.items)}</article>`).join('')}</div></div></section>
  <section class="section" id="credentials" aria-labelledby="credentials-title"><div class="shell credentials-layout"><div class="section-heading"><p class="eyebrow">05 / Professional development</p><h2 id="credentials-title">Learning that<br><span class="serif-word">supports the work.</span></h2><p>Certifications across cloud development,<br class="desktop-break"> Kubernetes, and machine learning.</p><div class="credential-actions"><a class="text-link" href="Awards.html">All credentials & recognition ${arrow}</a>${credly()}</div></div><div class="credential-list">${certRows(p.certifications.slice(0, 4))}</div></div></section>
  <section class="section section-tinted education-section" id="education" aria-labelledby="education-title"><div class="shell"><p class="eyebrow">06 / Foundations</p><div class="education-main"><div><h2 id="education-title">${e(p.education[0].school)}</h2><p class="degree">${e(p.education[0].degree)} · ${e(p.education[0].detail)}</p></div><span class="education-date">${e(p.education[0].dates)}</span></div><div class="community-grid">${p.community.map(c => `<div><span class="eyebrow">Community</span><h3>${e(c.name)}</h3><p>${e(c.role)} <span>· ${e(c.dates)}</span></p></div>`).join('')}</div></div></section>
  </main>`;
}

function projects() {
  return `<main id="main" class="shell archive-main"><section class="page-intro"><a class="back-link" href="index.html">← Back to home</a><p class="eyebrow">Projects / Independent work</p><h1>Projects with a <span class="serif-word">purpose.</span></h1><p>Computer vision, recommendation systems, and practical applications.<br class="desktop-break"> Explore each project’s approach, tools, and source code where available.</p>${external(p.github, 'Explore my GitHub')}</section>
    <section aria-label="Project collection"><div class="project-tools" hidden><div class="filters" role="group" aria-label="Filter projects">${['All work', 'Machine learning', 'Web applications', 'Applications'].map((c, i) => `<button class="filter-button${i === 0 ? ' is-active' : ''}" data-filter="${e(c)}" aria-pressed="${i === 0}">${e(c)}</button>`).join('')}</div><label class="search-box"><span class="sr-only">Search projects</span><svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="10" cy="10" r="6" stroke="currentColor" stroke-width="1.5"/><path d="m15 15 5 5" stroke="currentColor" stroke-width="1.5"/></svg><input type="search" placeholder="Search projects" autocomplete="off"></label></div><p class="project-count" role="status" aria-live="polite">${p.projects.length} projects</p><div class="archive-grid">${p.projects.map((project, i) => projectCard(project, i, true)).join('')}</div><div class="empty-state" hidden><h2>No projects found.</h2><p>Try a different search or category.</p><button class="button button-outline" data-reset-filters>Reset filters</button></div></section></main>`;
}

function awards() {
  return `<main id="main" class="shell archive-main"><section class="page-intro"><a class="back-link" href="index.html">← Back to home</a><p class="eyebrow">Credentials / Recognition</p><h1>Learning & <span class="serif-word">recognition.</span></h1><p>Recognition at Accenture, professional certifications,<br class="desktop-break"> and milestones from my academic journey.</p><div class="profile-links">${credly()}${external(p.linkedin, 'View LinkedIn profile')}</div></section>
  <section class="archive-section recognition-section" id="recognition" aria-labelledby="recognition-title"><span id="professional-recognition" class="anchor-alias" aria-hidden="true"></span><p class="eyebrow">Milestones</p><h2 id="recognition-title">Honors & recognition</h2><div class="recognition-grid">${[...p.awards, ...p.professionalAwards].map((award, i) => `<article class="recognition-card"><span class="recognition-index" aria-hidden="true">${String(i + 1).padStart(2, '0')}</span><p class="eyebrow">${e(award.issuer)}${award.scope ? ' · ' + e(award.scope) : ''}${award.date ? ' · ' + e(award.date) : ''}</p><h3>${e(award.name)}</h3>${award.description ? `<p>${e(award.description)}</p>` : ''}${award.image ? `<a class="text-link" href="${e(award.image)}" target="_blank" rel="noopener noreferrer">View the award ${arrow}</a>` : ''}</article>`).join('')}</div></section>
  <section class="archive-section" aria-labelledby="cert-title"><div class="section-title-row"><h2 id="cert-title">Professional certifications</h2><span class="eyebrow">Cloud · Development · AI</span></div><p class="section-intro">Issue dates are shown as recorded in my CV.</p><div class="credential-list full-credentials">${certRows(p.certifications)}</div></section>
  <section class="archive-section" aria-labelledby="education-history-title"><p class="eyebrow">Education</p><h2 id="education-history-title">Education</h2><div class="education-history">${p.education.map(school => `<article><span>${e(school.dates)}</span><div><h3>${e(school.school)}</h3><p>${e(school.degree)}${school.detail ? ' · ' + e(school.detail) : ''}</p></div></article>`).join('')}</div></section>
  <section class="archive-section"><details class="learning-details"><summary>Earlier coursework & certifications <span aria-hidden="true">+</span></summary><p>Courses in programming, machine learning, data, and bioinformatics.</p><ul>${p.earlierLearning.map(c => `<li>${e(c)}</li>`).join('')}</ul></details></section></main>`;
}

const pages = {
  'index.html': document('home', `${p.name} — Software Engineer`, 'Software engineer at Accenture in Bengaluru. Full-stack development, AWS, cloud-native systems, and applied machine learning.', home()),
  'Projects.html': document('projects', `Projects — ${p.shortName}`, 'Explore Rithvik’s projects in computer vision, machine learning, and web applications.', projects()),
  'Awards.html': document('awards', `Credentials & Recognition — ${p.shortName}`, 'Rithvik’s recognition at Accenture, professional certifications, education, and academic honors.', awards())
};
const error = document('error', `Page not found — ${p.shortName}`, 'Find your way back to Rithvik’s portfolio.', `<main id="main" class="shell error-main"><p class="eyebrow">404 / A small detour</p><h1>This page took<br>a different path.</h1><p>Let’s get you back to the work.</p><a class="button button-primary" href="index.html">Back to home ${arrow}</a></main>`);
// Absolute base keeps assets and navigation working for nested missing URLs on GitHub Pages.
pages['404.html'] = error.replace('<head>', `<head>\n  <base href="${e(p.siteUrl)}">`);
pages['error.html'] = error;
for (const [file, html] of Object.entries(pages)) await writeFile(new URL(file, root), html.replace(/[\t ]+$/gm, ''));
await writeFile(new URL('sitemap.xml', root), `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${['', 'Projects.html', 'Awards.html'].map(file => `<url><loc>${e(p.siteUrl + file)}</loc></url>`).join('')}</urlset>\n`);
console.log(`Built ${Object.keys(pages).length} pages from data/portfolio.json.`);
