# Internal validation record

The initial sandbox validation used three participants and exercised execution,
QC, sample changes, and reporting. It was followed by the October 2026 six-run
public benchmark evaluation. The latter is documented in the
[public scientific report](science/benchmark-validation-2026-10.md) and its
[machine-readable aggregate record](science/data/benchmark-results-2026-10.json).

## Implementation checks

The automated suite covers project and contrast validation, supported pipeline
contracts, typed graph invalidation, evidence matching, identity isolation,
subject decisions, stale second-level blocking, reporting, worker recovery, and
artifact publication. The 111-test checkpoint preceding the documentation
completion passed. Current GitHub CI is authoritative for each published commit.

## Real toolbox checks

MATLAB R2023b, SPM25, and CONN 25.b produced real seed-to-voxel and ROI-to-ROI
outputs, native QA images, ART summaries, and group models. The initial remote
seed run completed in 52 min 42 s and registered 36 selected artifacts, including
21 QC images. The historical ROI run completed in 29 min 45.8 s and registered
28 initial artifacts. These small runs established executable wiring.

The three-participant ROI test retained two participants after explicit QC
review, recalculated the second level in a new version, and exported a 36-file
package. Inference remained not evaluable for a scientific population claim.
See the [historical record](validation/roi-to-roi-2026-10-03.md).

## Full benchmark validation

Six full analyses completed technically over WU120, fibromyalgia, and UCLA CNP.
The evaluation reviewed 55 unique participants. Final samples were 15, 9+9, and
8+8 respectively. The corrected clinical models were independently inspected for
participant counts, design dimensions, rank, and residual degrees of freedom.
All six final reproducibility package hashes are public in the benchmark report.

A covariate-name reuse bug in the CONN Pilot second-level generator was corrected
before final clinical interpretation. Older apparent-success calculations were
superseded. This was a generator issue; it does not establish a defect in CONN
Toolbox. The current implementation still requires reviewer inspection of the
actual model rather than relying solely on a successful MATLAB exit.

## Interpretation boundary

The evidence establishes a traceable supported workflow and recovery on the
validated worker setup. WU120 recovered the functional positive control. Small
clinical subsets produced no corrected support for the restricted PCC questions.
Internal validation does not establish general scientific validity, adequate
clinical power, or autonomous source-paper replication.
