import { mkdir, readdir, readFile, open, rename, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';

export class NotesError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
const fail = (status, message) => { throw new NotesError(status, message); };
const idPattern = /^[a-f0-9-]{36}$/;
export function validateDraft(value) {
  if (!value || !['blog', 'note'].includes(value.kind)) fail(400, 'Choose a blog post or learning note.');
  const title = typeof value.title === 'string' ? value.title.trim() : '';
  const summary = typeof value.summary === 'string' ? value.summary.trim() : '';
  if (!title || title.length > 140) fail(400, 'Use a title of 1–140 characters.');
  if (summary.length > 320) fail(400, 'Keep the summary under 320 characters.');
  if (typeof value.body !== 'string' || Buffer.byteLength(value.body) > 65536) fail(400, 'Keep the Markdown under 64 KiB.');
  if (!Array.isArray(value.tags) || value.tags.length > 8 || value.tags.some(tag => typeof tag !== 'string' || !tag.trim() || tag.trim().length > 32)) fail(400, 'Use up to eight tags, each 1–32 characters.');
  return { kind: value.kind, title, summary, body: value.body, tags: [...new Set(value.tags.map(tag => tag.trim().toLowerCase()))] };
}
export const publicPath = entry => `/${entry.published.kind === 'blog' ? 'blog' : 'learn'}/${entry.slug}/`;
export const entrySummary = entry => ({ id: entry.id, revision: entry.revision, title: entry.draft.title, kind: entry.draft.kind, tags: entry.draft.tags, updatedAt: entry.updatedAt, deletedAt: entry.deletedAt, publishedAt: entry.publishedAt, url: entry.published ? publicPath(entry) : null, hasChanges: !!entry.published && JSON.stringify(entry.draft) !== JSON.stringify(entry.published) });

// One process owns the store. Serial writes + optimistic revisions prevent lost
// edits, and fsync/rename ensures readers see complete files after a restart.
export async function createNotesStore(directory) {
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const entries = new Map();
  for (const name of await readdir(directory)) {
    if (!name.endsWith('.json')) continue;
    const content = await readFile(join(directory, name), 'utf8');
    if (Buffer.byteLength(content) > 1000000) throw new Error('An entry exceeds the storage limit. Restore the notes backup.');
    const entry = JSON.parse(content);
    if (!idPattern.test(entry.id) || name !== `${entry.id}.json` || entry.schema !== 1 || !Number.isSafeInteger(entry.revision) || entry.revision < 1 || !/^[a-z0-9-]+$/.test(entry.slug) || !Number.isFinite(Date.parse(entry.updatedAt)) || !Number.isFinite(Date.parse(entry.createdAt)) || (entry.publishedAt && !Number.isFinite(Date.parse(entry.publishedAt))) || (entry.deletedAt && entry.published)) throw new Error('Invalid notes data. Restore a consistent backup.');
    validateDraft(entry.draft);
    if (entry.published) validateDraft(entry.published);
    entries.set(entry.id, entry);
  }
  if (entries.size > 250) throw new Error('The writing library exceeds the 250-entry limit.');
  let queue = Promise.resolve();
  async function persist(entry) {
    const target = join(directory, `${entry.id}.json`);
    const temporary = join(directory, `${entry.id}.${randomUUID()}.tmp`);
    try {
      const file = await open(temporary, 'wx', 0o600);
      try { await file.writeFile(JSON.stringify(entry) + '\n'); await file.sync(); } finally { await file.close(); }
      await rename(temporary, target);
      entries.set(entry.id, entry);
      if (process.platform !== 'win32') {
        const dir = await open(directory, 'r');
        try { await dir.sync(); } finally { await dir.close(); }
      }
    } finally { await unlink(temporary).catch(error => { if (error.code !== 'ENOENT') throw error; }); }
    return structuredClone(entry);
  }
  function serial(operation) {
    const next = queue.then(operation);
    queue = next.catch(() => {});
    return next;
  }
  return {
    list: () => [...entries.values()].map(entrySummary).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    published: kind => [...entries.values()].filter(entry => !entry.deletedAt && entry.published?.kind === kind).sort((a, b) => b.publishedAt.localeCompare(a.publishedAt)).map(entry => structuredClone(entry)),
    get: id => { const entry = entries.get(id); if (!entry) fail(404, 'Entry not found.'); return structuredClone(entry); },
    export: () => ({ schema: 1, exportedAt: new Date().toISOString(), entries: [...entries.values()] }),
    create: value => serial(async () => {
      if (entries.size >= 250) fail(409, 'The library has reached 250 entries, including trash. Export and archive it before adding more.');
      const draft = validateDraft(value);
      const id = randomUUID(); const now = new Date().toISOString();
      const slug = `${draft.title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'entry'}-${id.slice(0, 8)}`;
      return persist({ schema: 1, id, slug, revision: 1, draft, published: null, createdAt: now, updatedAt: now, publishedAt: null, deletedAt: null });
    }),
    change: (id, action, value) => serial(async () => {
      const current = entries.get(id);
      if (!current) fail(404, 'Entry not found.');
      if (value.revision !== current.revision) fail(409, 'This entry changed in another tab. Copy your unsaved text, then reload it before saving.');
      const entry = structuredClone(current);
      if (entry.deletedAt && action !== 'restore') fail(409, 'Restore this entry from trash first.');
      if (action === 'save') entry.draft = validateDraft(value);
      else if (action === 'publish') {
        if (!entry.draft.body.trim()) fail(400, 'Add some writing before publishing.');
        entry.published = structuredClone(entry.draft);
        entry.publishedAt ||= new Date().toISOString();
      } else if (action === 'unpublish') { entry.published = null; entry.publishedAt = null; }
      else if (action === 'trash') { entry.deletedAt = new Date().toISOString(); entry.published = null; entry.publishedAt = null; }
      else if (action === 'restore') { entry.deletedAt = null; }
      else fail(400, 'Unknown action.');
      entry.revision++; entry.updatedAt = new Date().toISOString();
      return persist(entry);
    })
  };
}
