# Evidence governance

The literature layer is a versioned decision aid. It is not a general search
engine, an autonomous systematic review, or an authority that can choose a
method without a researcher. This page defines how evidence enters the corpus,
how it may be used, and how a scientist can audit a recommendation.

## Corpus states

The current repository contains 138 deduplicated indexed papers and 45
structurally reviewed pipeline instances. These numbers describe different
levels of curation:

- **Indexed:** bibliographic identity and source hash are present.
- **Normalized:** inherited or new extraction has been mapped to the taxonomy.
- **Structurally reviewed:** a reviewer checked how the pipeline components were
  organized in the source.
- **Parameter-appraised:** a reported value, its context, and its applicability
  have been checked closely enough to inform an executable decision.

The 45-paper review is not a full risk-of-bias appraisal of all 138 papers.
Unreviewed inherited extraction can reveal a gap or candidate source but cannot
silently become executable guidance.

## Observation status

Every parameter observation distinguishes:

- `explicit`: the source directly reports the value;
- `inferred`: a reviewer derived the value from incomplete or indirect text;
- `not_reported`: the source does not provide a usable value.

Only `explicit` means that the cited source itself supplies the value. Inference
must remain labeled. Absence of reporting must never be converted to a default.

## Source roles

Evidence is evaluated according to the question it can answer:

| Source | Appropriate question |
| --- | --- |
| CONN or SPM documentation | What does a field or algorithm mean in that software version? |
| Consensus or methodological comparison | What consequences, tradeoffs, or selection criteria have been studied? |
| Systematic review | How common is a practice and where does the field disagree? |
| Application paper | Has a value been used in a sufficiently similar acquisition, population, or question? |
| Dataset descriptor | What was acquired and what limitations or labels accompany the public data? |
| Internal validation | Can this exact implementation and software combination execute reproducibly? |

No class substitutes for another. A popular application value does not prove
optimality, and successful internal execution does not establish external
scientific validity.

## Admission workflow

This is the required governance procedure for future corpus releases. The
current software loads and validates a frozen snapshot; it does not implement
an automatic literature-update or methodological-adjudication service.

A new record becomes actionable only after:

1. identifier and version resolution;
2. deduplication and source hashing;
3. structured extraction under the current taxonomy;
4. separation of explicit, inferred, and unreported fields;
5. review of acquisition, population, pipeline, and analysis context;
6. discrepancy and limitation recording;
7. automated corpus validation;
8. publication in a new immutable corpus snapshot.

Web search may find candidates but never mutates the frozen snapshot used by an
existing project. Full copyrighted papers are not redistributed. Bibliographic
identifiers, structured observations, hashes, and review notes are retained.

## Applicability review

When comparing an option with a new project, inspect at least:

- data type and analysis family;
- population and study question;
- TR, acquisition length, spatial resolution, and slice metadata;
- preprocessing order and software version;
- nuisance model and temporal filtering;
- seed or atlas definition;
- first- and second-level design;
- sample size and multiplicity family;
- reporting completeness and known risk of bias.

“Used in resting-state fMRI” is not sufficient context by itself. A method can be
executable yet poorly matched to the acquisition or estimand.

## Resolving disagreement

The resolver returns the allowed options and their evidence; it does not erase
conflict. When sources disagree, the assistant should state the competing
rationales, source roles, contexts, and missing comparability information. The
investigator records a value and rationale. The deterministic validator checks
that the value is executable and that the cited observations actually support
the recorded claim.

Corpus frequency is reported descriptively. It is never used as a vote. CONN
defaults are a comparator, not an automatic gold standard. A project-specific
decision may reasonably differ from both when the rationale and evidence are
explicit.

## Project-level audit trail

For an executed project, `list_method_decisions(project_id)` returns the exact
value, rationale, evidence identifiers, corpus version, observation status, and
stored evidence snapshot. `get_evidence_record(pmid)` exposes the normalized
record. This makes the answer to “which papers informed this choice?”
project-specific and reproducible.

An auditor should verify that:

- every unresolved parameter received an explicit decision;
- every cited evidence ID existed in the stored snapshot;
- the observation status supports the language used in the rationale;
- the value was permitted by the selected pipeline version;
- dataset metadata relevant to the choice were known;
- alternatives and uncertainty were not suppressed;
- the executed plan contains the same value as the decision record.

## Known limitations

The corpus is intentionally narrower than the connectivity literature. It does
not support autonomous meta-analysis, causal grading, universal best-practice
ranking, or claims that one parameter set is optimal. Parameter-level risk of
bias and applicability appraisal remain incomplete. The
[selector evaluation protocol](parameter-selector-evaluation.md) specifies the
evidence required before stronger performance claims can be made.
