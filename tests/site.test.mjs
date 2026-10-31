import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';

const root = path.resolve('dist');
const base = '/project-manager/';
const html = (name) => readFileSync(path.join(root, name, 'index.html'), 'utf8');
// Every release bumps the README's install line; the site's getting-started pages must name the same tag.
const release = readFileSync('README.md', 'utf8').match(/git clone --branch (v\d+\.\d+\.\d+\S*)/)[1];

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
    assert.ok(html(name).includes(`--branch ${release}`), `${name} installs ${release}, the README's release`);
    assert.match(html(name), /pm-setup/);
    assert.match(html(name), /tools\/setup\/app\.py/);
  }
  // The agent install page clones the release too, and its prompt points the agent at the page in the same language.
  for (const [name, source] of [['install-with-agent', 'docs/install-with-agent.md'], ['tr/install-with-agent', 'docs/tr/install-with-agent.md']]) {
    assert.ok(html(name).includes(`--branch ${release}`), `${name} installs ${release}, the README's release`);
    assert.ok(html(name).includes(`raw.githubusercontent.com/Kscl1/project-manager/main/${source}`), `${name} prompt names ${source}`);
    assert.match(html(name), /handover\.md/);
  }
});

const pages = readdirSync('docs').filter((name) => name.endsWith('.md')).map((name) => name.slice(0, -'.md'.length));
const slug = (page) => (page === 'index' ? '' : `${page}/`);

test('every English page has a Turkish page, and no Turkish page shows the missing-translation notice', () => {
  for (const page of pages) {
    assert.ok(existsSync(`docs/tr/${page}.md`), `docs/${page}.md has no docs/tr/${page}.md`);
    assert.doesNotMatch(html(`tr/${slug(page)}`), /Bu içerik henüz dilinizde mevcut değil\./);
  }
});

// The menu once rendered an empty group (autogenerate on a directory that matched no page) and every test passed.
test('the menu of a content page links every page in its language', () => {
  for (const [page, prefix] of [['getting-started', ''], ['tr/getting-started', 'tr/']]) {
    const nav = html(page).match(/<sl-sidebar-pane[\s\S]*?<\/sl-sidebar-pane>/)?.[0] ?? '';
    for (const target of pages) {
      assert.ok(nav.includes(`href="${base}${prefix}${slug(target)}"`), `${page} menu lacks ${prefix}${slug(target)}`);
    }
  }
});

test('the introduction is a landing page whose buttons lead to getting started', () => {
  for (const [page, prefix] of [['', ''], ['tr', 'tr/']]) {
    assert.match(html(page), /class="hero/);
    assert.ok(html(page).includes(`href="${base}${prefix}getting-started/"`), `${page || 'index'} hero has no getting-started button`);
  }
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
