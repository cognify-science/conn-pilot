# Scientific documentation map

This documentation describes the scientific behavior of CONN Pilot without
publishing credentials, host addresses, local paths, or infrastructure runbooks.

Start with the repository-level [scientific context](../SCIENTIST_CONTEXT.md).
It gives humans and AI assistants one question-to-source map and explains when
runtime MCP evidence is required.

## Method and execution

- [Detailed scientific module reference](science/scientific-modules.md)
- [Implemented statistical methods](science/statistical-methods.md)
- [Worked WU120 example](science/worked-example.md)
- [Scientific report template](science/study-report-template.md)
- [Preloaded public benchmark datasets](science/preloaded-datasets.md)
- [Public benchmark validation — October 2026](science/benchmark-validation-2026-10.md)
- [Architecture and trust boundaries](science/architecture.md)
- [Pipeline construction and lifecycle](science/pipeline-lifecycle.md)
- [Parameter selection](science/parameter-selection.md)
- [Parameter-selector evaluation protocol](science/parameter-selector-evaluation.md)
- [Evidence corpus](science/evidence-corpus.md)
- [Evidence governance](science/evidence-governance.md)
- [Quality control and inference](science/qc-and-inference.md)
- [Subject-level QC review manual](science/qc-manual.md)
- [Reproducibility outputs](science/reproducibility.md)
- [Data governance, ethics, and licensing](science/data-governance.md)
- [Scientific glossary](science/glossary.md)
- [Scientific questions and claim boundaries](science/scientific-faq.md)
- [Execution preflight](execution-preflight.md)
- [Modular pipeline builder](modular-pipeline-builder.md)
- [Resilient worker semantics](resilient-worker.md)
- [MCP scientific tool reference](reference/mcp-tools.md)
- [Official CONN sources by scientific topic](reference/conn-official-sources.md)

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
- [Release changelog](../CHANGELOG.md)

## Machine-readable sources

The scientific statements in these pages can be checked against:

- [official CONN consultation index](reference/conn-official-sources.json), with
  release-pinned source links and primary methodological references;
- pipeline contracts in `catalog/pipelines/`;
- stage contracts in `catalog/stages/`;
- tool and result schemas in `contracts/`;
- corpus metadata and normalized paper instances in `knowledge/pipeline_review/`;
- the deterministic implementation in `src/conn_pilot/`;
- executable verification in `tests/`.

Where prose and a versioned contract disagree, the contract defines what that
software version can execute. Neither source supersedes scientific judgment.

Saved-model, QC availability and structured inference checks are described in the
[automatic scientific audit guide](science/scientific-audit.md).
