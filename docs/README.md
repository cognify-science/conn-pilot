# Scientific documentation map

This documentation describes the scientific behavior of CONN Pilot without
publishing credentials, host addresses, local paths, or infrastructure runbooks.

## Method and execution

- [Detailed scientific module reference](science/scientific-modules.md)
- [Preloaded public benchmark datasets](science/preloaded-datasets.md)
- [Public benchmark validation — October 2026](science/benchmark-validation-2026-10.md)
- [Architecture and trust boundaries](science/architecture.md)
- [Pipeline construction and lifecycle](science/pipeline-lifecycle.md)
- [Parameter selection](science/parameter-selection.md)
- [Evidence corpus](science/evidence-corpus.md)
- [Quality control and inference](science/qc-and-inference.md)
- [Reproducibility outputs](science/reproducibility.md)
- [Execution preflight](execution-preflight.md)
- [Modular pipeline builder](modular-pipeline-builder.md)
- [Resilient worker semantics](resilient-worker.md)

## Access through an AI client

- [AI-assisted setup](integrations/ai-assisted-setup.md)
- [ChatGPT and Codex](integrations/openai-clients.md)
- [Claude and Claude Code](integrations/claude.md)
- [Copilot Studio and Microsoft 365 Copilot](integrations/microsoft-copilot.md)
- [Client-independent verification checklist](integrations/verification-checklist.md)
- [Copyable assistant bootstrap prompt](integrations/assistant-bootstrap-prompt.md)

## Validation and scope

- [Internal validation](internal-validation.md)
- [Pilot readiness](pilot-readiness.md)
- [External pilot protocol](external-pilot-protocol.md)
- [Known technical debt](technical-debt.md)
- [Security and data boundaries](security-and-data-boundaries.md)

## Machine-readable sources

The scientific statements in these pages can be checked against:

- pipeline contracts in `catalog/pipelines/`;
- stage contracts in `catalog/stages/`;
- tool and result schemas in `contracts/`;
- corpus metadata and normalized paper instances in `knowledge/pipeline_review/`;
- the deterministic implementation in `src/conn_pilot/`;
- executable verification in `tests/`.

Where prose and a versioned contract disagree, the contract defines what that
software version can execute. Neither source supersedes scientific judgment.
