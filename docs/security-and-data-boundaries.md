# Security and data boundaries

This public repository intentionally documents behavior without publishing
operator credentials, private host addresses, local paths, or infrastructure
runbooks containing machine-specific details.

## Researcher access

- The MCP endpoint uses OAuth authorization-code flow with PKCE and dynamic client
  registration where supported.
- Pilot accounts are allowlisted; public self-registration is disabled.
- Each token is checked for signature, issuer, audience, expiry, subject, and the
  `conn-pilot:use` permission.
- User-owned records are isolated by authenticated subject.

## Worker access

The worker uses a separate service credential and outbound HTTPS. Researcher
clients never receive that credential. Raw images and machine paths stay local.

## Repository rules

- Never commit `.env` files, access tokens, client secrets, private keys, local
  dataset registries, NIfTI images, MATLAB projects, or execution databases.
- OAuth should happen in the browser. An assistant must never ask a researcher to
  paste a one-time code, password, token, or secret into chat.
- Examples use placeholders unless a public service URL is required for access.
- Report suspected vulnerabilities privately using [SECURITY.md](../SECURITY.md).

## Scientific privacy

Selected derivatives and QC images can still be sensitive. Institutions should
review consent, de-identification, data-use agreements, and cross-border transfer
requirements before registering a dataset or sharing a reproducibility package.
