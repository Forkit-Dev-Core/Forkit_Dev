# Legacy version registry snapshot

`legacy-version-registry.json` is a fictional, deterministic snapshot of
persisted passport JSON and lineage, with no index database. It contains a model
and agent with version `1..0`, plus valid dependent model/agent records.

The malformed records were constructed with the version validator from commit
`c1e4c2a9c4939694c7a96ffbc308f88a39e20afc` (the parent of the strict version
validation change). That validator checked component count only. All other
schema fields and ID derivation were left intact. Timestamps are fixed and all
names and hashes are synthetic. The old IDs are consistent with the original
identity fields; the versions intentionally fail current schema validation.

Upgrade tests materialize these JSON records and their lineage on disk before
calling `rebuild_index()`. They do not create invalid records by calling the
current `register_model()` / `register_agent()` methods or relaxing validation
in the tests. They also verify a valid neighboring record, raw inspection,
explicit recovery with a new ID, and preservation of original lineage links.
