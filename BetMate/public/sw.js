const CACHE = 'betmate-v1';

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = e.request.url;

  // Always go network-first for API, Supabase, and odds data
  if (
    url.includes('/api/') ||
    url.includes('supabase') ||
    url.includes('the-odds-api')
  ) {
    e.respondWith(fetch(e.request).catch(() => caches.match(e.request)));
    return;
  }

  // Cache-first for static assets (_next/static, icons, manifest)
  if (
    url.includes('/_next/static/') ||
    url.includes('/icons/') ||
    url.includes('/manifest.json')
  ) {
    e.respondWith(
      caches.match(e.request).then(cached =>
        cached || fetch(e.request).then(res => {
          const clone = res.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
          return res;
        })
      )
    );
    return;
  }

  // Everything else: network with cache fallback
  e.respondWith(
    fetch(e.request).catch(() => caches.match(e.request))
  );
});
