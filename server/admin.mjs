import { proxyMatcher } from './proxy-trust.mjs';
const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

export function adminIdentity(req, { enabled = false, trustedProxyIPs = [], username = 'rithvik' } = {}) {
  // Identity headers are accepted only from the explicitly configured proxy.
  if (!enabled || !proxyMatcher(trustedProxyIPs)(req.socket.remoteAddress)) return null;
  if (req.headers['remote-user'] !== username) return null;
  const groups = String(req.headers['remote-groups'] || '').split(',').map(value => value.trim());
  if (!groups.includes('admins')) return null;
  return { username, name: String(req.headers['remote-name'] || username) };
}

const arrow = '<span aria-hidden="true">↗</span>';
const square = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>';
const stack = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="m3 7 9-4 9 4-9 4zM3 12l9 4 9-4M3 17l9 4 9-4"/></svg>';
const pulse = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 12h5l3-7 4 14 3-7h5"/></svg>';
const book = '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M4 3h13a2 2 0 0 1 2 2v16H6a3 3 0 0 1-3-3V6a3 3 0 0 1 3-3M3 17h16M8 7h7M8 11h5"/></svg>';

const sections = [
  { title: 'Personal tools', apps: [
    { name: 'Outline', path: '/notes', icon: book, description: 'Write private notes and share documents with your workspace.' },
    { name: 'Vaultwarden', path: '/vault', icon: square, description: 'Open your encrypted password vault.' },
  ] },
  { title: 'Site administration', apps: [
    { name: 'Service access', path: '/admin/access/', icon: square, description: 'Create accounts and manage each person’s service permissions.' },
    { name: 'Uptime Kuma', path: '/uptime', icon: pulse, description: 'Review availability, outages and alerts.' },
    { name: 'OmniRoute', path: '/models', icon: stack, description: 'Manage provider keys, model routing and application usage.' },
    { name: 'Portainer', path: '/portainer/', icon: stack, description: 'Inspect Swarm nodes, services and container logs.' },
    { name: 'Fieldnotes', path: '/admin/notes/', icon: book, description: 'Edit and publish your blog and learning notebook.' },
  ] },
];

function serviceSection({ title, apps }) {
  const cards = apps.map(({ name, path, icon, description }) => `
    <article class="app-card available"><div class="app-top"><span class="app-icon" aria-hidden="true">${icon}</span></div>
    <h3>${name}</h3><p>${description}</p><a href="${path}">Open ${name} ${arrow}</a></article>`);
  return `<section class="applications"><h2>${title}</h2><div class="app-grid">${cards.join('')}</div></section>`;
}

function workspaceNavigation() {
  const links = [
    ['Workspace', [['Overview', '/admin/'], ['Service access', '/admin/access/'], ['User guide', '/dashboard/guide/']]],
    ['Personal tools', [['Outline', '/notes'], ['Vaultwarden', '/vault']]],
    ['Administration', [['OmniRoute', '/models'], ['Uptime Kuma', '/uptime'], ['Portainer', '/portainer/'], ['Fieldnotes', '/admin/notes/']]],
  ];
  const nav = links.map(([label, items]) => `<p class="nav-label">${label}</p>${items.map(([name, path]) =>
    `<a class="nav-item${path === '/admin/' ? ' active' : ''}" href="${path}"${path === '/admin/' ? ' aria-current="page"' : ''}>${name}</a>`).join('')}`).join('');
  return `<nav class="desktop-nav" aria-label="Workspace">${nav}</nav><details class="mobile-nav"><summary>Menu</summary><nav aria-label="Workspace">${nav}</nav></details>`;
}

export function renderAdmin(identity) {
  const name = escapeHTML(identity.name);
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow"><meta name="theme-color" content="#193d30"><title>Workspace · Rithvik</title><link rel="icon" href="/images/favicon.svg"><link rel="stylesheet" href="/css/admin.css"></head>
<body><a class="skip" href="#main">Skip to content</a><div class="workspace">
<aside class="sidebar"><a class="workspace-brand" href="/admin/"><span class="brand-symbol">r.</span><span>rithvik<span class="brand-caption">workspace</span></span></a>${workspaceNavigation()}<div class="sidebar-bottom"><a class="visit-site" href="/">Public portfolio ${arrow}</a><div class="identity"><span class="avatar">${escapeHTML(identity.name.slice(0, 1).toUpperCase())}</span><div><strong>${name}</strong><span>Administrator</span></div><span class="online-dot" title="Signed in"></span></div></div></aside>
<div class="workspace-body"><header class="topbar"><span>Workspace <span class="breadcrumb">/</span> Overview</span><div><span class="secure-label"><i></i> Signed in securely</span><a href="/auth/logout">Sign out ${arrow}</a></div></header>
<main id="main"><section class="welcome"><h1>Your <em>dashboard.</em></h1><p>Welcome back, ${name}.</p><a class="primary-link" href="/">View portfolio ${arrow}</a></section>
${sections.map(serviceSection).join('')}
<section class="account-row"><div><h2>Sign-in settings</h2><p>Manage your Authelia account and authenticator.</p></div><a href="/auth/">Manage sign-in ${arrow}</a></section>
</main></div></div></body></html>`;
}
