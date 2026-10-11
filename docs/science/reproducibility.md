# Reproducibility outputs

Each run preserves enough information to distinguish the requested experiment,
the generated execution plan, the local attempt, and the reviewed result.

## Versioned records

- project specification and research question;
- pipeline and stage versions;
- dataset inventory without local paths;
- acquisition preflight decisions;
- selected parameter values, rationales, evidence IDs, and corpus snapshots;
- generated MATLAB batch hash;
- CONN/SPM/MATLAB compatibility metadata;
- job events, attempt count, and result version;
- artifact identities and content hashes;
- subject QC evidence and append-only decisions;
- sample version and second-level model version;
- experiment-quality report and scientific decision.

## Reproducibility package

`generate_reproducibility_package` produces a versioned archive containing JSON,
HTML, and PDF reports; methods; parameter provenance; literature identifiers;
QC evidence; current statistical artifacts; and a file manifest with hashes.

New packages also include `scientific-audit.json` and `statistical-results.json`,
with verified model evidence, explicit testing families and correction scope,
availability-aware QC, pending items, and current output-version binding.
See [automatic scientific audit](scientific-audit.md) for extraction limits and
read-only auditing of historical results.

The package captures what CONN Pilot did and what the researcher decided. It does
not bundle raw neuroimages, replace the original BIDS dataset, or guarantee that
licensed external software and atlas resources may be redistributed.

## Recovery and repeatability

The remote job is a durable intent. Local MATLAB executions are replaceable
attempts. Internet loss can delay synchronization while MATLAB continues. After a
power loss, the supervisor may start a clean attempt for the same remote job ID.
Artifact registration is content-addressed so result publication can be repeated
without creating conflicting identities.

## Independent reproduction checklist

A scientist reproducing an analysis should obtain the controlled package and
dataset-selection manifest through the authorized export process, then verify:

1. the exact source dataset snapshot, file selection, and source hashes;
2. pipeline, stage, corpus, software, and code versions;
3. prospective hypothesis, design, seed definitions, and multiplicity family;
4. parameter values, rationales, evidence observations, and acquisition decisions;
5. generated batch and inherited CONN defaults in the saved project;
6. artifact hashes against the package manifest;
7. QC decisions and the ordered final sample;
8. actual design matrix, rank, contrast dimensions, and residual degrees of freedom;
9. current result, sample, and second-level output versions;
10. effect estimates, inferential method, corrections, and interpretation limits.

The public benchmark JSON is an aggregate result summary. It is not sufficient
by itself to rerun the exact participant subset. Exact participant manifests and
selected derived data remain controlled as described in
[data governance](data-governance.md).

Large artifacts can be omitted by export size policy. The October seed-to-voxel
packages omitted `spmT_0001.nii`; those maps were preserved in the controlled
evaluation archive. An independent audit must retrieve needed omitted artifacts
separately and verify their hashes. A package checksum confirms file identity,
not numerical correctness or scientific validity.
