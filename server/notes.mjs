import { marked } from 'marked';
import sanitizeHtml from 'sanitize-html';
import { createNotesStore, NotesError, publicPath } from './notes-store.mjs';
import { adminIdentity } from './admin.mjs';

export const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
export function renderMarkdown(source) {
  return sanitizeHtml(marked.parse(source, { gfm: true }), {
    allowedTags: ['p', 'br', 'hr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'em', 'del', 'blockquote', 'pre', 'code', 'ul', 'ol', 'li', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'input'],
    allowedAttributes: { a: ['href', 'title', 'rel'], code: ['class'], input: ['type', 'checked', 'disabled'] },
    allowedClasses: { code: [/^language-[\w-]+$/] },
    allowedSchemes: ['http', 'https', 'mailto'], allowProtocolRelative: false,
    transformTags: { a: (tag, attrs) => ({ tagName: tag, attribs: { ...attrs, rel: 'nofollow noopener noreferrer' } }), input: (tag, attrs) => ({ tagName: tag, attribs: { type: 'checkbox', disabled: '', ...(Object.hasOwn(attrs, 'checked') ? { checked: '' } : {}) } }) }
  });
}
const e = escapeHTML;
const date = value => new Date(value).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const tags = values => values.map(value => `<span class="tag">${e(value)}</span>`).join('');
function page(title, body, { editor = false, canonical = '' } = {}) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="theme-color" content="#193d30"><title>${e(title)} · Rithvik</title>${editor ? '<meta name="robots" content="noindex,nofollow">' : ''}${canonical ? `<link rel="canonical" href="${e(canonical)}">` : ''}<link rel="icon" href="/images/favicon.svg"><link rel="stylesheet" href="/css/notes.css">${editor ? '<script src="/js/notes.js" defer></script>' : ''}</head><body${editor ? ' class="editor-page"' : ''}><a class="skip" href="#main">Skip to content</a><header class="masthead"><a class="brand" href="${editor ? '/admin/' : '/'}"><span class="brand-mark">r.</span><span>rithvik<span class="brand-caption">${editor ? 'workspace / fieldnotes' : 'notes from the journey'}</span></span></a><nav aria-label="${editor ? 'Workspace' : 'Main'} navigation">${editor ? '<a href="/admin/">Overview</a><a href="/portainer/">Portainer</a><a href="/blog/">Public writing ↗</a><a href="/auth/logout">Sign out</a>' : '<a href="/">Portfolio</a><a href="/blog/">Blog</a><a href="/learn/">Learning notes</a>'}</nav></header>${body}<footer class="footer"><span>Rithvik’s fieldnotes</span><span>A thought, a little further along.</span></footer></body></html>`;
}
function editorPage() {
  return page('Fieldnotes', `<main id="main" class="writing-workspace"><div class="workspace-heading"><div><p class="eyebrow">YOUR WRITING SPACE</p><h1>Make room for <em>ideas.</em></h1><p>Capture what you’re learning. Share it when you’re ready.</p></div><a class="quiet-link" href="/admin/notes/api/export">Export library ↓</a></div><div class="studio"><aside class="library"><div class="library-top"><h2>Your library</h2><button id="new-entry" class="button primary" type="button">+ New entry</button></div><label class="sr-only" for="search">Search your writing</label><input id="search" type="search" placeholder="Search titles, tags, or writing…"><label class="sr-only" for="filter">Filter entries</label><select id="filter"><option value="all">All entries</option><option value="blog">Blog posts</option><option value="note">Learning notes</option><option value="private">Private drafts</option><option value="published">Published</option><option value="trash">Trash</option></select><p id="library-count" class="muted" role="status"></p><div id="entry-list" class="entry-list"></div></aside><section class="editor" aria-label="Writing editor"><div id="editor-empty" class="editor-empty"><span class="empty-symbol" aria-hidden="true">✎</span><p class="eyebrow">A BLANK PAGE IS A BEGINNING</p><h2 id="editor-title">What did you learn today?</h2><p>Start a blog post or a learning note.<br>Everything stays private until you publish it.</p><button id="first-entry" class="button primary" type="button">Write something new ↗</button></div><form id="entry-form" hidden><div class="editor-toolbar"><span id="entry-state" class="pill">Private draft</span><span id="save-status" role="status" aria-live="polite">New entry · not saved</span><button id="save" class="button primary" type="submit">Save draft</button></div><fieldset id="entry-fields"><div class="field-row"><label>Entry type<select id="kind"><option value="note">Learning note</option><option value="blog">Blog post</option></select></label><label>Tags <span class="muted">comma separated</span><input id="tags" maxlength="264" placeholder="docker, learning, cloud"></label></div><label class="sr-only" for="title">Title</label><input id="title" class="title-input" required maxlength="140" placeholder="Give your idea a title"><label class="sr-only" for="summary">Short summary</label><textarea id="summary" maxlength="320" rows="2" placeholder="A short introduction (optional)"></textarea><div class="writing-tabs" role="group" aria-label="Editor mode"><button id="write-tab" type="button" aria-pressed="true">Write</button><button id="preview-tab" type="button" aria-pressed="false">Preview</button><span id="word-count" class="muted">0 words</span></div><label class="sr-only" for="body">Markdown content</label><textarea id="body" class="markdown-input" maxlength="65536" rows="18" placeholder="Start with a thought…&#10;&#10;## What I learned&#10;&#10;Write in Markdown. Use **bold**, lists, and fenced code blocks."></textarea><div id="preview" class="prose preview" hidden></div></fieldset><details class="markdown-help"><summary>Markdown quick reference</summary><p><code>## Heading</code> · <code>**bold**</code> · <code>*italic*</code> · <code>[link](https://example.com)</code></p><p><code>- List item</code> · <code>- [ ] Task</code> · surround code with three backticks. Images and embedded HTML widgets are not supported.</p></details><div class="publishing"><div><h3>Share on your site</h3><p id="publish-help">Saving keeps this entry private. Publishing makes it visible to everyone.</p><a id="public-link" hidden target="_blank" rel="noopener">View published entry ↗</a></div><div class="publishing-actions"><button id="publish" class="button" type="button">Publish entry</button><button id="unpublish" class="button" type="button" hidden>Unpublish</button><button id="restore" class="button" type="button" hidden>Restore draft</button><button id="trash" class="text-button danger" type="button">Move to trash</button><button id="download" class="text-button" type="button">Download Markdown ↓</button></div></div></form><p id="message" class="message" role="status" aria-live="polite"></p></section></div><dialog id="confirm-dialog" aria-labelledby="confirm-question"><form method="dialog"><h2 id="confirm-question">Confirm action</h2><p>Your writing stays saved unless you choose to discard unsaved changes.</p><div class="dialog-actions"><button class="button" value="cancel" autofocus>Cancel</button><button class="button primary" value="confirm">Continue</button></div></form></dialog></main>`, { editor: true });
}
function publicPage(entries, kind, url, origin) {
  const learning = kind === 'note'; const base = learning ? '/learn/' : '/blog/';
  const slug = url.pathname.slice(base.length).replace(/\/$/, '');
  if (slug) {
    const entry = entries.find(value => value.slug === slug);
    if (!entry) throw new NotesError(404, 'This entry is private or does not exist.');
    const value = entry.published;
    return page(value.title, `<main id="main" class="article"><a class="back-link" href="${base}">← ${learning ? 'Learning notebook' : 'All posts'}</a><header class="article-heading"><p class="eyebrow">${learning ? 'LEARNING NOTE' : 'FROM THE BLOG'} / ${date(entry.publishedAt)}</p><h1>${e(value.title)}</h1>${value.summary ? `<p class="lede">${e(value.summary)}</p>` : ''}<div class="tag-row">${tags(value.tags)}</div></header><div class="prose">${renderMarkdown(value.body)}</div><div class="article-end"><span>Written by Rithvik</span><a href="${base}">Keep exploring ↗</a></div></main>`, { canonical: origin + publicPath(entry) });
  }
  const query = (url.searchParams.get('q') || '').slice(0, 120).trim().toLowerCase();
  const selected = (url.searchParams.get('tag') || '').slice(0, 32).toLowerCase();
  const available = [...new Set(entries.flatMap(entry => entry.published.tags))].sort();
  const found = entries.filter(entry => { const value = entry.published; return (!selected || value.tags.includes(selected)) && (!query || [value.title, value.summary, value.body, ...value.tags].join(' ').toLowerCase().includes(query)); });
  return page(learning ? 'Learning notebook' : 'Blog', `<main id="main" class="public-main"><section class="public-intro"><p class="eyebrow">${learning ? 'THE LEARNING NOTEBOOK' : 'IDEAS, EXPERIENCE & EXPLORATION'}</p><h1>${learning ? 'Learning, <em>out loud.</em>' : 'Notes from<br>the <em>journey.</em>'}</h1><p>${learning ? 'Concepts, experiments, and things worth remembering.<br>A notebook that grows one discovery at a time.' : 'A space for longer thoughts, things I’ve built,<br>and lessons picked up along the way.'}</p><div class="collection-nav"><a href="/blog/" ${!learning ? 'aria-current="page"' : ''}>The blog</a><a href="/learn/" ${learning ? 'aria-current="page"' : ''}>Learning notebook</a></div></section><section aria-label="Published writing"><form class="public-search" method="get"><label class="sr-only" for="q">Search published writing</label><input id="q" name="q" type="search" placeholder="Find a thought, topic, or tool…" value="${e(query)}"><label class="sr-only" for="tag">Topic</label><select id="tag" name="tag"><option value="">All topics</option>${available.map(tag => `<option ${selected === tag ? 'selected ' : ''}value="${e(tag)}">${e(tag)}</option>`).join('')}</select><button class="button" type="submit">Search</button></form><div class="collection-heading"><p class="eyebrow">${learning ? 'PAGES FROM THE NOTEBOOK' : 'LATEST WRITING'}</p><span class="muted">${found.length} ${found.length === 1 ? 'entry' : 'entries'}</span></div>${found.length ? `<div class="post-grid">${found.map((entry, index) => `<article class="post-card"><div class="post-meta"><span>${String(index + 1).padStart(2, '0')}</span><time datetime="${e(entry.publishedAt)}">${date(entry.publishedAt)}</time></div><h2><a href="${publicPath(entry)}">${e(entry.published.title)}</a></h2><p>${e(entry.published.summary || 'Read this entry in the notebook.')}</p><div class="tag-row">${tags(entry.published.tags)}</div><a class="read-link" href="${publicPath(entry)}">Read ${learning ? 'note' : 'post'} <span aria-hidden="true">↗</span></a></article>`).join('')}</div>` : `<div class="public-empty"><span class="empty-symbol" aria-hidden="true">${query || selected ? '⌕' : '✎'}</span><h2>${query || selected ? 'No matching entries.' : 'The next page is still unwritten.'}</h2><p>${query || selected ? 'Try a different search or explore all topics.' : 'New writing will appear here when it’s ready to share.'}</p><a href="${query || selected ? base : '/'}">${query || selected ? 'Clear filters' : 'Explore the portfolio'} ↗</a></div>`}</section></main>`, { canonical: origin + base });
}
async function readJSON(req) {
  if (!req.headers['content-type']?.startsWith('application/json')) throw new NotesError(415, 'Send JSON content.');
  const chunks = []; let size = 0;
  for await (const chunk of req) { size += chunk.length; if (size > 90000) throw new NotesError(413, 'This request is too large.'); chunks.push(chunk); }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')); } catch { throw new NotesError(400, 'Invalid JSON.'); }
}
export async function createNotesHandler({ directory, origin, identityOptions }) {
  const store = directory ? await createNotesStore(directory) : null;
  return async (req, res, url) => {
    const path = url.pathname;
    if (!/^\/(?:blog|learn)(?:\/|$)/.test(path) && !/^\/admin\/notes(?:\/|$)/.test(path)) return false;
    res.setHeader('Cache-Control', 'no-store');
    const json = (status, value) => { res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(req.method === 'HEAD' ? undefined : JSON.stringify(value)); };
    try {
      if (path.startsWith('/admin/notes')) {
        res.setHeader('X-Robots-Tag', 'noindex, nofollow');
        if (!adminIdentity(req, identityOptions)) throw new NotesError(401, 'Sign in again through the workspace. Your unsaved writing is still in this tab.');
        if (!store) throw new NotesError(503, 'Writing storage is not configured.');
        const api = '/admin/notes/api/';
        if (!path.startsWith(api)) {
          if (!['/admin/notes', '/admin/notes/'].includes(path)) throw new NotesError(404, 'Not found.');
          if (!['GET', 'HEAD'].includes(req.method)) throw new NotesError(405, 'Use GET or HEAD.');
          res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(req.method === 'HEAD' ? undefined : editorPage()); return true;
        }
        const route = path.slice(api.length);
        if (['GET', 'HEAD'].includes(req.method)) {
          if (route === 'entries') {
            const query = (url.searchParams.get('q') || '').slice(0, 120).toLowerCase();
            json(200, store.list().filter(entry => !query || JSON.stringify(store.get(entry.id).draft).toLowerCase().includes(query)));
          } else if (route === 'export') { res.setHeader('Content-Disposition', 'attachment; filename="fieldnotes-backup.json"'); json(200, store.export()); }
          else if (/^entries\/[a-f0-9-]{36}$/.test(route)) json(200, store.get(route.split('/')[1]));
          else throw new NotesError(404, 'Not found.');
          return true;
        }
        if (req.method !== 'POST') throw new NotesError(405, 'Use POST for changes.');
        // Browser mutations require the exact origin and a non-simple header.
        if (req.headers.origin !== origin || req.headers['x-requested-with'] !== 'fieldnotes' || (req.headers['sec-fetch-site'] && req.headers['sec-fetch-site'] !== 'same-origin')) throw new NotesError(403, 'This change must come from the editor on your own site.');
        const value = await readJSON(req);
        if (!value || typeof value !== 'object' || Array.isArray(value)) throw new NotesError(400, 'Send an object.');
        if (route === 'preview') {
          if (typeof value.body !== 'string' || Buffer.byteLength(value.body) > 65536) throw new NotesError(400, 'Keep the Markdown under 64 KiB.');
          json(200, { html: renderMarkdown(value.body) });
        } else if (route === 'entries') json(201, await store.create(value));
        else if (/^entries\/[a-f0-9-]{36}\/(save|publish|unpublish|trash|restore)$/.test(route)) { const [, id, action] = route.split('/'); json(200, await store.change(id, action, value)); }
        else throw new NotesError(404, 'Not found.');
        return true;
      }
      if (!['GET', 'HEAD'].includes(req.method)) throw new NotesError(405, 'Use GET or HEAD.');
      if (path === '/blog' || path === '/learn') { res.writeHead(308, { Location: `${path}/${url.search}` }); res.end(); return true; }
      const kind = path.startsWith('/blog/') ? 'blog' : 'note';
      const html = publicPage(store?.published(kind) || [], kind, url, origin);
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' }); res.end(req.method === 'HEAD' ? undefined : html);
    } catch (error) {
      if (!(error instanceof NotesError)) console.error('Fieldnotes request failed:', error.code || error.name);
      json(error instanceof NotesError ? error.status : 503, { error: error instanceof NotesError ? error.message : 'Writing storage is temporarily unavailable. Keep your text and try again.' });
    }
    return true;
  };
}
