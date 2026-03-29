# Local MCP Server

Forkit Dev Core includes a local-only MCP server for read and draft workflows on top of the existing registry and verification logic.

Exposed tools:

- `get_passport`
- `verify_passport`
- `get_lineage`
- `search_registry`
- `create_draft_passport`

The server does not add hosted storage, org admin actions, approval chains, or enterprise governance flows. It only reads or drafts data from the local Forkit registry.

## Install

```bash
pip install -e ".[mcp]"
```

If you also want the `forkit` CLI entrypoint:

```bash
pip install -e ".[cli,mcp]"
```

## Run the server

Using the dedicated entrypoint:

```bash
forkit-mcp --registry-root /tmp/forkit-mcp-registry
```

Using the CLI alias after installing `.[cli,mcp]`:

```bash
forkit mcp serve --registry-root /tmp/forkit-mcp-registry
```

Using the module directly:

```bash
python -m forkit.mcp.server --registry-root /tmp/forkit-mcp-registry
```

All three start the same stdio server.

## Client configuration example

```json
{
  "mcpServers": {
    "forkit-local": {
      "command": "forkit-mcp",
      "args": ["--registry-root", "/tmp/forkit-mcp-registry"]
    }
  }
}
```

## Quick local demo

This example exercises the same tool surface without requiring an external MCP client:

```bash
python examples/mcp_quickstart.py
```

Expected output:

```json
{
  "search_results": 2,
  "passport_name": "mcp-demo-model",
  "verify_valid": true,
  "ancestor_count": 1,
  "draft_passport_id": "2769eee050f2eceee1a82c13b6b1317370e1449801eb6ac955a1d4ab3b61e171"
}
```

## Tool behavior

`get_passport`

- returns a locally stored `ModelPassport` or `AgentPassport` by deterministic ID

`verify_passport`

- re-derives identity from stored content and returns the same verification payload used by the SDK and CLI

`get_lineage`

- returns the requested passport plus local ancestor and descendant graph data

`search_registry`

- searches by name or creator, or lists local entries when `query` is blank

`create_draft_passport`

- validates a local draft payload and returns the deterministic `id` without storing it
