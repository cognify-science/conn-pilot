# Scientific report template

Use this template to produce a report that another scientist can audit. Fill
each field from the current project, evidence, result, and controlled package.
Write `not available` or `not applicable` with a reason when a field cannot be
supplied. Never invent a value or copy a decision from a stale model.

## Study identity and prospective question

- Software release and code revision:
- Pipeline/stage versions:
- Dataset accession, exact snapshot, registration, and retrieval manifest:
- Population, inclusion rules, and scientific estimand:
- Prospective hypothesis and target contrast:
- Expected direction and decision rule:
- Multiplicity family and method:
- Sample-size, power, precision, or feasibility argument:
- Deviations from the prospective plan and when they were decided:

## Acquisition and methods

- TR, functional duration/volume count, voxel resolution, and session/run selection:
- Structural and functional modalities:
- Slice-timing metadata and preflight decision:
- Exact seed/ROI names, atlas versions, and extraction settings:
- Spatial preprocessing branch and smoothing FWHM:
- ART thresholds and displacement definition:
- WM/CSF component counts and actual nuisance design:
- Filter, detrending, despiking, and GSR policy:
- Connectivity measure and within-condition weighting:
- Group membership, covariate definitions, transformations, and centering:
- Effect names, contrast weights, and between-source testing:
- Inherited toolbox defaults checked in the saved CONN project:
- MATLAB, SPM, CONN, and relevant atlas versions:
- Parameter provenance: values, rationales, evidence IDs, and corpus version:

## Execution and technical completion

- Attempts and reason for any replacement attempt:
- Calendar duration and compute duration, distinguished where measurable:
- Expected and registered artifact classes:
- Technical warnings, omitted artifacts, and missing metrics:
- Execution-plan and batch identities:
- Content hashes and publication state:

## QC and final sample

- Review rubric, evidence inspected, and reviewer attribution:
- Initial participant and group counts:
- Accepted/excluded/unresolved counts and reasons:
- Missing or unreliable QC summaries and their treatment:
- Residual motion, coverage, registration, or denoising limitations:
- Paired-branch sample consistency:
- Final sample version and controlled inclusion manifest:
- Post-QC recalculation identity and output version:
- Actual participant count, matrix dimensions, rank, contrast shape, and residual df:
- Sensitivity analysis for exclusions or borderline scans:

## Statistical evidence

- Effect estimate with units and direction:
- Confidence interval and level, if available:
- Test statistic, degrees of freedom, and raw p-value:
- Adjusted p-value/q-value and exact correction family:
- Prespecified target versus post-hoc peak or exploratory observation:
- Result and sample versions associated with every statistic:
- Null, equivalence, or absence claims justified by the actual design:

## Scientific interpretation

- Technical completion:
- Subject quality:
- Sample/model currency:
- Inferential evidence:
- Compatibility with the prospective hypothesis:
- Investigator conclusion and rationale:
- Source-paper comparison: matching versus different estimands, samples, and methods:
- Generalizability, residual confounding, uncertainty, and unresolved questions:

## Reproducibility and citation

- Package SHA-256 and manifest verification:
- Controlled artifacts needed in addition to the public repository:
- Source data, CONN, SPM, MATLAB, atlas, and CONN Pilot citations:
- Authorized access procedure and data-use conditions:

The completed [October benchmark report](benchmark-validation-2026-10.md)
illustrates aggregate reporting. The [reproducibility checklist](reproducibility.md)
defines the additional material required for exact independent reproduction.
