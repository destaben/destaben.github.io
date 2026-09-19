import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const readPage = (path) => readFile(new URL(`../dist/${path}`, import.meta.url), "utf8");

test("generates bilingual portfolio entries without a portrait", async () => {
  const [spanish, english] = await Promise.all([readPage("index.html"), readPage("en.html")]);

  assert.match(spanish, /Sistemas claros\. Equipos seguros\./);
  assert.match(english, /Clear systems\. Confident teams\./);
  assert.match(spanish, /favicon\.svg/);
  assert.match(spanish, /data-relay-local-url="http:\/\/127\.0\.0\.1:8787"/);
  assert.match(spanish, /Reticulum explicado desde el recorrido de un mensaje\./);
  assert.match(spanish, /Signal Relay/);
  assert.match(spanish, /Explorar recorrido LXMF/);
  assert.match(spanish, /Origen temporal/);
  assert.match(spanish, /Aviso Telegram/);
  assert.match(spanish, /Signal Relay online/);
  assert.match(english, /LXMF address/);
  assert.match(english, /Explore the LXMF journey/);
  assert.doesNotMatch(spanish, /Simulador de coste y fiabilidad/);
  assert.doesNotMatch(spanish, /Prometheus \/metrics/);
  assert.doesNotMatch(spanish, /mini PC/i);
  assert.doesNotMatch(spanish, /profile\.jpg/);
  assert.doesNotMatch(english, /Portrait of/);
});

test("generates project archives and published technical notes", async () => {
  const [projects, spanishNotes, englishArticle] = await Promise.all([
    readPage("es/proyectos.html"),
    readPage("es/bitacora.html"),
    readPage("en/notes/signal-relay.html"),
  ]);

  assert.match(projects, /Archivo de proyectos/);
  assert.match(projects, /data-filter="original"/);
  assert.match(spanishNotes, /Signal Relay: un punto de contacto directo/);
  assert.match(englishArticle, /A browser is not a Reticulum client/);
});

test("publishes a crawlable sitemap and RSS feed", async () => {
  const [sitemap, feed, notFound] = await Promise.all([readPage("sitemap-index.xml"), readPage("rss.xml"), readPage("404.html")]);

  assert.match(sitemap, /sitemap-/);
  assert.match(feed, /Signal Relay/);
  assert.match(notFound, /This route has no signal/);
});