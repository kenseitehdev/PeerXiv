# PeerXiv 0.10.0 — managed DOI reservation

## Changed

- New Zenodo deposits use the current InvenioRDM records API instead of the
  legacy deposition API.
- PeerXiv creates complete draft metadata and then calls Zenodo's dedicated
  managed-DOI reservation endpoint.
- PDF upload uses the current initialize, binary upload, and commit flow.
- PeerXiv verifies that the returned DOI is DataCite-managed and rejects an
  external-DOI state before uploading the manuscript.
- Drafts created by PeerXiv before 0.10 retain legacy publish compatibility.

## Safety

- Publication remains a separate, exact-DOI-confirmed action.
- Production publication remains disabled unless
  `PEERXIV_ZENODO_ALLOW_PRODUCTION_PUBLISH=1` is explicitly configured.
- No database migration is required after PeerXiv 0.9.0.
