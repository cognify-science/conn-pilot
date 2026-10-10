# Preloaded public benchmark datasets

CONN Pilot's research-preview environment registers a small set of public BIDS
datasets so a researcher can exercise the supported pipelines without first
onboarding an institutional dataset. The source neuroimages are not stored in
this GitHub repository. They remain on an authorized execution worker, while
the MCP service exposes only an identity-scoped, path-free inventory.

Runtime availability is authoritative: an AI client or researcher should call
`list_datasets` before designing a project. A dataset listed here may be hidden
from an identity, temporarily unavailable on a worker, or superseded by a
versioned registration.

## Registered scientific benchmark subsets

| CONN Pilot dataset ID | Public source | Registered subset | Resting-state TR | Intended role |
| --- | --- | --- | --- | --- |
| `evaluation_wu120_15` | [Washington University 120, OpenNeuro ds000243](https://openneuro.org/datasets/ds000243/snapshot) | 15 healthy control participants | 2.5 s | One-sample resting-state benchmark. The prospective check expects positive PCC/default-mode connectivity, including PCC-MPFC coupling. |
| `evaluation_fibromyalgia_20` | [A behavioral and brain imaging dataset with focus on emotion regulation of women with fibromyalgia, OpenNeuro ds004144](https://openneuro.org/datasets/ds004144/versions/1.0.2) | 10 women with fibromyalgia and 10 matched healthy control women | 2.0 s | Two-independent-group benchmark. Bilateral group differences are exploratory in this fixed subset. |
| `evaluation_ucla_schizophrenia_20` | [UCLA Consortium for Neuropsychiatric Phenomics LA5c Study, OpenNeuro ds000030](https://openneuro.org/datasets/ds000030/versions/1.0.0) | 10 participants with schizophrenia and 10 healthy controls | 2.0 s | Two-independent-group benchmark. Bilateral group differences are exploratory in this fixed subset. |

The subset sizes describe the registered CONN Pilot samples, not the complete
OpenNeuro cohorts. They were selected to validate end-to-end behavior under a
bounded compute budget. They do not establish prospective statistical power and
must not be presented as definitive replications of the source studies.

## Technical smoke subsets

Two smaller registrations exist only for fast technical checks:

| CONN Pilot dataset ID | Composition | Permitted interpretation |
| --- | --- | --- |
| `evaluation_wu120_smoke3` | 3 healthy control participants from WU120 | Pipeline wiring, artifact generation, and failure detection only. |
| `evaluation_fibromyalgia_smoke3` | 3 participants from the fibromyalgia dataset | Pipeline wiring, artifact generation, and failure detection only. |

A successful smoke run establishes technical executability for that input and
software version. It provides no useful test of a population-level scientific
hypothesis.

## What “preloaded” means

Preloaded means that the dataset has been registered on an authorized worker
and can be referenced by its stable dataset ID. It does not mean that:

- raw or derived participant data are distributed with this repository;
- every authenticated researcher can see every registration;
- CONN Pilot owns or relicenses the source data;
- the benchmark subset replaces the full source dataset;
- a successful analysis implies acceptable subject quality or scientific
  confirmation.

Each OpenNeuro source retains its own version, citation, license, known issues,
and acquisition documentation. Researchers should cite the exact source
snapshot and its associated study paper when reporting results. CONN Pilot's
reproducibility package records the registered dataset identifier and a
path-free inventory, but it does not redistribute source neuroimages.

## Dataset-specific cautions

- **WU120:** the OpenNeuro record describes typical young adults without a
  reported significant neurological or psychiatric history. Slice-timing
  metadata may be absent from the BIDS sidecars; CONN Pilot therefore requires
  an explicit preflight resolution and never invents a slice order.
- **Fibromyalgia:** the full public cohort consists of women with fibromyalgia
  and matched healthy women. The registered 20-participant subset preserves a
  balanced two-group comparison but is too small for broad confirmatory claims.
- **UCLA CNP:** the source dataset contains several diagnostic groups and tasks.
  The registered benchmark uses resting-state data from schizophrenia and
  healthy-control participants only. Findings from this subset do not generalize
  automatically to the other diagnoses or tasks in the source dataset.

These registrations are reference material for the research preview. Adding a
new institutional dataset requires separate governance, data-use review, BIDS
validation, worker registration, and identity-scoped authorization.

The completed six-analysis evaluation of these registrations is documented in
[Public benchmark validation — October 2026](benchmark-validation-2026-10.md).
