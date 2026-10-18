import { defineCollection } from 'astro:content';
import { glob } from 'astro/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

// The repository's docs are the site source; there is no second editable copy.
export const collections = {
  docs: defineCollection({
    loader: glob({ base: './docs', pattern: '**/[^_]*.{md,mdx}' }),
    schema: docsSchema(),
  }),
};
