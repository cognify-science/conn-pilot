# Parameter selection

CONN Pilot does not let CONN Toolbox, the server, or a language model silently
choose the scientific parameters of a study. It implements a constrained decision
process around seven executable parameters:

- spatial smoothing FWHM;
- ART framewise-displacement threshold;
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
3. queries the frozen evidence corpus by topic and context;
4. returns reported options with evidence identifiers and reporting status;
5. rejects options outside the executable contract or incompatible with known
   metadata;
6. requires a selected value, rationale, and exact matching evidence identifiers;
7. stores the corpus version and a snapshot of the evidence shown at decision time.

The language model explains and compares the returned records. The deterministic
resolver decides only whether the proposed value is represented by the cited
evidence and allowed by the executable contract.

## What the evidence means

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
