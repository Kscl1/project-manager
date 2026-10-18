import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineMdastPlugin } from 'satteri';

// Pages in docs/ link to each other as `getting-started.md`, which GitHub follows.
// On the site each page is a directory URL, so this rewrites relative links to a
// docs/ Markdown file into that page's URL. Other links are left alone.
const docs = path.resolve('docs');
const base = '/project-manager/';

export const mdLinks = defineMdastPlugin({
  name: 'md-links',
  link(node, context) {
    if (!context.fileURL || /^[a-z][a-z0-9+.-]*:|^[/#]/i.test(node.url)) return;
    const [target, hash] = node.url.split('#');
    if (!target.endsWith('.md')) return;
    const file = fileURLToPath(context.fileURL);
    const page = path.relative(docs, path.resolve(path.dirname(file), target));
    if (page.startsWith('..')) return;
    const dir = `${page.split(path.sep).join('/').slice(0, -'.md'.length)}/`;
    const slug = dir === 'index/' ? '' : dir.endsWith('/index/') ? dir.slice(0, -'index/'.length) : dir;
    context.setProperty(node, 'url', base + slug + (hash ? `#${hash}` : ''));
  },
});
