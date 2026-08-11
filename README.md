# PeerXiv

PeerXiv is an archive-first research network for publishing evolving preprints,
retaining version and artifact context, discussing work, and connecting with
other researchers. Its interface combines the scholarly density of a preprint
archive with community discovery, voting, and threaded discussion.

## Interface

- The homepage is a chronological feed of recent and revised papers.
- Every paper appears in a card with its subject code, PeerXiv identifier,
  version, authors, abstract, tags, vote score, citations, and discussion count.
- Explore expands into a tree of topic communities, subject codes, and activity
  counts in the left navigation. Discussions has its own nested branch for
  active, new, followed, and saved threads.
- Global search sits in the center of the top navigation.
- Submission, notifications, Messages, and researcher actions live in the top
  navigation, with Messages immediately to the right of notifications.
- Registration and sign-in use signed Flask sessions, HttpOnly cookies, scrypt
  password hashes, and per-session CSRF tokens. Drafts, publications, follows,
  discussions, comments, notifications, activity, and private spaces enforce
  authenticated ownership or membership at the API boundary. Production
  registration defaults to invite-only and can also be disabled.
- Paper detail pages join the formal research record to public discussion and
  version history.
- Cite opens a formatted export workflow for APA, MLA, Chicago, and BibTeX,
  including clipboard fallback and downloadable `.bib` output. Share links are
  permanent hash routes that reopen the exact paper; a paper can also be sent
  directly into an existing PeerXiv message conversation.
- Messages are stored in the database, enforce conversation membership, track
  unread/read state, and update connected browsers through Socket.IO.
- Discussions have active/new/following/saved views, permanent links, voting,
  follow/save controls, paper relationships, persistent replies, and Socket.IO
  creation events. New discussion and reply text continues through the CoU
  related-research matcher.
- On mobile, the research tree becomes an off-canvas drawer, the global search
  moves to its own header row, paper actions remain horizontally scrollable,
  and Messages transitions from inbox to conversation with an explicit back
  action.
- The secondary rail remains present on tablet: below the feed in portrait and
  beside the feed in landscape. The full three-column navigation/feed/rail
  layout begins at desktop width.
- Research spaces include Workspaces, Presentations, Conferences, and Journals.
  Workspaces connect submitted papers to Git repositories, Overleaf projects,
  artifacts, and collaborators.
- Research Spaces has a working overview and navigable records: workspace tabs,
  presentation outlines and export, conference details and related papers, and
  inspectable preprint-to-journal publication relationships. Workspaces,
  presentations, conferences, journal concepts, memberships, linked papers,
  and resources are persisted through the Flask API with public/private access.
- ORCID, Overleaf, and provider-neutral Git setup flows validate and retain
  local configuration without pretending that OAuth or synchronization has
  completed. Authenticated synchronization belongs to the backend integration
  layer.
- New drafts and publications are created through the Flask API. Publication
  quarantines the upload, validates and reconstructs the PDF without active
  document actions, scans both raw and rebuilt forms when ClamAV is configured,
  stores and checksums the accepted file, runs CoU classification, assigns
  the category and descriptive metadata, and returns related-research
  notifications. CoU-derived interests also power exact-subtopic notifications
  and people-to-follow explanations; followed-researcher activity appears in
  the desktop/tablet rail and profile.

## Run locally

```sh
cd client
python3 server.py
```

Open <http://127.0.0.1:8000>.

The historical `python3 app.py` command remains available as a compatibility
entry point and starts the same Flask-SocketIO server.

## Backend development

PeerXiv now uses a Flask application factory with Django-style project
configuration and domain Blueprints for Accounts, Papers, Social, Discovery,
Research Spaces, and Journals. `peerxiv/classifier.py` is the versioned Calculus of Uncertainty
classification boundary. The registered paper backend uses recurrent category
state, local eligibility traces, validation-gated lateral propagation, Gamma
refinement, and kappa validation without a global backward pass.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cd client
flask --app server db upgrade
python3 server.py
```

HTTP communication is rooted at `/api/v1`. Socket.IO uses the `/social`
namespace. PostgreSQL is the intended deployment database; SQLite is the
zero-configuration development default. Redis is optional for a single local
server and required when Socket.IO or background jobs span processes.

For production, use the included Docker/Compose or Gunicorn entry point and the
fail-fast environment contract in [DEPLOYMENT.md](DEPLOYMENT.md). The development
server intentionally does not stand in for the production process.

Run the backend and browser-DOM interaction suites together with:

```sh
make test
```

Paper classification is available through:

```text
POST /api/v1/discovery/classify
POST /api/v1/papers/{identifier}/classify
GET  /api/v1/papers/{identifier}/metadata
GET  /api/v1/papers/{identifier}/pdf
POST /api/v1/discovery/notifications/matches
POST /api/v1/discovery/notifications/classify
```

Authenticated community and collaboration APIs include:

```text
POST /api/v1/accounts/register
POST /api/v1/accounts/login
GET  /api/v1/accounts/notifications
GET  /api/v1/accounts/people/recommendations
GET  /api/v1/accounts/activity
GET/POST /api/v1/social/conversations
GET/POST /api/v1/social/conversations/{id}/messages
POST /api/v1/social/conversations/{id}/read
GET/POST /api/v1/social/discussions
POST /api/v1/social/discussions/{id}/comments
POST /api/v1/social/discussions/{id}/{follow|save|vote}
GET/POST /api/v1/spaces
POST /api/v1/spaces/{id}/{resources|papers|members}
```

The classifier returns a complete CoU trace and descriptive metadata tags with
facets, definitions, five-state classifications, weights, supporting excerpts,
and provenance. See [COU_CLASSIFIER.md](COU_CLASSIFIER.md) for the executable
mapping and current validation boundary.

## Rebuild styles

The responsive layout uses Tailwind CSS v4 compiled into the project, so the
development server does not require a live Tailwind CDN connection.

```sh
npm install
npm run build
```

To start a local alpha with an empty SQLite database, run this from the project
root after activating the virtual environment:

```sh
make reset-dev-db PYTHON=python
```

The reset command refuses to run in production or while `DATABASE_URL` points
at an external database. Legacy browser showcase records are cleared
automatically when the alpha frontend first loads.

The current build has durable accounts, sessions, invite gating, paper ownership,
classification, quarantined/reconstructed PDFs, persistent messaging,
discussions, replies, follows, votes, notifications, activity, and Research
Spaces. It ships with no sample accounts or research
records; every paper, discussion, notification, and Research Space is loaded
from the API. Development PDFs are stored under `client/uploads/manuscripts`;
production uses the configured durable filesystem adapter and should move to
object storage before horizontal scaling. Verified email/password recovery,
verified ORCID identity, provider OAuth, webhooks, moderation, remote
synchronization, and horizontally scaled notification delivery remain
pre-public-launch work.

See [BACKEND_PLAN.md](BACKEND_PLAN.md) for the proposed persistent API and CoU
integration boundary.
