// ERPlora Hub Service Worker
const CACHE_NAME = 'erplora-hub-v2';

// Static assets to cache for offline use (never cache HTML pages)
const STATIC_CACHE_URLS = [
    '/static/js/alpine.min.js',
    '/static/js/htmx.min.js',
    '/static/fonts/plus-jakarta-sans/plus-jakarta-sans.css',
    '/static/img/logo.png',
    '/offline/',
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[ServiceWorker] Install');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[ServiceWorker] Caching static assets');
                return cache.addAll(STATIC_CACHE_URLS);
            })
            .then(() => {
                console.log('[ServiceWorker] Skip waiting');
                return self.skipWaiting();
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[ServiceWorker] Activate');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((cacheName) => cacheName !== CACHE_NAME)
                    .map((cacheName) => {
                        console.log('[ServiceWorker] Deleting old cache:', cacheName);
                        return caches.delete(cacheName);
                    })
            );
        }).then(() => {
            console.log('[ServiceWorker] Claiming clients');
            return self.clients.claim();
        })
    );
});

// Fetch event
self.addEventListener('fetch', (event) => {
    // Skip non-GET requests
    if (event.request.method !== 'GET') {
        return;
    }

    // Skip cross-origin requests
    if (!event.request.url.startsWith(self.location.origin)) {
        return;
    }

    // Skip admin and API requests
    const url = new URL(event.request.url);
    if (url.pathname.startsWith('/admin/') ||
        url.pathname.startsWith('/api/') ||
        url.pathname.startsWith('/ht/')) {
        return;
    }

    // Static assets: cache-first with background revalidation
    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(event.request)
                .then((cachedResponse) => {
                    if (cachedResponse) {
                        // Serve from cache, update in background
                        event.waitUntil(
                            fetch(event.request)
                                .then((networkResponse) => {
                                    if (networkResponse && networkResponse.status === 200) {
                                        caches.open(CACHE_NAME)
                                            .then((cache) => cache.put(event.request, networkResponse));
                                    }
                                })
                                .catch(() => {/* Network failed, that's ok */})
                        );
                        return cachedResponse;
                    }

                    // Not in cache, fetch from network and cache it
                    return fetch(event.request)
                        .then((networkResponse) => {
                            if (networkResponse && networkResponse.status === 200) {
                                const responseToCache = networkResponse.clone();
                                caches.open(CACHE_NAME)
                                    .then((cache) => cache.put(event.request, responseToCache));
                            }
                            return networkResponse;
                        })
                        .catch(() => caches.match('/offline/'));
                })
        );
        return;
    }

    // HTML/navigation requests: network-first, fallback to offline page
    event.respondWith(
        fetch(event.request)
            .then((networkResponse) => networkResponse)
            .catch(() => caches.match('/offline/'))
    );
});

// Handle messages from the main thread
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});
