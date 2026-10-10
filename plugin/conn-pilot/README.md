# CONN Pilot research-preview plugin

This package connects a compatible AI client to the authenticated CONN Pilot MCP
server and contributes five workflows: setup, experiment design, method
comparison, execution, and result review. Authentication uses browser OAuth;
the package contains no API key, access token, client secret, or worker address.

For Codex, add this repository as a marketplace and install the plugin:

```powershell
codex plugin marketplace add C:\path\to\conn-pilot
codex plugin add conn-pilot@conn-pilot-research-preview
```

Each researcher authenticates independently. Workspace administrators may
restrict installation or use. Read `docs/integrations/` in the repository for
ChatGPT, Codex, Claude, and Microsoft Copilot instructions.
