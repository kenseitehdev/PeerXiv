import assert from "node:assert/strict";
import test from "node:test";

import { JSDOM } from "jsdom";


test("citation, sharing, discussions, and Research Spaces are interactive", async () => {
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
  const liveDiscussion = {
    id: "4a5d23ab-2f68-4bab-9294-21be708af233",
    title: "How should validation histories be retained?",
    topic: "Open Science",
    author: { id: "maya", display_name: "Maya Chen", role: "Researcher" },
    body: "A durable thread should keep the evidence state attached to each revision.",
    comment_count: 0,
    comments: [],
    score: 3,
    following: true,
    saved: false,
    viewer_vote: 0,
    paper: "px:alpha.test",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  const hostileWorkspace = {
    id: "workspace-hostile",
    kind: "workspace",
    title: '<img data-xss="workspace" src=x> Evidence workspace',
    status: "active",
    details: {
      repository: '<svg data-xss="repository"></svg>',
      overleaf: "Methods <script>window.__xss = true</script>",
    },
    members: [],
    papers: [],
    resources: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  const livePaper = {
    id: "paper-alpha-test",
    identifier: "px:alpha.test",
    title: "An API-Backed Alpha Research Record",
    abstract: "This backend-provided abstract is long enough for the frontend interaction test.",
    subject: "Machine Learning",
    subfield: "cs.LG",
    status: "published",
    license: "CC BY 4.0",
    open_review: true,
    authors: ["Alpha Researcher"],
    tags: ["validation"],
    current_version: 1,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    versions: [{ number: 1, manuscript_uri: "peerxiv://manuscripts/alpha.pdf", descriptive_metadata: null }],
  };
  const liveSpaces = [
    hostileWorkspace,
    {
      id: "presentation-alpha",
      kind: "presentation",
      title: "Alpha Research Briefing",
      status: "active",
      details: { speaker: "Alpha Researcher", format: "Briefing", event: "Alpha Review", slides: 12, paper: livePaper.identifier },
      members: [], papers: [], resources: [],
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    },
    {
      id: "conference-alpha",
      kind: "conference",
      title: "Alpha Research Conference",
      description: "Machine learning and validation",
      status: "active",
      details: { location: "Online", dates: "Sep 8 2026", deadline: "Aug 20", topics: "Machine learning · Validation" },
      members: [], papers: [], resources: [],
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    },
    {
      id: "journal-alpha",
      kind: "journal",
      title: "Alpha Journal Relationship",
      status: "published",
      details: { paper_title: livePaper.title, journal: "Alpha Journal", doi: "10.0000/alpha" },
      members: [], papers: [], resources: [],
      created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    },
  ];
  const persistedMessages = [];
  let persistedConversation = null;
  globalThis.fetch = async (input, options = {}) => {
    const url = String(input);
    let payload = { results: [], notifications: [] };
    if (url.endsWith("/accounts/me")) {
      payload = {
        authenticated: true,
        csrf_token: "frontend-test-csrf",
        user: {
          id: "jay",
          email: "jay@example.com",
          display_name: "Jay Kumar",
          role: "Independent Researcher",
          bio: "Uncertain systems",
        },
      };
    } else if (url.includes("/social/discussions?")) {
      payload = { results: [liveDiscussion] };
    } else if (url.endsWith("/papers")) {
      payload = { results: [livePaper] };
    } else if (url.endsWith("/spaces")) {
      payload = { results: liveSpaces };
    } else if (url.endsWith(`/social/discussions/${liveDiscussion.id}`)) {
      payload = liveDiscussion;
    } else if (url.endsWith(`/social/discussions/${liveDiscussion.id}/comments`)) {
      const body = JSON.parse(options.body);
      const comment = {
        id: "comment-1",
        author: { id: "jay", display_name: "Jay Kumar" },
        body: body.body,
        created_at: new Date().toISOString(),
      };
      liveDiscussion.comments.push(comment);
      liveDiscussion.comment_count = liveDiscussion.comments.length;
      payload = comment;
    } else if (url.endsWith("/social/conversations") && options.method === "POST") {
      const body = JSON.parse(options.body);
      const firstMessage = {
        id: "message-1", conversation_id: "conversation-1", author_id: "jay",
        body: body.body, created_at: new Date().toISOString(),
      };
      persistedMessages.push(firstMessage);
      persistedConversation = {
        id: "conversation-1", title: "Research conversation",
        participants: [
          { id: "jay", display_name: "Jay Kumar" },
          { id: "collaborator", display_name: "Research Collaborator" },
        ],
        last_message: firstMessage, unread_count: 0,
        created_at: new Date().toISOString(), messages: [...persistedMessages],
      };
      payload = persistedConversation;
    } else if (url.endsWith("/social/conversations")) {
      payload = { results: persistedConversation ? [persistedConversation] : [] };
    } else if (url.endsWith("/social/conversations/conversation-1/messages") && options.method === "POST") {
      const body = JSON.parse(options.body);
      const message = {
        id: `message-${persistedMessages.length + 1}`,
        conversation_id: "conversation-1", author_id: "jay",
        body: body.body, created_at: new Date().toISOString(),
      };
      persistedMessages.push(message);
      payload = message;
    }
    return { ok: true, status: 200, json: async () => payload };
  };
  document.execCommand = () => true;

  await import("../client/templates/src/main.js");
  await new Promise((resolve) => setTimeout(resolve, 20));

  document.querySelector('[data-page="messages"]').click();
  assert.match(document.body.textContent, /No conversations yet/);
  document.querySelector('[data-action="new-message"]').click();
  document.querySelector('[data-workflow-form="message"] [name="recipient"]').value = "collaborator@example.org";
  document.querySelector('[data-workflow-form="message"] [name="message"]').value = "Starting an alpha research conversation.";
  document.querySelector('[data-workflow-form="message"]').dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  document.querySelector('[data-page="home"]').click();

  document.querySelector('[data-cite="px:alpha.test"]').click();
  assert.ok(document.querySelector(".citation-dialog"));
  document.querySelector('[data-citation-style="bibtex"]').click();
  assert.match(document.querySelector(".citation-dialog textarea").value, /^@article{/);
  document.querySelector('[data-action="close-citation"]').click();

  document.querySelector('[data-share="px:alpha.test"]').click();
  assert.match(
    document.querySelector(".share-dialog input").value,
    /#paper=px%3Aalpha\.test$/,
  );
  document.querySelector("[data-share-form]").dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(document.querySelector(".messages-page"));
  assert.match(persistedMessages.at(-1).body, /Shared preprint/);

  document.querySelector('[data-page="home"]').click();
  document.querySelector('[data-action="toggle-discussions"]').click();
  document.querySelector(`[data-discussion="${liveDiscussion.id}"]`).click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(document.querySelector(".discussion-thread"));
  document.querySelector("[data-discussion-reply] textarea").value =
    "This is a substantive validation reply for the interaction test.";
  document.querySelector("[data-discussion-reply]").dispatchEvent(
    new dom.window.Event("submit", { bubbles: true, cancelable: true }),
  );
  await new Promise((resolve) => setTimeout(resolve, 20));
  assert.ok(
    [...document.querySelectorAll(".thread-replies article p")].some((node) =>
      node.textContent.includes("substantive validation reply"),
    ),
  );
  document.querySelector('[data-action="back-discussions"]').click();

  document.querySelector('[data-action="toggle-spaces"]').click();
  assert.ok(document.querySelector(".space-hub"));
  document.querySelector('[data-page="presentations"]').click();
  document.querySelector('[data-presentation-open="0"]').click();
  assert.ok(document.querySelector(".presentation-outline"));
  document.querySelector('[data-action="back-presentations"]').click();
  document.querySelector('[data-page="conferences"]').click();
  document.querySelector('[data-conference-open="0"]').click();
  assert.ok(document.querySelector(".conference-detail-grid"));
  document.querySelector('[data-action="back-conferences"]').click();
  document.querySelector('[data-page="journals"]').click();
  document.querySelector('[data-journal-open="0"]').click();
  assert.ok(document.querySelector(".publication-chain"));

  document.querySelector('[data-action="back-journals"]').click();
  document.querySelector('[data-page="workspaces"]').click();
  assert.equal(document.querySelector('[data-xss="workspace"]'), null);
  assert.equal(document.querySelector('[data-xss="repository"]'), null);
  assert.ok(
    [...document.querySelectorAll(".workspace-card h2")].some((node) =>
      node.textContent.includes('<img data-xss="workspace"'),
    ),
  );

  document.querySelector(".user-menu").click();
  document.querySelector('[data-action="logout"]').click();
  await new Promise((resolve) => setTimeout(resolve, 20));
  document.querySelector('[data-action="open-auth"]').click();
  assert.ok(document.querySelector('.auth-dialog[data-auth-form="login"]'));
  document.querySelector('[data-auth-switch="register"]').click();
  assert.ok(document.querySelector('.auth-dialog[data-auth-form="register"]'));

  dom.window.close();
});
