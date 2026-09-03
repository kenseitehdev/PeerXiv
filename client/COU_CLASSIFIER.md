# PeerXiv CoU lateral recurrent paper classifier

## Purpose

The first PeerXiv CoU algorithm reviews an ordered representation of a paper
and produces subject categories plus descriptive, evidence-bearing metadata.
It classifies what a paper is about and how it presents its contribution. It
does not claim that the paper's scientific conclusions are true.

Classifier version: `cou-paper-lateral-0.1.0`  
Taxonomy version: `peerxiv-subjects-2026.08`  
Metadata schema: `peerxiv.descriptive-metadata.v1`

## Execution model

The document is observed hierarchically as title, author keywords, abstract,
and ordered sections. Each observation updates a recurrent category state.
The network does not execute a global backward gradient pass.

For each observation at step `m`:

1. Compute direct evidence for every category.
2. Predict the next local evidence from the retained recurrent state.
3. Produce a local discrepancy between observed and predicted evidence.
4. Propagate that discrepancy laterally through the category-relation graph.
5. Apply movement, decay, and validation gates to every propagation round.
6. Retain the update through a local eligibility trace.
7. Append the resulting category state to its reconstruction history.

The classifier then evaluates each trajectory through the CoU stages:

- `Gamma`: rectangular, trapezoidal, and midpoint accumulation, followed by
  first-order extrapolation and logistic formulation;
- `R`: candidate category-state reconstruction;
- `Pi`: propagation across the configured forecast horizon;
- `C`: five-state category classification;
- `V_struct`: structural validation across document regions;
- `V_pred`: rolling predictive validation;
- `Eval`: thresholded selection while retaining every component and trace.

The current implementation performs local, within-document adaptation. A later
training milestone can persist validated local updates across a corpus after a
golden dataset and adversarial evaluation protocol are established.

## Descriptive metadata

A generated tag is a structured assertion rather than a bare string:

```json
{
  "facet": "method",
  "namespace": "peerxiv.method",
  "slug": "lateral-propagation",
  "label": "Lateral propagation",
  "description": "Propagates local state or update signals across contextually related units.",
  "state": "true",
  "weight": 0.94,
  "evidence": [
    {
      "location": "Abstract",
      "matched": ["lateral propagation"],
      "excerpt": "..."
    }
  ],
  "provenance": "cou-faceted-extraction"
}
```

Initial facets are:

- `subject`: arXiv-style subject classification;
- `paper-type`: theoretical, empirical, methodological, review, or systems;
- `contribution`: algorithm, framework, or evaluation;
- `method`: recurrent modeling, lateral propagation, uncertainty modeling,
  predictive validation, or state reconstruction;
- `evidence`: formal derivation, experiment, or benchmark;
- `artifact`: source code or dataset;
- `concept`: author-supplied and text-derived concepts.

Every generated record stores the classifier, taxonomy, and metadata-schema
versions. CoU runs remain append-oriented; the paper-version metadata record is
a replaceable query projection generated from the latest run.

## API

Preview classification without persistence:

```text
POST /api/v1/discovery/classify
```

Classify and persist metadata for the latest published paper version:

```text
POST /api/v1/papers/{identifier}/classify
GET  /api/v1/papers/{identifier}/metadata
```

Publication invokes classification automatically. Multipart publication can
include a PDF and ordered section excerpts; the response returns the immutable
version, category, descriptive metadata, and classification-driven research
matches. The PDF is available at:

```text
GET /api/v1/papers/{identifier}/pdf
```

Classification-driven notification projections are available for research,
comments, and discussions:

```text
POST /api/v1/discovery/notifications/matches
POST /api/v1/discovery/notifications/classify
```

Matches require exact method or concept overlap, or multiple corroborating
facets. Each result explains the overlapping tags. Durable recipient delivery
will be added with Accounts; the current frontend retains notification
projections in its local profile state.

The persistent endpoint is input-idempotent. Repeating the same classifier
version and document input reuses the existing classification run.

## Current boundaries

- The initial taxonomy is deliberately compact and auditable, not complete.
- PDF parsing is not implemented; clients currently provide ordered section
  text to the classification endpoint.
- Lateral relationships are explicit subject-graph edges, not learned hidden
  relationships yet.
- Corpus-level plasticity is disabled until labeled and adversarial validation
  datasets exist.
- Metadata is suitable for discovery and explanation, not automated peer
  review, publication acceptance, or research-integrity judgments.
