# CONN Pilot private beta plugin

This package connects Codex or ChatGPT Work to the deployed CONN Pilot MCP
server and adds four researcher workflows. Authentication is performed by the
server through Auth0; no OpenAI API key is required by this plugin.

For local testing, add the repository as a marketplace and install the plugin:

```powershell
codex plugin marketplace add C:\path\to\conn-pilot
codex plugin add conn-pilot@conn-pilot-private
```

For a ChatGPT Business pilot, an administrator can publish the locally tested
plugin to the workspace and grant access only to the intended roles. Each
researcher then authenticates independently with the CONN Pilot Auth0 account
assigned to them.
