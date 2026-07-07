/**
 * Mola Yönetim Merkezi — Service Worker
 * Statik dosyaları önbelleğe alır; çevrimdışı kabuk (shell) desteği sağlar.
 */

const CACHE_NAME = "mola-merkezi-v1";

const STATIC_ASSETS = [
  "./",
  "./index.html",
  "./dashboard.html",
  "./employee.html",
  "./style.css",
  "./script.js",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
];

const OFFLINE_PAGES = ["./index.html", "./dashboard.html", "./employee.html"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
      )
      .then(() => self.clients.claim())
  );
});

function isApiRequest(url) {
  return (
    url.pathname.startsWith("/auth") ||
    url.pathname.startsWith("/employees") ||
    url.pathname.startsWith("/users") ||
    url.pathname.startsWith("/breaks") ||
    url.pathname.startsWith("/dashboard") ||
    url.pathname.startsWith("/health")
  );
}

self.addEventListener("fetch", (event) => {
  const { request } = event;

  if (request.method !== "GET") return;

  const url = new URL(request.url);

  /* API istekleri — ağ üzerinden; önbelleğe alınmaz */
  if (isApiRequest(url)) {
    event.respondWith(
      fetch(request).catch(() =>
        new Response(
          JSON.stringify({ detail: "Çevrimdışı moddasınız. İnternet bağlantınızı kontrol edin." }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    return;
  }

  /* Statik dosyalar — önbellek öncelikli, ağ yedekli */
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;

      return fetch(request)
        .then((response) => {
          if (response.ok && url.origin === self.location.origin) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        })
        .catch(async () => {
          if (request.mode === "navigate") {
            for (const page of OFFLINE_PAGES) {
              const fallback = await caches.match(page);
              if (fallback) return fallback;
            }
            return caches.match("./index.html");
          }
          return new Response("", { status: 503, statusText: "Offline" });
        });
    })
  );
});
