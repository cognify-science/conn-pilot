# Worked example: WU120 PCC connectivity

This example follows the completed WU120 benchmark from a prospective question
to an auditable scientific statement. It illustrates the workflow; authenticated
runtime calls remain identity-scoped, and internal project and job identifiers
are intentionally omitted.

## 1. Prospective question

The registered subset contains 15 healthy control participants from OpenNeuro
`ds000243`. Before inspecting results, the evaluation asked whether a PCC seed
would show positive connectivity at four predefined default-mode coordinates and
whether PCC-MPFC ROI connectivity would be positive.

This was a functional positive control. It was not a direct replication of the
source papers' primary motion-method questions.

## 2. Discovery and design

The assistant used read-only discovery to confirm:

- dataset `evaluation_wu120_15` was visible and inspectable;
- seed-to-voxel and ROI-to-ROI pipeline versions were available;
- the CONN atlas contained `networks.DefaultMode.PCC (1,-61,38)` and
  `networks.DefaultMode.MPFC (1,55,-3)`;
- the design was a one-sample model with `AllSubjects`;
- the worker and object storage were ready.

The project recorded its contrast, positive expected direction, four-coordinate
multiplicity family for the seed analysis, and sample limitation before
submission.

## 3. Frozen method

The protocol fixed the CONN default MNI branch, 8 mm smoothing, ART displacement
0.5 mm, ART global-signal z 3, five white-matter and five CSF aCompCor
components, a 0.008-0.09 Hz band, linear detrending, no despiking, and no global
signal regression. Slice-time correction could be omitted only because preflight
confirmed missing `SliceTiming` and the omission was explicitly authorized.

Each parameter decision preserved its selected value, investigator rationale,
evidence identifiers, evidence-corpus version, and the evidence snapshot shown
at decision time. The full frozen protocol is identified by SHA-256
`A11BF21719D32152442416F3FF2D9B0A362170EB780AAC5D0D0CD647FF6951AE`.

## 4. Validation and execution

Before submission, `validate_project` and `generate_execution_plan` established
that the dataset, design, seeds, parameters, software compatibility, and
preflight decisions formed an executable contract. Submission created one
durable remote job. Local MATLAB attempts were replaceable, so infrastructure
recovery did not change the scientific identity of the analysis.

Monitoring separated supervisor heartbeat, live MATLAB activity, durable stage
milestones, and terminal technical state. Calendar time included interruptions
and retries and therefore was not used as a pure compute benchmark.

## 5. QC and current sample

All 15 participants were reviewed using ART, registration, normalization,
segmentation, denoising, and motion evidence. Some scans required closer motion
inspection, but the combined evidence did not justify exclusion. The final
sample remained 15, and no automated rule made that decision.

WU120 tSNR and DVARS were exported as zero in the initial summary. The review
treated those fields as unavailable rather than as measured zero values.

## 6. Statistical result

The seed-to-voxel analysis produced positive Fisher-z estimates at all four
prospectively specified coordinates:

| Region | MNI | Fisher z | t(14) | Two-sided p |
| --- | --- | ---: | ---: | ---: |
| PCC | `[1,-61,38]` | 0.9566 | 17.600 | 6.04 x 10^-11 |
| MPFC | `[1,55,-3]` | 0.2928 | 4.888 | 2.40 x 10^-4 |
| Left lateral parietal | `[-39,-77,33]` | 0.2636 | 4.068 | 1.15 x 10^-3 |
| Right lateral parietal | `[47,-67,29]` | 0.2899 | 4.590 | 4.21 x 10^-4 |

All four survived Bonferroni correction for the four predefined coordinates.
PCC-MPFC ROI-to-ROI connectivity was also positive: Fisher `z=0.3338`,
`t(14)=6.139`, two-sided `p=2.57 x 10^-5`.

## 7. Scientific statement

The correct conclusion is: **the final, reviewed WU120 subset produced evidence
compatible with the predefined PCC/default-mode functional positive control
under the recorded decision rules.**

It would be incorrect to say that technical completion proved the hypothesis,
that significance validated every preprocessing choice, or that this analysis
replicated the source papers' principal scientific claims.

## 8. Reproducibility record

The final seed-to-voxel and ROI-to-ROI packages have SHA-256 values recorded in
the [benchmark report](benchmark-validation-2026-10.md). The controlled packages
contain project, method, evidence, QC, sample and result versions, artifacts, and
manifests. Raw neuroimages and participant-level controlled records are not
published in this repository.

## A safe conversational sequence

A researcher can ask an MCP-capable assistant:

1. “Show the visible datasets, pipelines, seeds, and system health. Do not create
   anything.”
2. “Explain the one-sample PCC seed-to-voxel design and its unsupported cases.”
3. “Create the project only after showing the exact contrast and prospective
   hypothesis.”
4. “For each unresolved parameter, show the allowed values, evidence records,
   reporting status, and dataset applicability.”
5. “Validate the complete project and show the frozen execution plan.”
6. “Submit once, then monitor the existing job without duplicating it.”
7. “Show subject QC evidence; do not record a decision until I state one.”
8. “Show the current sample, model version, multiplicity rule, statistics, and
   quality report separately.”
9. “Generate the reproducibility package for the current result version.”

The [MCP tool reference](../reference/mcp-tools.md) lists the corresponding tool
names and mutation boundaries.
