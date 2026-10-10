# Copilot Studio and Microsoft 365 Copilot

Microsoft clients can consume CONN Pilot as a remote Streamable HTTP MCP server.
The exact screens depend on tenant policy and product release, so the assistant
should use the current Microsoft MCP onboarding flow rather than inventing a
custom HTTP connector.

## Copilot Studio

1. Open the target agent and add an existing MCP server or MCP tool.
2. Choose Streamable HTTP and enter
   `https://control-plane-production-0adf.up.railway.app/mcp`.
3. Select OAuth with discovery and dynamic client registration when offered.
4. Save the connection and complete browser authentication as the researcher.
5. Add the [bootstrap prompt](assistant-bootstrap-prompt.md) to the agent's
   instructions, adapting wording without weakening its scientific boundaries.
6. Run the [verification checklist](verification-checklist.md).

## Microsoft 365 Copilot and custom agents

Use the tenant's supported agent builder, Agents Toolkit, or declarative-agent
workflow to attach the same MCP server. A Microsoft 365 administrator may need
to allow custom agents, MCP tools, or the CONN Pilot domain. Tenant approval and
CONN Pilot identity authorization are separate checks.

Prefer OAuth discovery and dynamic registration. If the selected Microsoft flow
requires a fixed client identifier or redirect URI, ask a CONN Pilot
administrator to create a dedicated client for that integration. Never embed a
client secret in a repository, agent instruction, or chat.

## Agent behavior

Configure the agent to show the proposed design, contrast, parameter values,
evidence identifiers, and validation result before submission. It must keep
technical completion, QC, statistical significance, and scientific conclusion
as separate judgments.

Official references: [add an MCP server in Copilot Studio](https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-existing-server-to-agent)
and [Microsoft 365 Copilot plugin authentication](https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-authentication).
