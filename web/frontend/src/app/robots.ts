import type { MetadataRoute } from 'next';

/**
 * Next.js App Router robots generation.
 * Returned at /robots.txt — replaces the static public/robots.txt.
 * Allows all public dashboard pages (the static file blocked /dashboard).
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: '*',
      allow: '/',
      disallow: '/api/'
    },
    sitemap: 'https://frontend-jet-seven-33.vercel.app/sitemap.xml'
  };
}
