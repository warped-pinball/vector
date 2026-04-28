// This file is part of the Warped Pinball Vector Project.
// https://creativecommons.org/licenses/by-nc/4.0/
// This work is licensed under CC BY-NC 4.0

// CACHE_NAME and PRECACHE_URLS are injected by dev/build.py at build time.
// The cache name embeds the firmware version so the old cache is automatically
// evicted when a new firmware build is deployed.
var CACHE_NAME = "PLACEHOLDER_CACHE_NAME";
var PRECACHE_URLS = "PLACEHOLDER_PRECACHE_URLS";

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches
      .open(CACHE_NAME)
      .then(function (cache) {
        // cache:'reload' forces a network fetch, bypassing immutable HTTP-cache
        // entries, so the service worker always stores fresh copies on install.
        var requests = PRECACHE_URLS.map(function (url) {
          return new Request(url, { cache: "reload" });
        });
        return cache.addAll(requests);
      })
      .then(function () {
        // Skip waiting so the new SW activates immediately without requiring
        // all existing tabs to be closed first.
        return self.skipWaiting();
      }),
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (keys) {
        // Delete every cache whose name does not match the current version.
        return Promise.all(
          keys
            .filter(function (key) {
              return key !== CACHE_NAME;
            })
            .map(function (key) {
              return caches.delete(key);
            }),
        );
      })
      .then(function () {
        // Take immediate control of all open pages so they start using the
        // new cache without a navigation.
        return self.clients.claim();
      }),
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  var url = new URL(req.url);

  // Only intercept same-origin requests.
  if (url.origin !== self.location.origin) return;

  // Let API requests go straight to the network — they must never be cached.
  if (url.pathname.startsWith("/api/")) return;

  // Serve all static assets (HTML, CSS, JS, SVG, …) from the SW cache.
  // ignoreSearch strips any ?v=VERSION query param injected by the build step
  // so the cached entry (stored under the bare pathname) is found regardless
  // of the version suffix that appears in the HTML source.
  event.respondWith(
    caches.match(req, { ignoreSearch: true }).then(function (cached) {
      if (cached) return cached;

      // Asset not in cache yet — fetch from network and store for next time.
      return fetch(req).then(function (response) {
        if (!response || response.status !== 200 || response.type !== "basic") {
          return response;
        }
        var clone = response.clone();
        // Cache under the bare pathname and return the response once stored.
        return caches
          .open(CACHE_NAME)
          .then(function (cache) {
            return cache.put(new Request(url.pathname), clone);
          })
          .then(function () {
            return response;
          })
          .catch(function () {
            return response;
          });
      });
    }),
  );
});
