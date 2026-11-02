import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readPage = (path) => readFile(new URL(`../dist/${path}`, import.meta.url), "utf8");

const assertLabOrder = (page) => {
  const home = page.indexOf('data-home-status-panel');
  const metrics = page.indexOf('data-metrics-panel');
  const meshtastic = page.indexOf('data-meshtastic-panel');
  const meshtasticStatus = page.indexOf('data-meshtastic-status-panel');
  const relay = page.indexOf('data-relay-panel');

  assert.ok(home !== -1 && metrics !== -1 && meshtastic !== -1 && meshtasticStatus !== -1 && relay !== -1);
  assert.ok(home < metrics && metrics < meshtastic && meshtastic < meshtasticStatus && meshtasticStatus < relay);
};

test("generates bilingual portfolio entries without a portrait", async () => {
  const [spanish, english] = await Promise.all([readPage("index.html"), readPage("en/index.html")]);

  assert.match(spanish, /Sistemas claros\. Equipos seguros\./);
  assert.match(english, /Clear systems\. Confident teams\./);
  assert.match(spanish, /favicon\.svg/);
  assert.match(spanish, /data-relay-local-url="http:\/\/127\.0\.0\.1:8787"/);
  assert.match(spanish, /Sistemas reales, explicados desde su uso\./);
  assert.match(spanish, /Reticulum/);
  assert.match(spanish, /El recorrido guiado permite entender cómo se prepara, cifra y confirma una prueba antes de enviarla\./);
  assert.match(spanish, /Explorar recorrido Reticulum/);
  assert.match(spanish, /<h3 id="signal-relay-title"><a href="https:\/\/reticulum\.network"/);
  assert.match(spanish, /Origen temporal/);
  assert.match(spanish, /Aviso Telegram/);
  assert.match(spanish, /Se muestran los cinco mensajes más recientes como texto plano\./);
  assert.match(spanish, /Conexiones TCP Reticulum/);
  assert.match(spanish, /data-node-up-label="Online"/);
  assert.match(spanish, /data-node-down-label="Offline"/);
  assert.match(spanish, /La dirección LXMF no pertenece a un nodo concreto/);
  assert.match(spanish, /Pendiente de selección de ruta/);
  assert.match(spanish, /Observabilidad de servicios/);
  assert.match(spanish, /Puedes comparar ambos recursos, seleccionar servicios y revisar un intervalo concreto\./);
  assert.match(spanish, /data-metrics-panel/);
  assert.match(spanish, /Servicios/);
  assert.match(spanish, /data-metrics-start/);
  assert.match(spanish, /data-metrics-end/);
  assert.match(spanish, /metrics-time/);
  assert.match(spanish, /Monitorización y automatización del hogar/);
  assert.match(spanish, /Sirve para consultar el estado actual de mi hogar manteniendo la privacidad\./);
  assert.match(spanish, /data-home-status-panel/);
  assert.match(spanish, /Datos protegidos/);
  assert.match(spanish, /Calidad ambiental/);
  assert.match(spanish, /data-home-air-quality/);
  assert.match(spanish, /data-good-label="Buena"/);
  assert.match(spanish, /data-regular-label="Regular"/);
  assert.match(spanish, /data-bad-label="Mala"/);
  assert.match(spanish, /Estado agregado de una pasarela Meshtastic/);
  assert.match(spanish, /data-meshtastic-panel/);
  assert.doesNotMatch(spanish, /Últimas 5 actividades públicas/);
  assert.match(spanish, /Enviar a MediumFast/);
  assert.match(spanish, /Enviando mensaje a la radio/);
  assert.match(spanish, /La pasarela ha aceptado el mensaje para su difusión/);
  assert.match(spanish, /El envío público estará disponible tras configurar la verificación antiabuso/);
  assert.match(spanish, /<textarea[^>]*disabled/);
  assert.match(spanish, /Estado de la malla Meshtastic/);
  assert.match(spanish, /data-meshtastic-status-panel/);
  assert.match(spanish, /data-loading-label="Consultando malla"/);
  assert.match(spanish, /data-unavailable-label="La malla no está disponible ahora\."/);
  assert.doesNotMatch(spanish, /Último nodo visto/);
  assert.match(spanish, /Solo se publican contadores agregados y el último mensaje de cada canal público/);
  assertLabOrder(spanish);
  assert.doesNotMatch(spanish, /data-inbox-source-label/);
  assert.match(spanish, /Reticulum online/);
  assert.match(spanish, /abr 2021 - hoy/);
  assert.match(spanish, /Senior DevOps Engineer/);
  assert.match(spanish, /NTT/);
  assert.match(spanish, /Orbe/);
  assert.match(spanish, /mar 2012 - jun 2017/);
  assert.match(english, /Reticulum address/);
  assert.match(english, /Systems explained through use\./);
  assert.match(english, /Explore the Reticulum journey/);
  assert.match(english, /The five most recent messages are shown as plain text\./);
  assert.match(english, /The guided journey shows how a test is prepared, encrypted, and confirmed before it is sent\./);
  assert.doesNotMatch(english, /data-inbox-source-label/);
  assert.match(english, /Reticulum TCP connections/);
  assert.match(english, /data-node-up-label="Online"/);
  assert.match(english, /data-node-down-label="Offline"/);
  assert.match(english, /The LXMF address does not belong to one specific node/);
  assert.match(english, /Waiting for route selection/);
  assert.match(english, /Apr 2021 - present/);
  assert.match(english, /Systems Integrator/);
  assert.match(english, /NTT/);
  assert.match(english, /Orbe/);
  assert.match(english, /Mar 2012 - Jun 2017/);
  assert.doesNotMatch(spanish, /Simulador de coste y fiabilidad/);
  assert.match(english, /Service observability/);
  assert.match(english, /Compare both resources, select services, and inspect a specific time range\./);
  assert.match(english, /Home monitoring and automation/);
  assert.match(english, /Check the current state of my home while preserving privacy\./);
  assert.match(english, /Protected data/);
  assert.match(english, /Meshtastic mesh status/);
  assert.match(english, /data-meshtastic-status-panel/);
  assert.match(english, /data-loading-label="Checking mesh"/);
  assert.match(english, /data-unavailable-label="The mesh is unavailable right now\."/);
  assert.doesNotMatch(english, /Latest node seen/);
  assert.match(english, /Only aggregate counts and the latest message of each public channel are published/);
  assert.match(english, /Air quality/);
  assert.match(english, /Aggregate status for a Meshtastic gateway/);
  assert.doesNotMatch(english, /Last 5 public activities/);
  assert.match(english, /Send to MediumFast/);
  assert.match(english, /Sending message to the radio/);
  assert.match(english, /The gateway accepted the message for broadcast/);
  assert.match(english, /Public sending will be available after anti-abuse verification is configured/);
  assertLabOrder(english);
  assert.doesNotMatch(spanish, /profile\.jpg/);
  assert.doesNotMatch(english, /Portrait of/);
  assert.match(spanish, /<dt>Red profesional<\/dt><dd><a /);
  assert.doesNotMatch(spanish, /<footer class="shell site-footer">[\s\S]*?<a /);
  assert.doesNotMatch(english, /<footer class="shell site-footer">[\s\S]*?<a /);
});

