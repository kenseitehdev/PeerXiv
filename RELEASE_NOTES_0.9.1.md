# PeerXiv 0.9.1 — Zenodo bucket upload compatibility

## Fixed

- Send manuscript uploads to Zenodo bucket URLs as
  `application/octet-stream`, as required by the live Zenodo API.
- Preserve and reuse an existing unpublished Zenodo deposit when retrying a
  reservation after an upload failure.
- Add a regression assertion for the required upload media type.

No database migration is required after 0.9.0.
