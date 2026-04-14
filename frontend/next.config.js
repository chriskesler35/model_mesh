const backendPort = process.env.DEVFORGEAI_BACKEND_PORT || '19001'
const rawBackendUrl = process.env.NEXT_PUBLIC_API_URL || `http://localhost:${backendPort}`
const backendUrl = rawBackendUrl.replace(/\/+$/, '')

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    DEVFORGEAI_BACKEND_PORT: process.env.DEVFORGEAI_BACKEND_PORT,
  },
  async rewrites() {
    return [
      {
        source: '/v1/projects',
        destination: `${backendUrl}/v1/projects/`,
      },
      {
        source: '/v1/:path*',
        destination: `${backendUrl}/v1/:path*`,
      },
      {
        source: '/docs',
        destination: `${backendUrl}/docs`,
      },
      {
        source: '/openapi.json',
        destination: `${backendUrl}/openapi.json`,
      },
      {
        source: '/redoc',
        destination: `${backendUrl}/redoc`,
      },
    ]
  },
}

module.exports = nextConfig
