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
  assert.match(spanish, /Observabilidad de servicios/);
  assert.match(spanish, /Puedes comparar ambos recursos, seleccionar servicios y revisar un intervalo concreto\./);
  assert.match(spanish, /data-metrics-panel/);
  assert.match(spanish, /Servicios/);
  assert.match(spanish, /data-metrics-start/);
  assert.match(spanish, /data-metrics-end/);
  assert.match(spanish, /metrics-time/);
  assert.match(spanish, /Monitorización y automatización del hogar/);
  assert.match(spanish, /Sirve para consultar el estado actual sin publicar presencia, cámaras, dispositivos ni habitaciones\./);
  assert.match(spanish, /data-home-status-panel/);
  assert.match(spanish, /Datos protegidos/);
  assert.match(spanish, /Calidad ambiental/);
  assert.match(spanish, /data-home-air-quality/);
  assert.match(spanish, /data-good-label="Buena"/);
  assert.match(spanish, /data-regular-label="Regular"/);
  assert.match(spanish, /data-bad-label="Mala"/);
  assert.match(spanish, /data-inbox-source-label="ID de origen"/);
  assert.match(spanish, /Reticulum online/);
  assert.match(spanish, /abr 2021 - hoy/);
  assert.match(spanish, /Senior DevOps Engineer/);
  assert.match(spanish, /Orbe Telecomunicaciones, S\.L\./);
  assert.match(spanish, /mar 2012 - jun 2017/);
  assert.match(english, /Reticulum address/);
  assert.match(english, /Systems explained through use\./);
  assert.match(english, /Explore the Reticulum journey/);
  assert.match(english, /The guided journey shows how a test is prepared, encrypted, and confirmed before it is sent\./);
  assert.match(english, /data-inbox-source-label="Source ID"/);
  assert.match(english, /Apr 2021 - present/);
  assert.match(english, /Systems Integrator/);
  assert.match(english, /Mar 2012 - Jun 2017/);
  assert.doesNotMatch(spanish, /Simulador de coste y fiabilidad/);
  assert.match(english, /Service observability/);
  assert.match(english, /Compare both resources, select services, and inspect a specific time range\./);
  assert.match(english, /Home monitoring and automation/);
  assert.match(english, /Check the current state without publishing presence, cameras, devices, or rooms\./);
  assert.match(english, /Protected data/);
  assert.match(english, /Air quality/);
  assert.doesNotMatch(spanish, /profile\.jpg/);
  assert.doesNotMatch(english, /Portrait of/);
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
});

test("publishes a crawlable sitemap and RSS feed", async () => {
  const [sitemap, feed, notFound] = await Promise.all([readPage("sitemap-index.xml"), readPage("rss.xml"), readPage("404.html")]);

  assert.match(sitemap, /sitemap-/);
  assert.match(feed, /Reticulum/);
  assert.match(notFound, /This route has no signal/);
});