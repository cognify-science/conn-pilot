# Evaluation protocol for the parameter selector

The October 2026 benchmark showed that the selector was traceable, internally
consistent, executable, and concordant with one reserved expert baseline for all
comparable parameters. It did not show that the selector chooses better values
than reasonable alternatives. This protocol defines the next evaluation needed
to assess that claim.

## Evaluation questions

1. Does the selector recover defensible choices without seeing benchmark
   outcomes?
2. Does it explain why an option applies to the acquisition and scientific
   question?
3. Does it preserve uncertainty and disagreement rather than converting
   frequency into recommendation?
4. Do selected pipelines yield stable QC and estimates relative to blinded
   expert and paper-specific comparators?
5. Can an independent scientist reconstruct every choice from the recorded
   evidence snapshot?

## Frozen comparator arms

For each benchmark, define all arms before running any outcome analysis:

| Arm | Definition |
| --- | --- |
| Selector | Values produced through the CONN Pilot evidence-and-contract workflow. |
| Blinded expert | Values chosen independently by one or more domain experts who do not see selector choices or results. |
| Paper-specific | Values reported by the target paper when fully specified and executable. Missing values remain missing rather than guessed. |
| CONN reference | The documented CONN defaults for the applicable software and pipeline version. |

The scientific question, sample, seed or atlas, contrast, outcome family, QC
rubric, and multiplicity rule must be common across comparable arms. Values that
answer a different question are labeled non-comparable.

## Parameter-level endpoints

For smoothing, ART displacement, ART global threshold, white-matter components,
CSF components, temporal band, and GSR policy, report:

- exact agreement with each comparator;
- distance for numeric choices;
- whether the chosen value is explicit in the cited source;
- applicability completeness for acquisition, population, and analysis;
- number and role of supporting and conflicting sources;
- decision time and requests for clarification;
- reproducibility of the same decision from the frozen snapshot;
- independent expert ratings of defensibility and explanation quality.

Agreement alone is not success: several different values can be reasonable, and
experts can disagree. Ratings must include rationale quality and applicability.

## Pipeline-level endpoints

Evaluate downstream consequences without defining significance as success:

- retained volumes and QC flags;
- participant inclusion concordance under the common QC rubric;
- registration, normalization, segmentation, and denoising review;
- first-level effect distribution and test-retest or split-half stability when
  the dataset permits it;
- spatial overlap and rank correlation for seed maps;
- agreement and rank correlation for ROI matrices;
- second-level effect estimates and uncertainty;
- sensitivity of conclusions to parameter changes;
- technical failures, runtime, storage, and reproducibility completeness.

Spatial or statistical concordance is evaluated only where the estimand, sample,
atlas, and multiplicity family are comparable.

## Leakage control

Freeze selector, expert, and paper-specific choices before inspecting benchmark
results. Separate people who curate evidence from those who adjudicate outcomes
where feasible. Version every corpus, code revision, dataset snapshot, sample,
and analysis plan. Register any allowed deviations and label post-hoc analyses.

## Minimum success criteria

Before execution, define quantitative thresholds for traceability completeness,
expert-rated defensibility, reproducibility, technical completion, and tolerated
instability. A credible success statement should require:

- complete provenance for every executable choice;
- no fabricated value when a source is silent;
- no material contract or metadata incompatibility;
- performance within the prespecified range of blinded expert pipelines;
- conclusions that are not uniquely dependent on an unexplained selector choice;
- transparent reporting of all non-comparable parameters and failed arms.

## Current evidence level

The [12 October engineering validation](../validation/parameter-selector-2026-10-12.md)
documents the MCP, persistence, migration, interruption and export checks. These
are a prerequisite for, rather than a substitute for, the scientific benchmark.

The resolver's `context-and-strict-normalization-v2.1` revision now exposes
per-observation eligibility, contextual differences, missing appraisal dimensions
and frozen decision audits through the existing MCP operations. Regression tests
check ambiguous units/ranges, Nyquist rejection, explicit versus inferred support,
context changes, citation tampering and persistence. These are engineering
checks, not blinded expert ratings or downstream performance validation. The
revision has not been shown to improve scientific outcomes over the October
benchmark choices; that still requires the comparator arms above.

The existing six-run validation contributes one selector arm and one reserved
expert comparison. The shared baseline matched for all comparable parameters;
slice-timing policy and different seed questions were explicitly non-comparable.
Because alternatives were not run as frozen arms, the present result supports
auditability and concordance, not superiority, optimization, or universal
scientific validity.
