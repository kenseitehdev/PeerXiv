# PeerXiv backend handoff

## Selected implementation architecture

PeerXiv is a Flask modular monolith organized with a Django-like project
package and domain Blueprints:

- `peerxiv/__init__.py` owns the application factory;
- `peerxiv/settings.py` owns environment-specific configuration;
- `peerxiv/urls.py` registers the versioned API Blueprints;
- `peerxiv/extensions.py` initializes SQLAlchemy, migrations, and Socket.IO;
- `peerxiv/classifier.py` is the versioned Calculus of Uncertainty classifier
  boundary and persistent run record;
- `server.py` serves the frontend, HTTP API, and Socket.IO transport;
- Accounts, Papers, Social, Discovery, Research Spaces, and Journals are the
  current domain modules.

PostgreSQL is the production source of truth. SQLite remains available for
local development. Redis coordinates Socket.IO and later Celery workers when
the application spans processes.

## Goal

Replace browser-local prototype state with a durable, multi-user research
platform while preserving the current frontend workflows. CoU must enrich the
research record without flattening state, evidence, validation, history,
context, dependencies, movement, or uncertainty into a single score.

## Boundary established by the frontend

The frontend now uses durable APIs for accounts and sessions, submissions,
workspaces, discussions, replies, persistent messages, follows, votes, notifications, activity,
conferences, journal links, presentations, and profiles. Browser storage is
used only for interface preferences, provisional collection names, and external
service configuration; it contains no sample archive or community records and
is not an authentication or synchronization mechanism.

Backend-only responsibilities are intentionally visible in the interface:

- object-backed PDF, slide, dataset, and artifact storage beyond the current
  quarantined local PDF adapter;
- accounts, sessions, organization membership, and authorization;
- ORCID authorization and verified identity data;
- Overleaf capability discovery, authorization, imports, and synchronization;
- Git provider authorization, repository access, releases, and webhooks;
- DOI and journal relationship verification;
- horizontally scaled real-time messaging and notification delivery;
- search indexing, moderation, audit records, and abuse controls;
- CoU calculation, provenance, explanation, and recalculation.

## Canonical data model

| Aggregate | Canonical records | Important invariants |
|---|---|---|
| Identity | User, ResearcherProfile, ExternalIdentity | Provider IDs are unique; verification state is explicit and auditable. |
| Research | Paper, PaperVersion, AuthorCredit, License | Published versions are immutable; corrections create new versions or explicit notices. |
| Workspace | Workspace, Membership, PaperLink, ResourceLink | A resource keeps its provider, immutable external ID, and last verified state. |
| Artifacts | Artifact, ArtifactVersion, FileObject | Checksums, media types, owners, provenance, and retention state are required. |
| Community | Discussion, Comment, Vote, Save, Collection | Idempotency and uniqueness prevent duplicate votes, saves, and retries. |
| Events | Conference, Presentation, Journal, PublicationLink | External relationships have source, verification, and review status. |
| Communication | Conversation, Participant, Message, Notification | Access follows conversation membership; read state is per user. |
| Integrations | Connection, SyncCursor, WebhookDelivery, SyncRun | Tokens are encrypted; connection status is separate from sync health. |

## CoU classifier model

CoU is PeerXiv's classifier and remains a versioned analytical layer, not a
column on `Paper`, a generic discovery score, or a replacement for ordinary
database behavior.

| CoU record | Purpose |
|---|---|
| StateSnapshot | A claim about system state at a specific boundary and time. |
| EvidenceAssertion | Evidence, provenance, observation time, scope, and source. |
| ValidationEvent | Who or what validated an assertion, by which rule, and with what result. |
| ContextFrame | Assumptions, environment, actors, and interpretive constraints. |
| Transition | Movement between snapshots, including proposed and observed change. |
| DependencyEdge | Explicit support, contradiction, derivation, and prerequisite relationships. |
| UncertaintyAssessment | A typed uncertainty result tied to inputs and a calculation version. |
| CoUProjection | A disposable read model for UI summaries and search; never the source of truth. |