const meshtasticStatusSection = (page) => {
  const start = page.indexOf("data-meshtastic-status-panel");
  assert.notEqual(start, -1);
  return page.slice(start, page.indexOf("</article>", start));
};

test("publishes the Meshtastic status panel with channel labels and a contact note without an address", async () => {
  const [spanish, english] = await Promise.all([readPage("index.html"), readPage("en/index.html")]);

  const spanishPanel = meshtasticStatusSection(spanish);
  assert.match(spanishPanel, /data-meshtastic-status-channels/);
  assert.match(spanishPanel, />Canales públicos</);
  assert.match(spanishPanel, /data-channel-label="Canal"/);
  assert.match(spanishPanel, /data-last-message-label="Último mensaje"/);
  assert.match(spanishPanel, /data-node-label="Nodo"/);
  assert.match(spanishPanel, /data-time-label="Hora"/);
  assert.match(spanishPanel, /data-hops-label="Saltos"/);
  assert.match(spanishPanel, /data-no-messages-label="No hay mensajes nuevos"/);
  assert.match(spanishPanel, /Los mensajes proceden de canales públicos de Meshtastic\./);
  assert.match(spanishPanel, /contacta a través de los enlaces de esta página/);
  assert.doesNotMatch(spanishPanel, /@|mailto:/);

  const englishPanel = meshtasticStatusSection(english);
  assert.match(englishPanel, /data-meshtastic-status-channels/);
  assert.match(englishPanel, />Public channels</);
  assert.match(englishPanel, /data-channel-label="Channel"/);
  assert.match(englishPanel, /data-last-message-label="Last message"/);
  assert.match(englishPanel, /data-node-label="Node"/);
  assert.match(englishPanel, /data-time-label="Time"/);
  assert.match(englishPanel, /data-hops-label="Hops"/);
  assert.match(englishPanel, /data-no-messages-label="No new messages"/);
  assert.match(englishPanel, /Messages come from public Meshtastic channels\./);
  assert.match(englishPanel, /contact via the links on this page/);
  assert.doesNotMatch(englishPanel, /@|mailto:/);
});

