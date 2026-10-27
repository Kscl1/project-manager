import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';
import mermaid from 'astro-mermaid';
import { satteri } from '@astrojs/markdown-satteri';
import { mdLinks } from './src/md-links.mjs';

export default defineConfig({
  site: 'https://kscl1.github.io',
  base: '/project-manager',
  trailingSlash: 'always',
  markdown: { processor: satteri({ mdastPlugins: [mdLinks] }) },
  integrations: [
    mermaid({ enableLog: false }),
    starlight({
      title: 'project-manager',
      description: 'Tasks, decisions and working rules next to your code.',
      defaultLocale: 'root',
      locales: {
        root: { label: 'English', lang: 'en' },
        tr: { label: 'Türkçe', lang: 'tr' },
      },
      social: [{ icon: 'github', label: 'GitHub', href: 'https://github.com/Kscl1/project-manager' }],
      editLink: { baseUrl: 'https://github.com/Kscl1/project-manager/edit/main/' },
      // Each page by slug: Starlight links the reader's language and uses that page's title. Its own default menu
      // nests translated pages under docs/tr, because the pages live outside src/content/docs. A new page goes here;
      // the site test fails when a page is missing from the menu.
      sidebar: ['index', 'how-it-works', 'getting-started', 'own-tools', 'upgrading'],
    }),
  ],
});
