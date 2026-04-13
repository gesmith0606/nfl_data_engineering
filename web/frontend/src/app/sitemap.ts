import type { MetadataRoute } from 'next';

const BASE_URL = 'https://frontend-jet-seven-33.vercel.app';

/**
 * Next.js App Router sitemap generation.
 * Returned at /sitemap.xml — picked up automatically by crawlers.
 */
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: BASE_URL,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1.0
    },
    {
      url: `${BASE_URL}/dashboard/projections`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 0.9
    },
    {
      url: `${BASE_URL}/dashboard/predictions`,
      lastModified: new Date(),
      changeFrequency: 'weekly',
      priority: 0.8
    },
    {
      url: `${BASE_URL}/dashboard/news`,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 0.8
    },
    {
      url: `${BASE_URL}/dashboard/advisor`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.7
    },
    {
      url: `${BASE_URL}/dashboard/draft`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.7
    },
    {
      url: `${BASE_URL}/dashboard/accuracy`,
      lastModified: new Date(),
      changeFrequency: 'monthly',
      priority: 0.5
    }
  ];
}