test("renders Meshtastic channel data with DOM text APIs only", async () => {
  const page = await readPage("es/index.html");
  // Astro inlines each component script as its own module block, so the panel script is found by its endpoint.
  const scripts = [...page.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  const meshtasticScript = scripts.find((script) => script.includes("/v1/lab/meshtastic-status"));

  assert.ok(meshtasticScript, "the Meshtastic panel script is present in the page");
  assert.doesNotMatch(meshtasticScript, /innerHTML|outerHTML|insertAdjacentHTML|document\.write/);
  assert.match(meshtasticScript, /createElement/);
  assert.match(meshtasticScript, /textContent/);
});

test("declares locale alternates, og:locale, and RSS discovery in every page head", async () => {
  const [spanish, english, spanishArticle, englishArticle] = await Promise.all([
    readPage("es/index.html"),
    readPage("en/index.html"),
    readPage("es/bitacora/signal-relay/index.html"),
    readPage("en/notes/signal-relay/index.html"),
  ]);

  assert.match(spanish, /<link rel="canonical" href="https:\/\/info\.destaben\.dev\/es\/">/);
  assert.match(spanish, /<link rel="alternate" hreflang="es" href="https:\/\/info\.destaben\.dev\/es\/">/);
  assert.match(spanish, /<link rel="alternate" hreflang="en" href="https:\/\/info\.destaben\.dev\/en\/">/);
  assert.match(spanish, /<meta property="og:locale" content="es_ES">/);
  assert.match(english, /<link rel="canonical" href="https:\/\/info\.destaben\.dev\/en\/">/);
  assert.match(english, /<link rel="alternate" hreflang="es" href="https:\/\/info\.destaben\.dev\/es\/">/);
  assert.match(english, /<link rel="alternate" hreflang="en" href="https:\/\/info\.destaben\.dev\/en\/">/);
  assert.match(spanish, /<link rel="alternate" hreflang="x-default" href="https:\/\/info\.destaben\.dev\/es\/">/);
  assert.match(english, /<link rel="alternate" hreflang="x-default" href="https:\/\/info\.destaben\.dev\/es\/">/);
  assert.match(english, /<meta property="og:locale" content="en_US">/);

  for (const page of [spanish, english, spanishArticle, englishArticle]) {
    assert.match(page, /<link rel="alternate" type="application\/rss\+xml" title="[^"]+" href="https:\/\/info\.destaben\.dev\/rss\.xml">/);
  }

  // Articles do not claim an alternate: their counterpart slugs are not guaranteed to exist.
  assert.doesNotMatch(spanishArticle, /hreflang=/);
  assert.doesNotMatch(englishArticle, /hreflang=/);
  assert.match(spanishArticle, /<link rel="canonical" href="https:\/\/info\.destaben\.dev\/es\/bitacora\/signal-relay\/">/);
  assert.match(englishArticle, /<link rel="canonical" href="https:\/\/info\.destaben\.dev\/en\/notes\/signal-relay\/">/);
});

test("localizes the brand link label to the page language", async () => {
  const [spanish, english, spanishArticle, englishArticle] = await Promise.all([
    readPage("es/index.html"),
    readPage("en/index.html"),
    readPage("es/bitacora/signal-relay/index.html"),
    readPage("en/notes/signal-relay/index.html"),
  ]);

  assert.match(spanish, /class="brand" href="\/es\/" aria-label="Inicio de David Estaben"/);
  assert.match(spanishArticle, /class="brand" href="\/es\/" aria-label="Inicio de David Estaben"/);
  assert.doesNotMatch(spanish, /David Estaben home/);
  assert.doesNotMatch(spanishArticle, /David Estaben home/);
  assert.match(english, /class="brand" href="\/en\/" aria-label="David Estaben home"/);
  assert.match(englishArticle, /class="brand" href="\/en\/" aria-label="David Estaben home"/);
});

test("integrates projects and published technical notes into portfolio pages", async () => {
  const [spanishPortfolio, englishPortfolio, englishArticle] = await Promise.all([
    readPage("es/index.html"),
    readPage("en/index.html"),
    readPage("en/notes/signal-relay/index.html"),
  ]);

  assert.match(spanishPortfolio, /id="proyectos"/);
  assert.match(spanishPortfolio, /data-filter="original"/);
  assert.match(spanishPortfolio, /id="bitacora"/);
  assert.match(spanishPortfolio, /Reticulum: un punto de contacto directo/);
  assert.match(spanishPortfolio, /Alertas que ayudan a decidir/);
  assert.match(englishPortfolio, /id="projects"/);
  assert.match(englishPortfolio, /id="notes"/);
  assert.match(englishPortfolio, /Alerts that help teams decide/);
  assert.match(englishArticle, /A browser is not a Reticulum client/);
  assert.match(englishArticle, /class="article-header"/);
  assert.match(englishArticle, /class="article-body"/);
  assert.doesNotMatch(englishArticle, /<footer class="shell site-footer">[\s\S]*?<a /);
});

test("publishes a crawlable sitemap and RSS feed", async () => {
  const [sitemap, feed, notFound] = await Promise.all([readPage("sitemap-index.xml"), readPage("rss.xml"), readPage("404.html")]);

  assert.match(sitemap, /sitemap-/);
  assert.match(feed, /Reticulum/);
  assert.match(feed, /https:\/\/info\.destaben\.dev\/en\/notes\/signal-relay\//);
  assert.match(feed, /https:\/\/info\.destaben\.dev\/es\/bitacora\/signal-relay\//);
  assert.doesNotMatch(feed, /\/posts\//);
  assert.match(notFound, /This route has no signal/);
});

const heroGraphic = (page) => {
  const start = page.indexOf('<div class="system-graphic" aria-hidden="true"');
  assert.notEqual(start, -1, "the hero graphic is rendered with aria-hidden on its root");
  return page.slice(start, page.indexOf("</section>", start));
};

test("renders the decorative hero graphic hidden from assistive technology, with its labels as text", async () => {
  const [spanish, english] = await Promise.all([readPage("es/index.html"), readPage("en/index.html")]);

  for (const page of [spanish, english]) {
    const graphic = heroGraphic(page);
    assert.match(graphic, /<svg class="system-svg" viewBox="0 0 420 420"/);
    assert.ok(graphic.includes(">OBSERVE</span>"));
    assert.ok(graphic.includes(">RESPOND</span>"));
    for (const step of ["ALERT", "TRIAGE", "RESOLVED"]) assert.ok(graphic.includes(`>${step}</span>`));
    assert.match(graphic, /class="sg-event/);
    // The core is a plain decorative disc: no island and no text.
    assert.match(graphic, /<div class="system-core"[^>]*><\/div>/);
  }
});

test("disables every hero animation under reduced motion", async () => {
  const source = await readFile(new URL("../src/components/SystemGraphic.astro", import.meta.url), "utf8");
  const block = source.match(/@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\n\s*\}\n/)?.[0] ?? "";
  for (const selector of [".sg-orbit", ".sg-upright", ".sg-event", ".log-alert", ".log-triage", ".log-resolved"]) {
    assert.match(
      block,
      new RegExp(`(^|[\\s,])${selector.replace(".", "\\.")}\\s*[,{][^}]*?animation:\\s*none`),
      `${selector} sets animation: none under reduced motion`,
    );
  }
});

test("keeps the numbered section labels as final plain text and scrambles them only as decorative islands", async () => {
  const [spanish, english] = await Promise.all([readPage("es/index.html"), readPage("en/index.html")]);
  const expected = {
    spanish: ["01 / Áreas de trabajo", "02 / Laboratorio", "03 / GitHub", "04 / Bitácora", "05 / Trayectoria", "06 / Contacto"],
    english: ["01 / Areas of work", "02 / Lab", "03 / GitHub", "04 / Notes", "05 / Experience", "06 / Contact"],
  };

  for (const [page, labels] of [[spanish, expected.spanish], [english, expected.english]]) {
    for (const label of labels) {
      // The final text is the screen-reader copy; the scrambled visual is aria-hidden and sits next to it.
      assert.ok(page.includes(`>${label}</span>`), `${label} is plain text in the HTML`);
    }
    const islands = page.match(/component-url="\/_astro\/SectionLabel\.[^"]+"[^>]*client="visible"/g) ?? [];
    assert.equal(islands.length, labels.length, "each numbered label is a visible-triggered island");
  }
});

test("adds no third-party script and keeps every script on this origin", async () => {
  const [spanish, english] = await Promise.all([readPage("es/index.html"), readPage("en/index.html")]);

  for (const page of [spanish, english]) {
    const sources = [...page.matchAll(/<script[^>]*\ssrc="([^"]+)"/g)].map((match) => match[1]);
    assert.ok(sources.length > 0, "the page loads its bundled scripts");
    for (const source of sources) assert.match(source, /^\/_astro\//, `${source} is served from this site`);
    assert.doesNotMatch(page, /<script[^>]*\ssrc="https?:/);
    assert.doesNotMatch(page, /import\(\s*["']https?:/);
  }
});
test("keeps animated headings readable without JavaScript and under reduced motion", async () => {
  const [spanish, english, css] = await Promise.all([
    readPage("es/index.html"),
    readPage("en/index.html"),
    readFile(new URL("../src/styles/global.css", import.meta.url), "utf8"),
  ]);

  for (const page of [spanish, english]) {
    // The animated pieces start hidden in the server HTML, so a noscript rule must show them.
    assert.match(page, /<noscript><style>[^<]*\[data-blur-piece\][^<]*opacity:\s*1\s*!important/);
    // Screen readers get the heading once, as plain text, ahead of the aria-hidden animated pieces.
    assert.match(page, /<h1 id="hero-title">[\s\S]*?<span[^>]*>[^<]+<\/span>[\s\S]*?data-blur-piece/);
    // Case numbers are plain identifiers, not animated counters.
    assert.match(page, /<p class="case-number">0[123]<\/p>/);
    // The relay copy button keeps its script hooks inside the spark wrapper.
    assert.match(page, /data-copy-address[^>]*disabled/);
  }
  const reduced = css.match(/@media \(prefers-reduced-motion: reduce\) \{ \[data-blur-piece\][^}]*\}/)?.[0] ?? "";
  assert.match(reduced, /opacity:\s*1\s*!important/);
  assert.match(reduced, /\[data-reveal\]/);
});
