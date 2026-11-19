import { defineConfig } from 'vite';
// vite-plugin-pwa disabled temporarily — workbox-build dynamic require not supported in ESM context
// Re-enable after upgrading vite to v5+ or vite-plugin-pwa to v0.20+
// import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
    plugins: [
        // VitePWA({
        //     registerType: 'autoUpdate',
        //     injectRegister: 'auto',
        //     manifest: {
        //         name: 'Capstone CRM',
        //         short_name: 'CRM',
        //         description: 'Capstone CRM – staff and customer support portal',
        //         theme_color: '#d98d7e',
        //         background_color: '#fbf7f2',
        //         display: 'standalone',
        //         start_url: '/',
        //     },
        //     workbox: {
        //         globPatterns: ['**/*.{js,css,html,png,svg,ico,woff2}'],
        //         navigateFallback: '/index.html',
        //         runtimeCaching: [
        //             {
        //                 urlPattern: /^https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/i,
        //                 handler: 'CacheFirst',
        //                 options: {
        //                     cacheName: 'google-fonts',
        //                     expiration: { maxEntries: 20, maxAgeSeconds: 60 * 60 * 24 * 365 },
        //                     cacheableResponse: { statuses: [0, 200] },
        //                 },
        //             },
        //         ],
        //     },
        // }),
    ],
    preview: {
        port: 5173,
        strictPort: true,
    },
});
