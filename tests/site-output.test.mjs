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
  assert.match(spanish, /Reticulum explicado desde el recorrido de un mensaje\./);
  assert.match(spanish, /Reticulum/);
  assert.match(spanish, /Explorar recorrido Reticulum/);
  assert.match(spanish, /<h3 id="signal-relay-title"><a href="https:\/\/reticulum\.network"/);
  assert.match(spanish, /Origen temporal/);
  assert.match(spanish, /Aviso Telegram/);
  assert.match(spanish, /data-inbox-source-label="ID de origen"/);
  assert.match(spanish, /Reticulum online/);
  assert.match(english, /Reticulum address/);
  assert.match(english, /Explore the Reticulum journey/);
  assert.match(english, /data-inbox-source-label="Source ID"/);
  assert.doesNotMatch(spanish, /Simulador de coste y fiabilidad/);
  assert.doesNotMatch(spanish, /Prometheus \/metrics/);
  assert.doesNotMatch(spanish, /mini PC/i);
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