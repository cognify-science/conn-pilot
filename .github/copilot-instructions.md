# Copilot instructions

This repository implements CONN Pilot, a research system for reproducible
resting-state fMRI connectivity workflows. Read `SCIENTIST_CONTEXT.md`,
`AGENTS.md`, `docs/README.md`, and the versioned contracts before proposing
changes.

Keep scientific decisions explicit and auditable. Separate execution status,
subject QC, inferential statistics, and scientific conclusions. Do not add
credentials, private infrastructure, local dataset paths, or source imaging data
to code, documentation, tests, logs, or generated examples.

When configuring an MCP client, use the public endpoint and browser OAuth as
documented in `docs/integrations/`; never ask a researcher to paste a token or
secret into a conversation.
