// Selvra: tar emot morgonrapporten som push, sparar den på telefonen och visar en notis.
// Rapporten lagras bara här, i telefonens cache; ingen server sparar den.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));

self.addEventListener("push", (e) => {
  let d;
  try {
    d = e.data.json();
  } catch {
    d = { titel: "Selvra", kort: e.data ? e.data.text() : "", text: e.data ? e.data.text() : "" };
  }
  const spara = caches.open("selvra").then((c) =>
    c.put("senaste.json", new Response(JSON.stringify(d), { headers: { "content-type": "application/json" } }))
  );
  const meddela = self.clients.matchAll({ type: "window" }).then((ws) => ws.forEach((w) => w.postMessage("ny-rapport")));
  const notis = self.registration.showNotification(d.titel || "Selvra", {
    body: d.kort || "",
    tag: "selvra-morgon",
    icon: "ikon-192.png",
    data: { url: "./" },
  });
  e.waitUntil(Promise.all([spara, notis]).then(() => meddela));
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  e.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((ws) => {
      for (const w of ws) if ("focus" in w) return w.focus();
      return self.clients.openWindow("./");
    })
  );
});
