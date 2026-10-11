# Parameter selection

CONN Pilot does not let CONN Toolbox, the server, or a language model silently
choose the scientific parameters of a study. It implements a constrained decision
process around seven executable parameters:

- spatial smoothing FWHM;
- ART displacement threshold (motion-metric equivalence requires review);
- ART global-signal z threshold;
- white-matter aCompCor component count;
- CSF aCompCor component count;
- temporal band-pass filter;
- global-signal regression policy.

## Selection process

For each unresolved parameter, the resolver:

1. reads the allowed type, range, implemented values, and target CONN field from
   the selected pipeline version;
2. reads relevant dataset context, including TR and acquisition metadata;
3. reads the frozen evidence corpus by topic and annotates the available context;
4. returns reported options with evidence identifiers and reporting status;
5. rejects options outside the executable contract or incompatible with known
   metadata;
6. requires a selected value, rationale, and exact matching evidence identifiers;
7. stores the corpus version and a snapshot of the evidence interpreted at decision time.

The language model explains and compares the returned records. The deterministic
resolver decides only whether the proposed value is represented by the cited
evidence and allowed by the executable contract.

## What the evidence means

The deterministic resolver revision `context-and-strict-normalization-v2` adds
the assessment below. It improves the audit of a choice; it does not implement
an optimizer or silently change investigator-confirmed parameters.

### What the AI receives for each option

`get_project_parameter_guidance` returns executable `options` together with
`evidence_assessments` for **all mapped observations**, including inferred,
unreported, unparsed, and incompatible records. The option limit truncates only
the option list; `options_truncated` identifies this and the assessment list
retains the complete mapped evidence. `reporting_summary` counts observations,
not independent studies or evidence strength. Each option supplies separate
paper and observation counts and a descriptive context-alignment summary.

| Field | Meaning and limitation |
| --- | --- |
| `reported_value`, `normalized_value` | Preserve the original wording and the unambiguous executable interpretation, if one exists. |
| `executable_candidate` | Explicit evidence with a parsable value that passes the parameter contract and known TR/Nyquist check. This does not certify scientific applicability. |
| `exclusion_reason`, `compatibility_errors` | Explain why an observation is not offered as an executable option. |
| `context_alignment` | Compare the reviewed paper's primary analysis family and modality label with the project's supported workflow. Values are `matching`, `different`, or `unknown`. |
| `study_design` | Preserve both descriptions but leave equivalence unassessed: the corpus's design labels and the executable design vocabulary are not interchangeable. |
| `unassessed_dimensions` | Population, acquisition TR, voxel resolution, motion-metric definition, source role, and risk of bias are not sufficiently curated for automated comparison. |
| `scientific_applicability` | Remains `requires_review`, including for matching metadata. |

Different family or modality labels remain visible and do not automatically
discard shared preprocessing observations. A methodological QC paper can inform
another analysis family. Matching labels likewise do not establish applicability
to a new population or acquisition. The resolver never infers a study population
or a source's methodological role from its title.

Numeric text must describe one value in the expected units, or one Hz interval
for the temporal band. For example, `6–8 mm`, `0.5 cm`, contradictory bands, and
component counts qualified by additional derivatives do not become a guessed
scalar. Negative signs are preserved for contract validation; NaN and infinity
are rejected. The ART displacement threshold still needs review of the motion
metric's actual definition: a matching number in mm does not prove equivalence
between translation, FD variants, and CONN/ART displacement settings.

Options retain their legacy descriptive frequency order, explicitly labeled
`option_order`; no rank is a quality score. Inspect citations, contextual
differences, unresolved source items and missing dimensions before explaining
alternatives to the investigator.

### Frozen choice audit and review after context changes

`resolve_project_parameter` requires an explicit cited match and an investigator
rationale. It saves a `selection_audit` atomically with the parameter record and
method decision. `list_method_decisions` and the execution plan expose it, and
the method-decision reproducibility export retains it. Its contents include:

- resolver revision, selected value, parameter path and corpus version/hash;
- pipeline-contract hash and decision-time experiment context, including TR,
  analysis family, research question, seeds, design hash and dataset fingerprint;
- the full candidate/assessment snapshot reconstructed at decision time;
- cited explicit matches and separately labeled cited alternative values;
- hashes of the cited evidence snapshot and the audit contents.

A cited alternative is a different *reported value*, not a finding that the
sources scientifically contradict each other. The snapshot is generated at
resolution time; it does not attest to which earlier guidance response the AI
or investigator actually viewed. It preserves the server's candidate set and
source interpretation at the moment the choice was recorded.

Resolution checks detect altered citation contents or audit records. Changes to
the recorded dataset fingerprint, TR, research question, seeds, design, workflow
scope or executable contract mark an audited decision unresolved and require a
fresh documented choice before a new validation/submission. Existing completed
results are not modified or rerun. Updating the literature corpus alone does
not rewrite or invalidate a frozen historical choice.

Older decisions remain readable and retain their previous provenance checks,
with `selection_audit_status=legacy_unavailable`. They are not retroactively
credited with this new audit. A hash establishes content consistency, not the
truth of a paper extraction or the scientific adequacy of a rationale.

### Reporting status and scientific interpretation

The corpus distinguishes:

- `explicit`: the paper directly reports the value;
- `inferred`: a reviewer inferred it from incomplete reporting;
- `not_reported`: the source does not supply the value.

Frequency means only “reported in this corpus.” It does not establish efficacy,
optimality, or applicability to a new acquisition, population, or hypothesis.
Official software documentation, methodological studies, systematic reviews,
application papers, and internal validation have different evidentiary roles.

## Exact citations for an executed project

Use `list_method_decisions(project_id)` to retrieve the selected value,
investigator rationale, evidence IDs, corpus version, and stored evidence snapshot.
Use `get_evidence_record(pmid)` for the normalized source record. This answers
which papers informed a particular decision; it is more precise than asking which
papers “CONN selected,” because CONN Toolbox itself does not run this selector.

## Current scientific limitation

The corpus contains 138 indexed papers and 45 structurally reviewed pipeline
instances. Structural review confirms how methods were organized; it is not a
complete parameter-level risk-of-bias or applicability appraisal. The remaining
uncertainty is surfaced to the client and retained in reproducibility outputs.
