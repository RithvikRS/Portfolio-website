import assert from 'node:assert/strict';
import { readFile, access } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const root = new URL('../', import.meta.url);
const pageNames = ['index.html', 'Projects.html', 'Awards.html', '404.html', 'error.html'];
const pages = new Map(await Promise.all(pageNames.map(async name => [name, await readFile(new URL(name, root), 'utf8')])));
let checkedLinks = 0;
for (const [name, html] of pages) {
  assert.equal((html.match(/<h1\b/g) || []).length, 1, `${name}: exactly one primary heading`);
  assert.match(html, /<html lang="en"/, `${name}: document language`);
  assert.match(html, /<title>[^<]+<\/title>/, `${name}: page title`);
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
  assert.equal(ids.length, new Set(ids).size, `${name}: duplicate IDs`);
  for (const match of html.matchAll(/\b(?:href|src)="([^"]+)"/g)) {
    const link = match[1].replaceAll('&amp;', '&');
    if (/^(?:https?:|mailto:|data:)/.test(link)) continue;
    const [path, hash] = link.split('#');
    const target = path || name;
    await access(new URL(target, root));
    if (hash && pages.has(target)) assert.ok(pages.get(target).includes(`id="${hash}"`), `${name}: missing anchor ${link}`);
    checkedLinks++;
  }
  assert.ok(!html.includes('Resume-Rithvik-Rajani-Kanth-Sasi.pdf'), `${name}: old CV link`);
}
const content = JSON.parse(await readFile(new URL('data/portfolio.json', root), 'utf8'));
const cv = await readFile(new URL(content.cv, root));
assert.equal(cv.subarray(0, 5).toString(), '%PDF-', 'CV download is a PDF');
assert.equal(new Set(content.projects.map(project => project.id)).size, content.projects.length, 'Unique project anchors');
for (const project of content.projects) {
  assert.ok(Array.isArray(project.technologies), `${project.id}: list confirmed tools, or use an empty array`);
  assert.ok(Array.isArray(project.skills) && project.skills.length > 0, `${project.id}: applied skills are required`);
  const labels = [...project.technologies, ...project.skills];
  assert.ok(labels.every(label => typeof label === 'string' && label.trim()), `${project.id}: nonempty skill labels`);
  assert.equal(new Set(labels).size, labels.length, `${project.id}: duplicate skills or tools`);
}
assert.match(content.credly, /^https:\/\/www\.credly\.com\/users\//, 'Credly profile URL');
for (const name of ['index.html', 'Awards.html']) assert.ok(pages.get(name).includes(`href="${content.credly}"`), `${name}: Credly profile link`);
console.log(`Checked ${pages.size} pages, ${checkedLinks} local links, unique anchors, and CV: ${fileURLToPath(new URL(content.cv, root))}`);