Required CoU invariants:

1. Evidence and validation are independent records.
2. Observation time, assertion time, and ingestion time are distinct.
3. Context is referenced, versioned, and never silently replaced.
4. A transition cannot destroy its predecessor or its supporting evidence.
5. Conflicting evidence is retained and linked rather than overwritten.
6. Every assessment records its algorithm/schema version and complete input IDs.
7. Recalculation creates a new assessment; it does not mutate the old result.
8. UI confidence summaries are explainable projections, not canonical truth.

## API slices

Start with `/api/v1` and require an idempotency key on mutating endpoints that
can be retried.

| Slice | Initial endpoints |
|---|---|
| Session | `GET /me`, `POST /sessions`, `DELETE /sessions/current` |
| Papers | `GET/POST /papers`, `GET /papers/{id}`, `POST /papers/{id}/versions` |
| Files | `POST /uploads`, `POST /uploads/{id}/complete`, signed read URLs |
| Workspaces | `GET/POST /workspaces`, membership and resource subresources |
| Community | discussion, comment, vote, save, and collection endpoints |
| Messaging | conversation/message endpoints plus a server event stream |
| Discovery | feed, topic, conference, journal, researcher, and search endpoints |
| Connections | provider start/callback/disconnect, status, and sync-run endpoints |
| CoU | snapshots, assertions, validation events, contexts, transitions, dependencies, assessments, and projections |

Use cursor pagination for feeds and messages. Use optimistic concurrency tokens
for editable drafts and workspaces. Return stable machine error codes alongside
human-readable messages.

## Delivery sequence

1. **Contract and persistence:** freeze the JSON shapes used by the current UI,
   add migrations, PostgreSQL, repository interfaces, and API contract tests.
2. **Identity and authorization:** accounts, sessions, roles, workspace
   membership, object-level permissions, and audit events.
3. **Research records:** drafts, immutable published versions, upload lifecycle,
   checksums, licenses, author credits, and workspace links.
4. **Community and communication:** saves, votes, discussions, messages,
   notifications, moderation, and live delivery.
5. **External services:** implement ORCID first; run capability spikes for
   Overleaf and each Git provider before committing to sync semantics. Store
   encrypted tokens and process webhooks through an idempotent inbox.
6. **CoU foundation:** implement the canonical CoU records and validation rules
   before any score or visualization. Add an append-only event log and versioned
   calculation jobs.
7. **CoU projections:** expose explanations, timelines, dependency views, and
   uncertainty summaries only after golden-case and adversarial tests pass.
8. **Frontend cutover:** introduce an API repository beside local persistence,
   migrate one workflow at a time, and retain a development-only local adapter.

## First backend milestone

The first deployable milestone is intentionally narrow:

- authenticated researcher account;
- create/edit a draft;
- upload one PDF using a signed upload lifecycle;
- publish immutable version `v1`;
- create a workspace and connect that paper;
- list a chronological feed;
- preserve an audit event for every mutation.

The first CoU paper-classification slice is now implemented. It retains an
ordered observation trace, recurrent category histories, local eligibility,
lateral propagation rounds, Gamma refinements, kappa validation, movement,
forecast state, and evidence-bearing metadata. Corpus-level plasticity remains
disabled until golden-case and adversarial datasets prove the update behavior.

The next canonical CoU milestone still requires one end-to-end research-record
case containing two snapshots, three evidence assertions, two validation
events, one context, one transition, one dependency, and a reproducible
assessment. The paper classifier's metadata is a projection, not a substitute
for those canonical records.

## Decisions required before implementation

- deployment target and operational budget;
- authentication method and organization/tenant model;
- moderation and publication authority model;
- object storage and malware-scanning provider;
- golden and adversarial CoU paper-classification reference cases;
- which Overleaf and Git behaviors are required versus merely convenient;
- retention, deletion, embargo, licensing, and research-integrity policies.
