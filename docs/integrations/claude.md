# Claude and Claude Code

## Claude Code

Add the remote server at user scope:

```powershell
claude mcp add --transport http --scope user conn-pilot `
  https://control-plane-production-0adf.up.railway.app/mcp
```

Open Claude Code and run `/mcp` to inspect the server and start browser
authentication. The root `.mcp.json` is also suitable for clients that import
standard project MCP configuration.

`CLAUDE.md` gives Claude the repository-specific scientific boundaries. It does
not contain credentials or private infrastructure details.

## Claude web and desktop

Use the custom connector interface to add the remote MCP URL. Claude should
discover OAuth from the server. Team and Enterprise organizations may require an
owner to add or approve the connector before members can authenticate.

If the client cannot complete dynamic registration, stop and ask the CONN Pilot
administrator to register that client. Do not copy credentials from another
client or researcher.

Complete the [verification checklist](verification-checklist.md) before creating
an experiment.

Official reference: [Claude remote MCP custom connectors](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).
