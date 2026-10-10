# Statistical methods implemented by CONN Pilot

This page describes the current executable statistical contract. It is intended
to let a methodologist distinguish what the software actually computes from what
an AI assistant may explain, what a paper reported, and what an investigator
ultimately concludes.

The authoritative machine-readable definitions are the selected pipeline in
`catalog/pipelines/`, its referenced stages in `catalog/stages/`, the frozen
project and execution plan, and the generated MATLAB batch hash. This page is a
human-readable account of those definitions.

## Supported observations and designs

The research preview accepts one resting-state session per participant from a
registered BIDS dataset. Its supported analysis families are:

- seed-to-voxel connectivity;
- ROI-to-ROI connectivity.

The second level supports a one-sample model or two independent groups, with
optional numeric between-subject covariates. Every group membership, covariate
value, contrast, contrast direction, and rationale must be supplied explicitly.
Longitudinal, repeated-measures, task-modulated, dynamic-connectivity, graph,
multivariate, predictive, and arbitrary MATLAB analyses are outside this
executable contract.

## Spatial preprocessing

The `default_mni` pipeline follows the CONN default volume-based MNI workflow.
It centers the functional and structural images, realigns and unwarps the
functional series, detects ART outliers, performs affine functional-to-structural
coregistration, segments and normalizes functional and structural data to MNI
space, and smooths the functional data with the recorded FWHM.

Slice-time correction is included only when a valid slice order is available.
If the BIDS preflight establishes that `SliceTiming` is absent, the investigator
may explicitly authorize a versioned branch that omits slice-time correction.
The system does not infer a slice order. The exact branch and preflight decision
are stored in the execution plan.

The implementation can be compared with the official
[CONN preprocessing pipeline](https://web.conn-toolbox.org/fmri-methods/preprocessing-pipeline)
and the versioned stage catalog. Official documentation explains CONN behavior;
the generated plan records which behavior was requested for a particular run.

## Denoising model

The denoising stage regresses the following nuisance sets:

- white-matter aCompCor components;
- CSF aCompCor components;
- the CONN `realignment` confound with a requested dimension of 12 and
  first-derivative expansion (`deriv=1`);
- all ART scrubbing regressors.

The numbers of white-matter and CSF components, temporal band, detrending order,
despiking policy, and global-signal-regression policy are frozen project
parameters. The benchmark baseline used five white-matter components, five CSF
components, a 0.008-0.09 Hz band, linear detrending, no despiking, and no global
signal regression. Those values describe the benchmark, not a universal default.

The realignment setting is specified at the CONN field level. The final number
of nuisance columns depends on the available realignment covariate and CONN's
expansion rules; it must be checked in the saved project. It should not be
described unconditionally as either a 12- or 24-column model.

Filtering and nuisance regression are configured in the same CONN denoising
stage. See the official [CONN denoising pipeline](https://web.conn-toolbox.org/fmri-methods/denoising-pipeline)
for the toolbox semantics. ART thresholds define candidate outlier volumes for
scrubbing and QC; they do not automatically exclude a participant.

## First-level connectivity

For seed-to-voxel analysis, CONN computes the bivariate Pearson correlation
between the selected seed time series and each voxel time series after denoising.
For ROI-to-ROI analysis, it computes bivariate correlations among the selected
ROI time series. The project uses CONN analysis measure `1` and analysis type `2`
for seed-to-voxel or type `1` for ROI-to-ROI.

Correlations are represented for group analysis with the Fisher transform

```text
z = atanh(r) = 0.5 * ln((1 + r) / (1 - r)).
```

The rest condition spans the full acquisition (`onset=0`, `duration=Inf`). The
adapter does not explicitly assign `Analysis.weight` or `Analysis.modulation`;
the documented CONN defaults are HRF within-condition weighting and standard
connectivity analysis. This is a toolbox-default dependency, not an explicit
unweighted-correlation setting. The official CONN descriptions of
[seed-based connectivity](https://web.conn-toolbox.org/fmri-methods/connectivity-measures/seed-based)
and [ROI-to-ROI connectivity](https://web.conn-toolbox.org/fmri-methods/connectivity-measures/roi-to-roi)
provide the toolbox context.

The [CONN batch reference](https://web.conn-toolbox.org/resources/conn-manual/conn_batch)
defines these fields. For exact computational reproduction, inspect the saved
CONN project as well as the generated batch. ROI extraction dataset, analysis
mask/resolution, and other unassigned CONN options also inherit toolbox defaults.
The current release does not capture every implicit option as a separate
CONN Pilot parameter decision; software-version pinning is therefore necessary.

## Second-level general linear model

For each voxel or ROI connection, the second level is represented as

```text
Y = X beta + epsilon,
```

where `Y` contains participant-level Fisher-z estimates, `X` contains the named
between-subject effects, `beta` contains their coefficients, and `epsilon` is the
residual. A contrast vector `c` tests a specified linear combination `c' beta`.

The project records named effects and weights rather than relying on column
position alone. A one-sample model uses `AllSubjects`. A two-group model uses
explicit binary group effects; optional covariates add explicitly named numeric
columns. Before a post-QC recalculation, CONN Pilot requires at least two retained
participants, nonempty requested groups, consistent participant vectors, and a
current sample version. Execution-unique aliases prevent an older CONN covariate
from being selected accidentally.

The October benchmark review independently checked the actual participant count,
design dimensions, rank, and residual degrees of freedom. The current automatic
completion gate checks expected model files, but does not yet enforce those
matrix properties as success invariants. A reviewer must inspect them before
scientific acceptance. The intended
statistical framework is the SPM general linear model described in the
[SPM group-analysis guidance](https://www.fil.ion.ucl.ac.uk/spm/docs/wikibooks/Group_Analysis/).

## Thresholds and multiplicity

The project hypothesis must state its target contrast, expected direction,
decision rule, and multiplicity method. CONN Pilot preserves the inferential
artifacts and can evaluate version-matched evidence against that rule. It does
not reinterpret an uncorrected peak as a corrected finding, choose a threshold
after seeing results, or treat the display threshold in a viewer as the study's
decision rule.

Whole-brain voxelwise inference, a finite set of predefined coordinates, and a
finite set of ROI connections create different multiplicity families. The
researcher must define the family that matches the prospective question. The
October 2026 benchmark used Bonferroni correction for four predefined WU120
coordinates and reported FDR and whole-volume Bonferroni checks for exploratory
clinical seed maps.

## Assumptions and interpretation limits

The implemented model assumes that the design and contrast are correctly
specified, observations at the group level are independent for the supported
designs, and the residual model is suitable for the requested inference. Motion,
registration error, temporal artifacts, small samples, imbalance, missing data,
atlas choice, seed definition, preprocessing choices, and residual confounding
can all affect estimates.

A small p-value does not measure effect importance, replication probability, or
hypothesis truth. A non-significant result does not establish equivalence or
absence. The quality report therefore evaluates technical completion, QC,
sample-version consistency, inferential evidence, and scientific interpretation
as separate layers.

## Auditing one executed analysis

To reconstruct an analysis, inspect in this order:

1. project specification and prospective hypothesis;
2. pipeline and stage versions;
3. dataset inventory and acquisition preflight;
4. parameter-decision records and evidence snapshots;
5. generated execution plan and MATLAB batch hash;
6. technical result and artifact manifest;
7. participant QC evidence and decisions;
8. active sample and second-level model version;
9. statistical artifacts and multiplicity rule;
10. quality report and investigator decision.

The [MCP tool reference](../reference/mcp-tools.md) maps those questions to the
read-only calls available to an authenticated researcher.
