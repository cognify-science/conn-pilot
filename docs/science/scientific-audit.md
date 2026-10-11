# Automatic audit of saved scientific results

CONN Pilot audits saved second-level models and QC evidence before treating a
result as interpretable. This audit is separate from technical completion and
from an investigator's scientific decision. It does not rerun CONN, select a
favorable hypothesis endpoint, or automatically exclude participants.

## 1. Executed model verification

The auditor reads `SPM.mat` for seed-to-voxel or `ROI.mat` for ROI-to-ROI and
compares each model with the execution snapshot and current included sample:

- CONN's saved subject-selection mask, translated through original subject order;
- actual matrix rows and values for the frozen group and covariate definitions;
- saved effect names, including explicitly recorded recalculation aliases;
- full column rank and positive residual degrees of freedom;
- agreement between saved degrees of freedom and rows minus rank;
- between-subject contrast weights and the actual SPM/ROI test contrast;
- the single `rest` condition and its unit within-condition contrast;
- for SBC, the subject order in saved first-level BETA input filenames;
- coverage of all declared contrasts and distinct SBC source indices or
  requested ROI source labels.

The audit records matrix and model-file SHA-256 hashes without exporting raw
covariate matrices. Matching participant counts alone is insufficient. A matrix
with old covariate values, a changed sample, incorrect weights, a deficient rank,
or absent identity evidence remains failed or unverified. SBC source indices
establish distinct source coverage; exact atlas-label verification still needs
the corresponding first-level source registry.

CONN 25.b's saved structures were checked against its
[release-pinned processing source](https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_process.m).
An unreadable structure, including unsupported MAT v7.3 files, is reported as
unverified; file existence does not substitute for an inspected model.

## 2. Availability-aware QC

`metric_availability` accompanies every numeric QC field. Missing, ambiguous,
malformed, nonfinite, or unverified legacy measurements are `null`, not zero.
A verified ART matrix with no outliers legitimately produces an available zero.

The Python audit rereads the staged ART files and records their hashes. Outlier
counts use flagged **volume rows**; the longest streak is measured in acquisition
order, rather than by consecutive regressor columns. The audit checks that total,
outlier, retained, percentage, and streak values agree internally. Missing or
duplicate participant records cannot silently change the effective sample.

The required quantitative fields are total volumes, outlier volumes, retained
volumes, and mean ART displacement. They establish availability and consistency,
not scientific acceptability. Registration, normalization, segmentation and
denoising still require review of native CONN QA. Exported tSNR and DVARS are
explicitly labeled as preprocessed, before denoising. They cannot demonstrate
the success of denoising. No universal exclusion threshold is introduced.

## 3. Structured statistics and uncertainty

The first extractor supports univariate T models only:

| Analysis | Extracted evidence | Limits |
| --- | --- | --- |
| ROI-to-ROI | Per-source/target contrast effect, T, two-sided p, BH-adjusted p, and pointwise 95% interval | Recomputed OLS effects and T must agree with saved values; intervals are not simultaneous |
| Seed-to-voxel | Complete saved-mask testing family, significant voxel counts and a descriptive peak with effect, T, p and adjusted p | A selected peak is biased by selection; no naive peak interval or automatic hypothesis claim |

ROI intervals use saved participant data, the inspected matrix, contrast weights,
and residual variance. They remain defined for a zero effect and T=0; the code
does not divide effect by T. CONN's native ROI `p` is not assumed two-sided:
the audit recomputes `2 * sf(abs(T), df)` using the saved residual degrees of
freedom and checks its OLS reconstruction against the saved estimates. See the
[release-pinned CONN GLM](https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_glm.m).

Benjamini-Hochberg correction applies to **one explicitly defined saved model**:
all saved targets except self-connections for an ROI source, or all voxels in
the saved SBC mask. The audit does not discard nonfinite tested values to obtain
a smaller favorable family. It does not pool seeds or project contrasts, and
does not claim equivalence to CONN Explorer's selected family, cluster inference,
permutation inference, or a registered hypothesis's correction policy.

F/multivariate models, multiple conditions, unsupported image representations,
and missing or inconsistent inferential artifacts remain explicitly unavailable.
They must not be presented as nonsignificant or as zero effects.

## 4. Report and reproducibility integration

New completed runs and second-level recalculations generate
`scientific_audit.json`. Its containing immutable result/output version binds
the audit to the uploaded artifact hashes; the sidecar also records the included
sample version and execution-specification hash. It cannot contain its own
result hash without a circular dependency.
The audit also records its implementation-file hash and NumPy, SciPy and nibabel
versions, so independent numerical review can identify the extraction runtime.

`get_experiment_quality_report` exposes `automatic_audit` with model verification,
subject metric evidence, version identities, limitations and pending items.
The quality gates now require available QC and a verified executed model.
An older model with no audit is `unverified_model`, even if its files exist.
Technical success remains distinct from this stricter scientific gate.

Packages add `scientific-audit.json` and `statistical-results.json`, alongside
HTML/PDF reports, methods, decisions and artifact manifests. Reports record
elapsed wall time when start/end timestamps are available; that includes pauses
and is not a CPU-time measurement. Exploratory statistics never populate the
registered `hypothesis_assessment` automatically. A new second-level output
cannot inherit evidence from its predecessor; hypothesis evidence for a
recalculation must bind its `second_level_output_version` as well as the parent
result and sample identities.

## Existing results and validation boundary

The maintainer command `conn-pilot audit-results <run-directory>` reads an
existing execution snapshot and saved results. Optional `--second-level-run`
selects an existing recalculation. Each invocation writes a new `audit_reviews`
directory and preserves historical QC, models, manifests and result versions.
This command does not publish a replacement runtime result or alter prior
scientific decisions. It can recover ART evidence from legacy exports when
the original staged files remain available.

The implementation is covered by synthetic MAT/NIfTI integration tests,
numerical checks and gate/version regressions. These tests establish software
behavior, not numerical validation of a fresh CONN execution or clinical
validity. The published October benchmark summaries predate this automatic
auditor and are not retroactively reclassified by this release. Audit their
controlled originals and review the resulting evidence before making new
scientific claims.

See [`scientific_audit.v1.json`](../../contracts/scientific_audit.v1.json),
[QC manual](qc-manual.md), and [official CONN sources](../reference/conn-official-sources.md).
