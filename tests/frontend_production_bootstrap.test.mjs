import assert from "node:assert/strict";
import test from "node:test";

import { JSDOM } from "jsdom";


test("frontend renders only persisted API paper records", async () => {
  const dom = new JSDOM(
    '<!doctype html><html><body><div id="app"></div></body></html>',
    { url: "https://peerxiv.example/" },
  );
  for (const key of [
    "window",
    "document",
    "navigator",
    "location",
    "history",
    "Blob",
    "FormData",
    "URL",
  ]) {
    Object.defineProperty(globalThis, key, {
      value: dom.window[key],
      configurable: true,
      writable: true,
    });
  }
  window.__PEERXIV_DISABLE_REALTIME__ = true;

  const persistedPaper = {
    id: "paper-db-id",
    identifier: "px:2608.persisted",
    title: "A Persisted Production Research Record",
    abstract: "This persisted abstract is long enough to represent a production paper.",
    subject: "Machine Learning",
    subfield: "cs.LG",
    status: "published",
    license: "CC BY 4.0",
    open_review: true,
    authors: ["Persistent Researcher"],
    tags: ["production"],
    current_version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    versions: [
      {
        number: 1,
        manuscript_uri: "peerxiv://manuscripts/00000000-0000-0000-0000-000000000000.pdf",
        descriptive_metadata: null,
      },
    ],
  };

  globalThis.fetch = async (input) => {
    const url = String(input);
    let payload = { results: [] };
    if (url.endsWith("/bootstrap")) payload = { service: "PeerXiv" };
    else if (url.endsWith("/accounts/me")) {
      payload = { authenticated: false, user: null, csrf_token: null };
    } else if (url.endsWith("/papers")) payload = { results: [persistedPaper] };
    return { ok: true, status: 200, json: async () => payload };
  };

  await import("../client/templates/src/main.js");
  await new Promise((resolve) => setTimeout(resolve, 30));

  const cards = [...document.querySelectorAll(".paper-card")];
  assert.equal(cards.length, 1);
  assert.equal(cards[0].dataset.paper, "px:2608.persisted");
  assert.match(cards[0].textContent, /Persisted Production Research Record/);
  assert.doesNotMatch(document.body.textContent, /Context-Aware Reconstruction/);
  assert.match(document.body.textContent, /Archive status/);
  assert.doesNotMatch(document.body.textContent, /Current prototype/);

  dom.window.close();
});
