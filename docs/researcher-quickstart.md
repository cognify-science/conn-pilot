# Researcher quickstart

CONN Pilot is designed to be operated through an MCP-capable AI assistant such
as ChatGPT/Codex, Claude, Copilot Studio, Microsoft 365 Copilot, or a custom
agent. The researcher does not need to edit MATLAB or YAML to use a supported
workflow.

Before beginning, give the assistant the repository and ask it to read
`SCIENTIST_CONTEXT.md`. Connect to the authenticated MCP server using the guide
for your client in `docs/integrations/`. Never paste a password, one-time code,
token, client secret, private host address, or local dataset path into a chat.

## 1. Discover the current scope

Ask:

> Show my identity-scoped capabilities, visible datasets, supported pipelines,
> available seeds, and system health. Do not create or run anything.

The assistant should use runtime tools. Repository documentation cannot prove
that a particular dataset or worker is currently available.

## 2. State the scientific question

Specify the population, resting-state condition, seed or ROI question,
one-sample or two-group design, covariates, contrast direction, hypothesis,
decision rule, multiplicity family, and sample limitation. The assistant should
identify unsupported designs before creating a project.

The current scope is one-session raw-BIDS resting-state fMRI, seed-to-voxel or
ROI-to-ROI bivariate connectivity, and one-sample or two-independent-group
second-level designs with optional numeric covariates.

## 3. Review the project and parameters

Ask the assistant to show the complete specification and pipeline graph. For
every unresolved parameter, review:

- allowed values and target CONN field;
- acquisition context such as TR and slice metadata;
- explicit, inferred, and unreported literature observations;
- source roles and applicability;
- reasonable alternatives and uncertainty.

Record the chosen value, rationale, and exact evidence identifiers. Literature
frequency is descriptive and must not become an automatic recommendation.

## 4. Validate before execution

Ask:

> Validate the project and show the frozen execution plan, versions, contrast,
> parameters, preflight decisions, and remaining blockers. Do not submit yet.

Submit only after those records match the intended study. Repeating a request
should reuse an existing compatible project or active job rather than creating a
duplicate.

## 5. Monitor execution

The assistant should distinguish supervisor health, live MATLAB/CONN activity,
durable stage progress, and technical completion. A worker heartbeat does not by
itself prove MATLAB progress. Conversely, a long CONN stage can be healthy even
when no participant milestone changes for several minutes.

## 6. Review QC

After technical completion, follow the [QC manual](science/qc-manual.md). Inspect
ART, registration, normalization, segmentation, denoising, and temporal metrics.
The assistant may summarize or flag evidence, but it must not record `accept`,
`exclude`, or `needs_review` without an explicit attributable decision.

If the reviewed sample changes, request a new second-level calculation and
verify its participant counts, design matrix, rank, residual degrees of freedom,
sample version, and output version. The old result remains preserved and stale.

## 7. Interpret and export

Read the experiment-quality report before recording a scientific conclusion.
Keep technical completion, subject QC, sample currency, statistics, and
hypothesis evidence separate. Report effects and uncertainty or tests together
with the prospective multiplicity rule and design limitations.

Finally, generate the reproducibility package for the current result and sample
version. It records methods, parameter provenance, evidence, QC, results,
decisions, artifacts, and hashes without redistributing raw source images.

The [worked WU120 example](science/worked-example.md) demonstrates this lifecycle
with completed public benchmark results, and the [MCP tool reference](reference/mcp-tools.md)
maps every step to the current server tools.
