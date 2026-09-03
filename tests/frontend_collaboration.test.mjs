import assert from "node:assert/strict";
import test from "node:test";

import { JSDOM } from "jsdom";


test("verified ORCID and collaborator autosuggest are wired to persisted accounts", async () => {
  const dom = new JSDOM(
    '<!doctype html><html><body><div id="app"></div></body></html>',
    { url: "http://127.0.0.1:8000/" },
  );
  for (const key of ["window", "document", "navigator", "location", "history", "Blob", "FormData", "URL"]) {
    Object.defineProperty(globalThis, key, {
      value: dom.window[key], configurable: true, writable: true,
    });
  }
  window.__PEERXIV_DISABLE_REALTIME__ = true;
  window.confirm = () => true;

  const jay = {
    id: "11111111-1111-4111-8111-111111111111",
    email: "jay@example.com",
    display_name: "Jay Kumar",
    role: "Independent Researcher",
    bio: "Uncertain systems",
    orcid: {
      id: "0000-0002-1825-0097",
      name: "Jay Kumar",
      url: "https://orcid.org/0000-0002-1825-0097",
      verified_at: new Date().toISOString(),
    },
  };
  const maya = {
    id: "22222222-2222-4222-8222-222222222222",
    display_name: "Maya Chen",
    role: "Machine Learning Researcher",
    bio: "",
    orcid: null,
  };
  const workspace = {
    id: "33333333-3333-4333-8333-333333333333",
    kind: "workspace",
    title: "CoU implementation",
    status: "active",
    visibility: "private",
    details: {},
    owner: jay,
    members: [{ id: "member-owner", user: jay, role: "owner", permissions: ["view", "manage_members"] }],
    papers: [], resources: [],
    viewer_access: { role: "owner", permissions: ["view", "edit_space", "manage_members", "manage_resources"] },
    created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
  };

  globalThis.fetch = async (input, options = {}) => {
    const url = String(input);
    let payload = { results: [] };
    if (url.endsWith("/bootstrap")) payload = { registration_mode: "invite", orcid: { enabled: true } };
    else if (url.endsWith("/accounts/me")) payload = { authenticated: true, csrf_token: "csrf", user: jay };
    else if (url.includes("/accounts/people/search?")) payload = { results: [maya] };
    else if (url.endsWith(`/spaces/${workspace.id}/members`) && options.method === "POST") {
      const request = JSON.parse(options.body);
      workspace.members.push({
        id: "member-maya", user: maya, role: request.role,
        permissions: ["view", "manage_resources", "write_files", "review"],
      });
      payload = workspace.members.at(-1);
    } else if (url.endsWith(`/spaces/${workspace.id}`)) payload = workspace;
    else if (url.endsWith("/spaces")) payload = { results: [workspace] };
    return { ok: true, status: 200, json: async () => payload };
  };

  await import("../client/templates/src/main.js");
  await new Promise((resolve) => setTimeout(resolve, 30));

  document.querySelector('[data-page="workspaces"]').click();
  document.querySelector('[data-workspace="0"]').click();
  document.querySelector('[data-workspace-tab="collaborators"]').click();
  assert.match(document.body.textContent, /Jay Kumar/);
  document.querySelector('[data-action="add-collaborator"]').click();
  const search = document.querySelector("[data-collaborator-search]");
  search.value = "Maya";
  search.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 250));
  document.querySelector(`[data-select-collaborator="${maya.id}"]`).click();
  document.querySelector("[data-collaborator-form]").dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.match(document.body.textContent, /Maya Chen/);
  assert.match(document.body.textContent, /contributor/i);
  document.querySelector(".user-menu").click();
  assert.match(document.body.textContent, /0000-0002-1825-0097/);

  dom.window.close();
});
