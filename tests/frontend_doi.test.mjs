import assert from "node:assert/strict";
import test from "node:test";

import { JSDOM } from "jsdom";


test("paper DOI workflow connects Zenodo, reserves safely, publishes, and updates citations", async () => {
  const dom = new JSDOM(
    '<!doctype html><html><body><div id="app"></div></body></html>',
    { url: "https://peerxiv.example/" },
  );
  for (const key of ["window", "document", "navigator", "location", "history", "Blob", "FormData", "URL"]) {
    Object.defineProperty(globalThis, key, {
      value: dom.window[key], configurable: true, writable: true,
    });
  }
  window.__PEERXIV_DISABLE_REALTIME__ = true;

  const user = {
    id: "11111111-1111-4111-8111-111111111111",
    email: "jay@example.com",
    display_name: "Jay Kumar",
    role: "Independent Researcher",
    bio: "Uncertain systems",
    orcid: null,
    zenodo: null,
  };
  let doi = null;
  let submittedToken = null;
  const encodedIdentifier = encodeURIComponent("px:2608.d0a1f");
  const paper = {
    id: "paper-1",
    owner: user,
    identifier: "px:2608.d0a1f",
    title: "Versioned DOI Integration Under Uncertainty",
    abstract: "A detailed abstract about DOI preservation and versioned uncertainty evidence.",
    subject: "Computer Science",
    subfield: "cs.DC",
    status: "published",
    license: "CC BY 4.0",
    open_review: true,
    authors: ["Jay Kumar"],
    tags: ["persistent identifiers"],
    current_version: 1,
    created_at: "2026-08-12T00:00:00Z",
    updated_at: "2026-08-12T00:00:00Z",
    versions: [{
      id: "version-1", number: 1, title: "Versioned DOI Integration Under Uncertainty",
      abstract: "A detailed abstract about DOI preservation and versioned uncertainty evidence.",
      authors: ["Jay Kumar"], tags: ["persistent identifiers"],
      manuscript_uri: "peerxiv://manuscripts/version-1.pdf",
      manuscript_checksum: "sha256:abc", change_summary: "Initial submission",
      published_at: "2026-08-12T00:00:00Z", descriptive_metadata: null, doi: null,
    }],
  };

  globalThis.fetch = async (input, options = {}) => {
    const url = String(input);
    let payload = { results: [] };
    if (url.endsWith("/bootstrap")) {
      payload = {
        registration_mode: "invite", orcid: { enabled: false },
        zenodo: { enabled: true, environment: "sandbox", production_publish_enabled: false },
      };
    } else if (url.endsWith("/accounts/me")) {
      payload = { authenticated: true, csrf_token: "csrf", user };
    } else if (url.endsWith("/papers")) {
      payload = { results: [paper] };
    } else if (url.endsWith("/accounts/zenodo") && options.method === "POST") {
      submittedToken = JSON.parse(options.body).token;
      user.zenodo = {
        status: "connected", environment: "sandbox", token_hint: "…3456",
        scopes: ["deposit:write", "deposit:actions"], verified_at: new Date().toISOString(),
      };
      payload = user.zenodo;
    } else if (url.endsWith(`/papers/${encodedIdentifier}/doi/prepare`)) {
      doi = {
        state: "metadata_ready", environment: "sandbox", provider: "zenodo",
        doi: null, doi_url: null, provider_record_id: null, provider_record_url: null,
        manuscript_checksum: "sha256:abc", last_error: null,
      };
      payload = doi;
    } else if (url.endsWith(`/papers/${encodedIdentifier}/doi/reserve`)) {
      assert.equal(JSON.parse(options.body).no_existing_doi, true);
      doi = {
        ...doi, state: "reserved", doi: "10.5072/zenodo.74201",
        doi_url: "https://doi.org/10.5072/zenodo.74201", provider_record_id: "74201",
        provider_record_url: "https://sandbox.zenodo.org/deposit/74201",
      };
      payload = doi;
    } else if (url.endsWith(`/papers/${encodedIdentifier}/doi/publish`)) {
      assert.equal(JSON.parse(options.body).confirmation, "10.5072/zenodo.74201");
      doi = {
        ...doi, state: "published",
        provider_record_url: "https://sandbox.zenodo.org/records/74201",
      };
      payload = doi;
    }
    return { ok: true, status: 200, json: async () => payload };
  };

  await import("../client/templates/src/main.js");
  await new Promise((resolve) => setTimeout(resolve, 40));

  document.querySelector(`[data-paper="${paper.identifier}"]`).click();
  await new Promise((resolve) => setTimeout(resolve, 10));
  document.querySelector(`[data-doi="${paper.identifier}"]`).click();
  assert.match(document.body.textContent, /Connect Zenodo sandbox/);

  const tokenInput = document.querySelector("[data-zenodo-form] [name=token]");
  tokenInput.value = "sandbox-secret-token-value-123456";
  document.querySelector("[data-zenodo-form]").dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.equal(submittedToken, "sandbox-secret-token-value-123456");
  assert.match(document.body.textContent, /Prepare DOI metadata/);

  document.querySelector('[data-action="prepare-doi"]').click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  const reserveForm = document.querySelector("[data-doi-reserve-form]");
  reserveForm.querySelector('[name="no_existing_doi"]').checked = true;
  reserveForm.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.match(document.body.textContent, /10.5072\/zenodo.74201/);
  assert.match(document.body.textContent, /test DOI/);
  assert.match(document.body.textContent, /will not resolve through DOI.org until/);
  assert.equal(
    document.querySelector('a[href="https://doi.org/10.5072/zenodo.74201"]'),
    null,
  );

  const publishForm = document.querySelector("[data-doi-publish-form]");
  publishForm.querySelector('[name="confirmation"]').value = "10.5072/zenodo.74201";
  publishForm.dispatchEvent(new dom.window.Event("submit", { bubbles: true, cancelable: true }));
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.match(document.body.textContent, /DOI registered/);

  document.querySelector('[data-action="close-doi"]').click();
  document.querySelector(`[data-cite="${paper.identifier}"]`).click();
  assert.match(document.querySelector(".citation-dialog textarea").value, /doi.org\/10.5072\/zenodo.74201/);

  dom.window.close();
});
