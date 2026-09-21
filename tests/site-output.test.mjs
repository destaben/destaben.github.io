import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readPage = (path) => readFile(new URL(`../dist/${path}`, import.meta.url), "utf8");

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
  assert.match(english, /Air quality/);
  assert.doesNotMatch(spanish, /profile\.jpg/);
  assert.doesNotMatch(english, /Portrait of/);
  assert.match(spanish, /<dt>Red profesional<\/dt><dd><a /);
  assert.doesNotMatch(spanish, /<footer class="shell site-footer">[\s\S]*?<a /);
  assert.doesNotMatch(english, /<footer class="shell site-footer">[\s\S]*?<a /);
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