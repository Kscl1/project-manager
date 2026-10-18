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
      sidebar: [
        {
          label: 'Documentation',
          translations: { tr: 'Belgeler' },
          items: [{ autogenerate: { directory: '.' } }],
        },
      ],
    }),
  ],
});
