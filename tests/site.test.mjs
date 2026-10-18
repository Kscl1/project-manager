import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve('dist');
const base = '/project-manager/';
const html = (name) => readFileSync(path.join(root, name, 'index.html'), 'utf8');

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const name = path.join(dir, entry.name);
    return entry.isDirectory() ? files(name) : [name];
  });
}

test('English and Turkish pages build at the project Pages base', () => {
  for (const name of ['', 'getting-started', 'how-it-works', 'tr', 'tr/getting-started']) {
    assert.match(html(name), /<html[^>]*lang="(?:en|tr)"/);
    assert.match(html(name), /\/project-manager\/_astro\//);
  }
  assert.match(html(''), /Who is it for/);
  assert.match(html('tr'), /Kimler için/);
  for (const name of ['getting-started', 'tr/getting-started']) {
    assert.match(html(name), /v0\.1\.0-alpha\.1/);
    assert.match(html(name), /pm-setup/);
    assert.match(html(name), /tools\/setup\/app\.py/);
  }
});

test('missing Turkish translation uses English with Starlight notice', () => {
  assert.equal(existsSync('docs/tr/how-it-works.md'), false);
  assert.match(html('tr/how-it-works'), /Bu içerik henüz dilinizde mevcut değil\./);
  assert.match(html('tr/how-it-works'), /One request, from intent to evidence/);
});

test('edit links point at the actual single-source documents', () => {
  for (const [page, source] of [['', 'index.md'], ['how-it-works', 'how-it-works.md'], ['tr/getting-started', 'tr/getting-started.md']]) {
    assert.ok(html(page).includes(`https://github.com/Kscl1/project-manager/edit/main/docs/${source}`));
    assert.ok(!html(page).includes('/edit/main/docs/docs/'));
  }
});

test('publishing is manual and main-only, never triggered by a push', () => {
  const workflow = readFileSync('.github/workflows/pages.yml', 'utf8');
  assert.match(workflow, /^  workflow_dispatch:/m);
  assert.doesNotMatch(workflow, /^  push:/m);
  assert.match(workflow, /github\.event_name == 'workflow_dispatch' && github\.ref == 'refs\/heads\/main'/);
  assert.match(workflow, /enablement: false/);
});

test('the existing architecture diagram is prepared for Mermaid rendering', () => {
  assert.match(html('how-it-works'), /class="[^"]*mermaid/);
  assert.match(html('how-it-works'), /flowchart TB/);
});

test('all built HTML local links and assets resolve inside the project base', () => {
  for (const filename of files(root).filter((name) => name.endsWith('.html'))) {
    const url = `https://example.test${base}${path.relative(root, filename).replaceAll('\\', '/')}`;
    for (const match of readFileSync(filename, 'utf8').matchAll(/(?:href|src)="([^"]+)"/g)) {
      const target = new URL(match[1].replaceAll('&amp;', '&'), url);
      if (target.origin !== 'https://example.test') continue;
      assert.ok(target.pathname.startsWith(base), `${filename}: outside site base: ${target.pathname}`);
      const relative = decodeURIComponent(target.pathname.slice(base.length));
      const destination = path.join(root, relative);
      assert.ok(
        existsSync(destination) || existsSync(path.join(destination, 'index.html')),
        `${filename}: missing ${target.pathname}`,
      );
    }
  }
});
