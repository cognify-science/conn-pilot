# Subject-level QC review manual

CONN Pilot exposes evidence for review but does not make autonomous participant
inclusion decisions. The labels `accept`, `exclude`, and `needs_review` are
append-only investigator decisions tied to a result version. This manual defines
a reproducible review order and a minimum rationale standard.

## Review order

Review each participant in the following order. A problem observed at an early
stage can explain a later metric, but no single panel should be judged in
isolation.

1. **Acquisition and completeness.** Confirm the expected anatomical and
   functional series, number of volumes, and relevant BIDS metadata.
2. **Realignment and ART.** Inspect motion traces, outlier distribution, retained
   volumes, and the longest contiguous outlier sequence.
3. **Registration.** Check functional-to-structural alignment at cortical,
   ventricular, and boundary landmarks.
4. **Normalization.** Check coverage and alignment in MNI space, especially
   frontal, temporal, cerebellar, and inferior regions vulnerable to dropout.
5. **Segmentation.** Inspect gray matter, white matter, and CSF separation for
   gross leakage or failed anatomy.
6. **Denoising.** Compare distributions before and after denoising and look for
   remaining structured motion or global artifacts.
7. **Temporal summaries.** Review tSNR and DVARS when measured. Treat missing or
   unavailable values as missing, never as zero-quality evidence.
8. **Cross-branch consistency.** When seed-to-voxel and ROI-to-ROI use the same
   preprocessed sample, reconcile their QC decisions.

## Evidence exposed by the system

Depending on the result, the QC record may include CONN QA panels for
registration, normalization, segmentation, ART/outliers, and denoising, plus:

- total and outlier volume counts;
- percentage and number of retained volumes;
- longest contiguous outlier run;
- maximum global-signal z score;
- maximum and mean motion;
- median tSNR;
- mean and maximum DVARS;
- processing warnings and missing evidence.

The metrics summarize different failure modes. Their scales depend on sequence,
TR, voxel size, scan duration, population, preprocessing, and implementation.
The product deliberately has no universal rule such as “exclude whenever one
number exceeds X.” ART thresholds are prospective nuisance-model parameters,
not complete participant-level scientific criteria.

## Metric definitions and current export limitations

The adapter exports tSNR as voxelwise temporal mean divided by temporal sample
standard deviation, summarized by the median of finite values. Its mask is the
finite nonzero voxels of the first preprocessed volume. DVARS is the root mean
square intensity difference between consecutive volumes in that mask; the
export reports its mean and maximum. These are preprocessed-image summaries,
not guaranteed post-denoising or standardized DVARS measures.

The new availability-aware exporter requires an unambiguous `swa*.nii` file for
these image summaries. A missing or different filename produces `null` with
`metric_availability=false`, rather than a zero placeholder. Verified ART
measurements likewise carry availability and original-file hashes. Legacy
numeric fields without availability are treated as unverified, including
positive values, until the original evidence is reread.

The updated ART audit computes `longest_outlier_streak` from flagged **volume
rows** in acquisition order. Older exports used regressor columns and cannot
establish temporal adjacency. The October benchmark decisions remain historical:
inspect original ART traces or run a separate retrospective audit before using
their legacy metrics. See [automatic scientific audit](scientific-audit.md) for
checks, version binding and unsupported cases.

The parameter named `outlier_fd_threshold_mm` is passed to CONN's second ART
threshold. Its ART displacement semantics must be checked against the toolbox
version; it must not be assumed interchangeable with every published definition
of framewise displacement. Similarly, `motion_max_mm` and `motion_mean_mm`
summarize ART's second time-series column rather than independently recomputing
a named FD formula.

## Decision rubric

### Accept

Use `accept` when the available evidence is complete enough for the stated
analysis and no observed issue is expected to make the participant scientifically
unusable. Record any residual limitation that should influence interpretation.

Example rationale: “Registration and normalization are anatomically plausible;
outliers are sparse rather than contiguous; sufficient volumes remain; no
structured artifact persists after denoising.”

### Needs review

Use `needs_review` when evidence is missing, ambiguous, discordant across panels,
or requires a second reviewer or domain-specific judgment. This is not an
exclusion and should not be converted automatically into one.

Example rationale: “Temporal-lobe coverage is borderline and DVARS remains high;
request independent review before changing the analysis sample.”

### Exclude

Use `exclude` only when combined evidence supports a concrete failure relevant
to the planned analysis. The system requires a rationale. Prefer observable
descriptions over generic labels.

Example rationale: “A long contiguous artifact interval removes most usable
resting-state data and the same interval leaves structured residuals after
denoising; the participant is unsuitable for this connectivity estimate.”

## Decisions the reviewer should avoid

- Excluding a participant because one metric is an outlier without inspecting
  the images and time series.
- Changing thresholds after viewing group results in order to improve a p-value.
- Treating a successful CONN job as acceptable QC.
- Treating a visually attractive connectivity map as evidence of good
  registration or denoising.
- Interpreting a missing exported metric as a measured zero.
- Applying different samples to paired benchmark branches without documenting
  why comparability was intentionally broken.

## After the sample changes

Any accepted-sample change makes the old second-level result stale. Preserve the
old result, request a second-level recalculation, and verify the new participant
count, group counts, design dimensions, rank, residual degrees of freedom,
sample version, and output version. Do not carry a scientific decision from the
old version to the new one automatically.

## Minimal audit record

For every participant, retain the result version, evidence reviewed, decision,
rationale, reviewer identity, and timestamp. For the final group result, retain
the included participant count, group counts, unresolved `needs_review` cases,
missing QC fields, model version, and any sensitivity analysis. The
[data-governance guide](data-governance.md) explains which participant-level
records belong in controlled storage rather than this public repository.
