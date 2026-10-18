const $ = selector => document.querySelector(selector);
const apiRoot = '/admin/notes/api/';
let current = null;
let dirty = false;
let busy = false;
let listRequest = 0;
let searchTimer;
const fields = ['kind', 'title', 'summary', 'tags', 'body'];
const message = (text, error = false) => { $('#message').textContent = text; $('#message').classList.toggle('error', error); };
function setBusy(value) {
  busy = value;
  document.querySelectorAll('#entry-form button, #new-entry, #first-entry').forEach(button => { button.disabled = value; });
  $('#entry-fields').disabled = value || !!current?.deletedAt;
}
async function api(path, data) {
  const response = await fetch(apiRoot + path, { method: data ? 'POST' : 'GET', redirect: 'error', headers: data ? { 'Content-Type': 'application/json', 'X-Requested-With': 'fieldnotes' } : {}, ...(data ? { body: JSON.stringify(data) } : {}) });
  if (!response.headers.get('content-type')?.includes('application/json')) throw new Error('Your session may have expired. Sign in through Overview in another tab, then try again.');
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The request failed. Keep your text and try again.');
  return result;
}
function failure(error) { message(error instanceof TypeError ? 'Could not connect or your session expired. Keep this tab open, sign in through Overview in another tab, then try again.' : error.message, true); }
async function run(operation) {
  if (busy) return;
  setBusy(true); message('');
  try { await operation(); } catch (error) { failure(error); } finally { setBusy(false); }
}
function draft() { return { kind: $('#kind').value, title: $('#title').value, summary: $('#summary').value, tags: $('#tags').value.split(',').map(tag => tag.trim()).filter(Boolean), body: $('#body').value }; }
function markDirty() { dirty = true; $('#save-status').textContent = 'Unsaved changes'; updateCount(); }
function updateCount() { const text = $('#body').value.trim(); $('#word-count').textContent = `${text ? text.split(/\s+/).length : 0} words`; }
function ask(text) {
  return new Promise(resolve => {
    const dialog = $('#confirm-dialog');
    $('#confirm-question').textContent = text;
    dialog.returnValue = '';
    dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
    dialog.showModal();
  });
}
async function mayLeave() { return !dirty || await ask('You have unsaved writing. Discard those changes?'); }
function setMode(preview) {
  $('#body').hidden = preview; $('#preview').hidden = !preview;
  $('#write-tab').setAttribute('aria-pressed', String(!preview)); $('#preview-tab').setAttribute('aria-pressed', String(preview));
}
function fill(entry) {
  current = entry; dirty = false;
  $('#editor-empty').hidden = true; $('#entry-form').hidden = false;
  const value = entry?.draft || { kind: 'note', title: '', summary: '', tags: [], body: '' };
  fields.forEach(key => { $(`#${key}`).value = key === 'tags' ? value.tags.join(', ') : value[key]; });
  const published = !!entry?.published; const trash = !!entry?.deletedAt;
  const changed = published && JSON.stringify(value) !== JSON.stringify(entry.published);
  $('#entry-state').textContent = trash ? 'In trash' : published ? changed ? 'Published · draft changes' : 'Published' : 'Private draft';
  $('#save-status').textContent = entry ? `Saved ${new Date(entry.updatedAt).toLocaleString()}` : 'New entry · not saved';
  $('#save').hidden = trash;
  $('#publish').hidden = trash; $('#publish').textContent = published ? 'Publish update' : 'Publish entry';
  $('#unpublish').hidden = !published || trash; $('#trash').hidden = !entry || trash; $('#restore').hidden = !trash;
  $('#public-link').hidden = !published;
  if (published) $('#public-link').href = `/${entry.published.kind === 'blog' ? 'blog' : 'learn'}/${entry.slug}/`;
  $('#publish-help').textContent = trash ? 'This entry is no longer public. Restore it as a private draft.' : published ? 'Save your draft as you write. The published version changes only when you choose Publish update.' : 'Saving keeps this entry private. Publishing makes it visible to everyone.';
  $('#entry-fields').disabled = trash;
  setMode(false); updateCount(); message('');
}
async function refreshLibrary() {
  const request = ++listRequest;
  const items = await api(`entries?q=${encodeURIComponent($('#search').value)}`);
  if (request !== listRequest) return;
  const filter = $('#filter').value;
  const visible = items.filter(entry => filter === 'trash' ? entry.deletedAt : !entry.deletedAt && (filter === 'all' || entry.kind === filter || (filter === 'private' && !entry.url) || (filter === 'published' && entry.url)));
  $('#library-count').textContent = `${visible.length} ${visible.length === 1 ? 'entry' : 'entries'}`;
  const list = $('#entry-list'); list.replaceChildren();
  if (!visible.length) { const empty = document.createElement('p'); empty.className = 'library-empty'; empty.textContent = items.length ? 'No entries match this view.' : 'Your ideas belong here. Start with a new entry.'; list.append(empty); }
  for (const entry of visible) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'library-entry';
    button.classList.toggle('selected', current?.id === entry.id);
    const type = document.createElement('span'); type.className = 'entry-type'; type.textContent = `${entry.kind === 'blog' ? 'BLOG POST' : 'LEARNING NOTE'} · ${entry.deletedAt ? 'Trash' : entry.url ? 'Published' : 'Private'}`;
    const title = document.createElement('strong'); title.textContent = entry.title;
    const meta = document.createElement('span'); meta.className = 'entry-meta'; meta.textContent = entry.hasChanges ? 'Unpublished changes' : new Date(entry.updatedAt).toLocaleDateString();
    button.append(type, title, meta);
    button.addEventListener('click', () => run(async () => { if (!await mayLeave()) return; fill(await api(`entries/${entry.id}`)); await refreshLibrary(); }));
    list.append(button);
  }
}
async function newEntry() { if (busy || !await mayLeave()) return; fill(null); $('#title').focus(); refreshLibrary().catch(failure); }
async function save() {
  if (!$('#entry-form').reportValidity()) return false;
  if (new TextEncoder().encode($('#body').value).length > 65536) throw new Error('Keep the Markdown under 64 KiB. Download a copy before shortening it.');
  const result = await api(current ? `entries/${current.id}/save` : 'entries', { ...draft(), ...(current ? { revision: current.revision } : {}) });
  fill(result); message('Draft saved.'); await refreshLibrary(); return true;
}
$('#new-entry').addEventListener('click', newEntry); $('#first-entry').addEventListener('click', newEntry);
fields.forEach(key => $(`#${key}`).addEventListener('input', markDirty));
$('#entry-form').addEventListener('submit', event => { event.preventDefault(); run(save); });
$('#write-tab').addEventListener('click', () => setMode(false));
$('#preview-tab').addEventListener('click', () => run(async () => { const result = await api('preview', { body: $('#body').value }); $('#preview').innerHTML = result.html; setMode(true); }));
$('#publish').addEventListener('click', () => run(async () => {
  if (!$('#entry-form').reportValidity()) return;
  if (!await ask('Publish this version for everyone to read on your site?')) return;
  if ((!current || dirty) && !await save()) return;
  fill(await api(`entries/${current.id}/publish`, { revision: current.revision }));
  message('Published. Your writing is now visible on your site.'); await refreshLibrary();
}));
for (const action of ['unpublish', 'trash', 'restore']) {
  $(`#${action}`).addEventListener('click', () => run(async () => {
    if (!current) return;
    const prompts = { unpublish: 'Remove the published version from your site? The saved draft stays in your library.', trash: 'Move this entry to trash and remove it from your public site? You can restore the saved draft later.', restore: 'Restore this entry as a private draft?' };
    if (!await mayLeave() || !await ask(prompts[action])) return;
    fill(await api(`entries/${current.id}/${action}`, { revision: current.revision }));
    message(action === 'trash' ? 'Moved to trash. You can restore it using the Trash filter.' : action === 'restore' ? 'Restored as a private draft.' : 'Unpublished. Your saved draft is private.');
    await refreshLibrary();
  }));
}
$('#download').addEventListener('click', () => {
  const value = draft();
  const blob = new Blob([`# ${value.title || 'Untitled'}\n\n${value.summary ? value.summary + '\n\n' : ''}${value.body}\n`], { type: 'text/markdown;charset=utf-8' });
  const link = document.createElement('a'); link.href = URL.createObjectURL(blob); link.download = `${value.title.replace(/[^a-z0-9]+/gi, '-').slice(0, 60) || 'entry'}.md`; link.click(); setTimeout(() => URL.revokeObjectURL(link.href), 1000);
});
$('#search').addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => refreshLibrary().catch(failure), 200); });
$('#filter').addEventListener('change', () => refreshLibrary().catch(failure));
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && !$('#entry-form').hidden) { event.preventDefault(); if (!current?.deletedAt) run(save); } });
refreshLibrary().catch(failure);
