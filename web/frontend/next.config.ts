import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  output: process.env.BUILD_STANDALONE === 'true' ? 'standalone' : undefined,
  // Allow common localhost aliases so the dev server doesn't block HMR or
  // client hydration when the browser connects via 127.0.0.1 or a LAN IP.
  allowedDevOrigins: ['localhost', '127.0.0.1', '0.0.0.0', '*.local'],
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'api.slingacademy.com',
        port: ''
      }
    ]
  },
  transpilePackages: ['geist'],
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/:path*`
      }
    ];
  }
};

export default nextConfig;
