const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const normalizeIP = value => value?.startsWith('::ffff:') ? value.slice(7) : value;

export function adminIdentity(req, { enabled = false, trustedProxyIPs = [], username = 'rithvik' } = {}) {
  // Identity headers are accepted only from the explicitly configured proxy.
  if (!enabled || !trustedProxyIPs.includes(normalizeIP(req.socket.remoteAddress))) return null;
  if (req.headers['remote-user'] !== username) return null;
  const groups = String(req.headers['remote-groups'] || '').split(',').map(value => value.trim());
  if (!groups.includes('admins')) return null;
  return { username, name: String(req.headers['remote-name'] || username) };
}

const arrow = '<span aria-hidden="true">↗</span>';
const square = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';
const stack = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m3 7 9-4 9 4-9 4zM3 12l9 4 9-4M3 17l9 4 9-4"/></svg>';
const book = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 3h13a2 2 0 0 1 2 2v16H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3M3 17h16M8 7h7M8 11h5"/></svg>';

export function renderAdmin(identity) {
  const name = escapeHTML(identity.name);
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#193d30"><title>Workspace · Rithvik</title><link rel="icon" href="/images/favicon.svg"><link rel="stylesheet" href="/css/admin.css"></head>
<body><a class="skip" href="#main">Skip to content</a><div class="workspace">
<aside class="sidebar"><a class="workspace-brand" href="/admin/"><span class="brand-symbol">r.</span><span>rithvik<span class="brand-caption">workspace</span></span></a><p class="nav-label">YOUR SPACE</p><nav aria-label="Workspace navigation"><a class="nav-item active" href="/admin/" aria-current="page">${square}<span>Overview</span></a><span class="nav-item planned" aria-disabled="true">${stack}<span>Portainer</span><small>Next</small></span><span class="nav-item planned" aria-disabled="true">${book}<span>Fieldnotes</span><small>Later</small></span></nav><div class="sidebar-bottom"><a class="visit-site" href="/">Public portfolio ${arrow}</a><div class="identity"><span class="avatar">${escapeHTML(identity.name.slice(0, 1).toUpperCase())}</span><div><strong>${name}</strong><span>Administrator</span></div><span class="online-dot" title="Signed in"></span></div></div></aside>
<div class="workspace-body"><header class="topbar"><span>Workspace <span class="breadcrumb">/</span> Overview</span><div><span class="secure-label"><i></i> Signed in securely</span><a href="/auth/logout">Sign out ${arrow}</a></div></header>
<main id="main"><section class="welcome"><p class="eyebrow">A LITTLE ORDER BEHIND THE SCENES</p><h1>Your <em>workspace.</em></h1><p>Welcome back, ${name}. One place to look after your site,<br class="desktop-break"> your applications, and the things you’re learning.</p><a class="primary-link" href="/">View your portfolio ${arrow}</a><div class="welcome-art" aria-hidden="true"><span class="art-square one"></span><span class="art-square two"></span><span class="art-square three"></span><span class="art-dot"></span></div></section>
<section class="summary" aria-label="Workspace status"><div><span class="stat-label">YOUR IDENTITY</span><strong>One shared login</strong><p><i class="status-dot"></i>Authelia is connected</p></div><div><span class="stat-label">PUBLIC WEBSITE</span><strong>Portfolio</strong><p>Available over HTTPS ${arrow}</p></div><div><span class="stat-label">UP NEXT</span><strong>Container management</strong><p>Portainer is the next stage</p></div></section>
<section class="applications" aria-labelledby="applications-title"><div class="section-heading"><div><p class="eyebrow">YOUR APPLICATIONS</p><h2 id="applications-title">A place for everything.</h2></div><span class="section-note">Connected as you go</span></div><div class="app-grid"><article class="app-card available"><div class="app-top"><span class="app-icon">${square}</span><span class="badge live">Connected</span></div><h3>Portfolio</h3><p>Your public home for projects, experience, and professional work.</p><a href="/">Open website ${arrow}</a></article><article class="app-card"><div class="app-top"><span class="app-icon">${stack}</span><span class="badge">Next stage</span></div><h3>Portainer</h3><p>Containers, service logs, and the applications running on Oracle.</p><span class="unavailable">Available after the next setup</span></article><article class="app-card"><div class="app-top"><span class="app-icon">${book}</span><span class="badge">Planned</span></div><h3>Blog & learning notes</h3><p>A browser editor for articles, working notes, drafts, and new ideas.</p><span class="unavailable">Writing tools are coming next</span></article></div></section>
<section class="account-row" aria-label="Account settings"><div class="account-mark" aria-hidden="true">✓</div><div><h2>Your account comes with you.</h2><p>This shared sign-in will connect the next applications as they’re added.</p></div><a href="/auth/">Manage sign-in ${arrow}</a></section>
<footer><span>Rithvik’s workspace</span><span>Built a step at a time.</span></footer></main></div></div></body></html>`;
}
