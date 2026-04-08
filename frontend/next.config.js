/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: 'http://multiagente-alb-1689721042.sa-east-1.elb.amazonaws.com/:path*',
      },
    ];
  },
}
module.exports = nextConfig;
