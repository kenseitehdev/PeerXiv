import assert from "node:assert/strict";
import test from "node:test";

import { JSDOM } from "jsdom";


test("fresh alpha ignores legacy browser fixtures and renders empty API state", async () => {
  const dom = new JSDOM(
    '<!doctype html><html><body><div id="app"></div></body></html>',
    { url: "http://127.0.0.1:8000/" },
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

  window.localStorage.setItem("peerxiv.prototype.v1", JSON.stringify({
    papers: [{ id: "legacy-paper", title: "Legacy Fixture Paper" }],
    conversations: [{ name: "Legacy Fixture User" }],
    notifications: [{ text: "Legacy Fixture Notification" }],
  }));

  globalThis.fetch = async (input) => {
    const url = String(input);
    const payload = url.endsWith("/accounts/me")
      ? { authenticated: false, user: null, csrf_token: null }
      : { results: [], service: "PeerXiv" };
    return { ok: true, status: 200, json: async () => payload };
  };

  await import("../client/templates/src/main.js");
  await new Promise((resolve) => setTimeout(resolve, 30));

  assert.equal(document.querySelectorAll(".paper-card").length, 0);
  assert.match(document.body.textContent, /No matching papers/);
  assert.doesNotMatch(document.body.textContent, /Legacy Fixture/);
  assert.equal(window.localStorage.getItem("peerxiv.prototype.v1"), null);

  dom.window.close();
});
