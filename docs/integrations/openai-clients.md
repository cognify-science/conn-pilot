# ChatGPT and Codex

## Codex CLI and Codex desktop

From a terminal, add and authenticate the remote server:

```powershell
codex mcp add conn-pilot `
  --url https://control-plane-production-0adf.up.railway.app/mcp `
  --oauth-client-registration dcr
codex mcp login conn-pilot --oauth-client-registration dcr
codex mcp list
```

The repository also includes `.mcp.json` and `.vscode/mcp.json`. An assistant
may use either file when the surrounding client recognizes that format. Login
must still happen in the browser under the researcher's own identity.

For the richest workflow in Codex, install the packaged plugin from
`plugin/conn-pilot/`. It contributes task-specific guidance for experiment
design, method comparison, execution, and result review. Direct MCP access and
the plugin use the same remote scientific tools.

## ChatGPT

When a ChatGPT workspace permits custom MCP connectors or plugins, use the same
MCP URL and OAuth discovery. Workspace administrators control whether a custom
connector may be installed and which members can use it. Each researcher should
authenticate separately.

After connection, use the [verification checklist](verification-checklist.md)
and the [bootstrap prompt](assistant-bootstrap-prompt.md). Keep project creation
and job submission as explicit scientific actions in the conversation.

Official references: [Codex MCP configuration](https://developers.openai.com/codex/mcp/),
[OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins/),
and [OpenAI plugin authentication](https://developers.openai.com/plugins/build/auth/).
