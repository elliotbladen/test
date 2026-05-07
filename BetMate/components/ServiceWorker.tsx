'use client';
import { useEffect } from 'react';

export default function ServiceWorker() {
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    if (process.env.NODE_ENV !== 'production') {
      navigator.serviceWorker.getRegistrations()
        .then((registrations) => Promise.all(registrations.map((registration) => registration.unregister())))
        .then(() => caches?.keys?.())
        .then((keys) => Promise.all((keys ?? []).map((key) => caches.delete(key))))
        .catch(() => {});
      return;
    }

    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }, []);
  return null;
}
