# AI-assisted connection guide

This guide is written so that a researcher can give the repository URL to an AI
assistant and ask it to configure CONN Pilot. The connection uses a public MCP
endpoint and browser-based OAuth. No Auth0 administration, worker access, API
token, or local dataset path is required on the researcher's computer.

## Information the assistant may use

- MCP URL: `https://control-plane-production-0adf.up.railway.app/mcp`
- transport: Streamable HTTP
- authentication: OAuth 2.1 with discovery, PKCE S256, and dynamic client
  registration when the client supports it
- requested scope: `conn-pilot:use`

The assistant must never ask the researcher to paste a password, one-time code,
access token, refresh token, or client secret into chat. Browser authentication
is the expected flow.

## Installation sequence

1. Confirm that the AI client supports remote MCP servers and OAuth.
2. Add the endpoint using the client-specific guide in this directory.
3. Complete the browser login with the allowlisted researcher email.
4. Run the [verification checklist](verification-checklist.md).
5. Begin with read-only discovery. Do not create or run an analysis until the
   researcher has reviewed the dataset, design, contrast, and parameter record.

If automatic registration is unavailable, an administrator may need to register
the AI client in Auth0. This is an administrative exception; it does not justify
sharing an existing client secret among researchers.

## Safe first conversation

Copy the [assistant bootstrap prompt](assistant-bootstrap-prompt.md) into the AI
client. It tells the assistant to discover tools from MCP, preserve scientific
decision boundaries, and avoid submitting work during the connection test.

## What successful access means

A successful connection proves that the client can authenticate and call the
identity-scoped MCP service. It does not prove that a dataset is suitable, a
pipeline is scientifically justified, the worker is available, or a result is
scientifically valid.
