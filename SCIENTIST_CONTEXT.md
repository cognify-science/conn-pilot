# CONN Pilot scientific context

Read this page first when answering scientific questions about CONN Pilot. It
summarizes the current executable scope and points to the evidence needed for a
deeper answer. The versioned catalog, contracts, and result records remain
authoritative over prose.

## What the product is

CONN Pilot is a research-preview system that turns a structured resting-state
fMRI question into a validated, versioned CONN Toolbox execution. It combines:

- a constrained experiment and pipeline contract;
- a versioned literature-evidence corpus;
- investigator-confirmed method decisions;
- deterministic MATLAB batch generation;
- remote execution with durable job identity;
- subject-level QC and sample versioning;
- second-level recalculation after QC;
- hypothesis-aware reporting and reproducibility export.

It is not an official CONN Toolbox product, a clinical device, an autonomous
scientist, or a general interface to arbitrary MATLAB code.

## Current scientific scope

- Raw BIDS resting-state fMRI with one session per participant.
- CONN default MNI-space preprocessing.
- Seed-to-voxel bivariate correlation and ROI-to-ROI bivariate correlation.
- Built-in CONN atlas, network, and Schaefer regions.
- One-sample and two-independent-group second-level designs.
- Optional continuous covariates and explicit contrasts.
- MATLAB R2023b, SPM25, and CONN 25.b in the validated environment.

Longitudinal and repeated-measures designs, task connectivity, PPI, dynamic
connectivity, graph analysis, ICA, arbitrary external ROIs, arbitrary MATLAB,
and automatic power analysis are outside the executable contract.

## Governing scientific separation

Always report these states separately:

1. **Technical completion:** expected stages and artifacts exist.
2. **Subject quality:** current QC evidence and investigator decisions.
3. **Sample currency:** second-level output matches the reviewed sample.
4. **Statistical evidence:** effect, uncertainty or test, and multiplicity.
5. **Scientific interpretation:** compatibility with a prospectively specified
   hypothesis and the limits of the design.

A successful job is not proof of data quality. A significant result is not
proof that a hypothesis is true. A non-significant result is not proof of no
effect.

## Where to answer common questions

| Question | Authoritative entry point |
| --- | --- |
| Where should I verify CONN algorithms, defaults, and methodological references? | [Official CONN source guide](docs/reference/conn-official-sources.md) and [machine-readable index](docs/reference/conn-official-sources.json) |
| What modules exist and how do they interact? | [`docs/science/scientific-modules.md`](docs/science/scientific-modules.md) |
| What exactly happens to the images and time series? | [`docs/science/statistical-methods.md`](docs/science/statistical-methods.md) |
| What pipelines and designs are supported? | [`docs/science/pipeline-lifecycle.md`](docs/science/pipeline-lifecycle.md) and `catalog/` |
| How are parameters selected? | [`docs/science/parameter-selection.md`](docs/science/parameter-selection.md) |
| How should the selector's performance be evaluated? | [`docs/science/parameter-selector-evaluation.md`](docs/science/parameter-selector-evaluation.md) |
| What papers are in the corpus and how are they governed? | [`docs/science/evidence-corpus.md`](docs/science/evidence-corpus.md) and [`docs/science/evidence-governance.md`](docs/science/evidence-governance.md) |
| Which datasets are registered? | [`docs/science/preloaded-datasets.md`](docs/science/preloaded-datasets.md) and runtime `list_datasets` |
| How did the benchmarks perform? | [`docs/science/benchmark-validation-2026-10.md`](docs/science/benchmark-validation-2026-10.md) |
| How should QC be performed? | [`docs/science/qc-manual.md`](docs/science/qc-manual.md) |
| How are saved models, QC availability and statistics audited? | [Automatic scientific audit](docs/science/scientific-audit.md) and `contracts/scientific_audit.v1.json` |
| What statistical claims are permitted? | [`docs/science/qc-and-inference.md`](docs/science/qc-and-inference.md) |
| Can I inspect a complete study lifecycle? | [`docs/science/worked-example.md`](docs/science/worked-example.md) |
| What does each MCP tool do? | [`docs/reference/mcp-tools.md`](docs/reference/mcp-tools.md) |
| What is in a reproducibility package? | [`docs/science/reproducibility.md`](docs/science/reproducibility.md) |
| What must a scientific report contain? | [`docs/science/study-report-template.md`](docs/science/study-report-template.md) |
| How are privacy, identity, and data use handled? | [`docs/science/data-governance.md`](docs/science/data-governance.md) |
| What does a term mean? | [`docs/science/glossary.md`](docs/science/glossary.md) |
| Which claims are established and which remain open? | [`docs/science/scientific-faq.md`](docs/science/scientific-faq.md) |

## Runtime verification

Repository documentation describes a software release. Runtime state can
change. Before answering operational questions, an authenticated assistant
should call read-only tools in this order:

1. `get_product_capabilities`;
2. `list_datasets`;
3. `list_pipelines`;
4. `get_system_health`;
5. project- or job-specific read tools when an identifier is supplied.

Never invent a dataset, seed, paper, result, parameter, or worker state from the
documentation. Cite the exact runtime record and its version.

For underlying CONN behavior, use the [official source guide](docs/reference/conn-official-sources.md).
It distinguishes released code, mutable official documentation, primary
methodology, Pilot's supported contract, and actual execution evidence. Its
source identifiers are consultation references, not selector evidence IDs.

## Current validation conclusion

Six full analyses over WU120, fibromyalgia, and UCLA CNP completed technically.
After QC, the final samples were 15, 9+9, and 8+8 participants respectively.
The WU120 analyses recovered the prospectively specified PCC-centered default
mode positive control. The two clinical benchmarks produced no corrected
support for their restricted PCC comparisons and remain inconclusive in their
small subsets. This demonstrates a traceable supported workflow; it does not
establish autonomous paper replication or universal parameter optimality.

Important implementation limits remain: some CONN options inherit toolbox
defaults; actual design-matrix rank and degrees of freedom still require
inspection; structured hypothesis evidence is not automatically extracted from
every completed model. The methods and FAQ pages explain these boundaries.

## Parameter resolver assessment revision

New parameter resolutions use `context-and-strict-normalization-v2.1`. The existing
MCP guidance reports all mapped observations, execution exclusions, descriptive
family/modality alignment and unassessed applicability dimensions. A hashed
`selection_audit` freezes the decision-time candidate set, context and citations;
recorded context changes require review before a new submission. Legacy decisions
have no retroactive audit. This improves traceability, not evidence that the
chosen values outperform alternatives. See [parameter selection](docs/science/parameter-selection.md)
and [evaluation protocol](docs/science/parameter-selector-evaluation.md).
