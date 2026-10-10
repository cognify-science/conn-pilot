# Evidence corpus

The repository includes a versioned normalization of an inherited CONN literature
collection. It is designed for traceability and gap detection, not automated
meta-analysis.

## Contents

- `corpus_manifest.csv`: 138 unique papers with identifiers and source hashes.
- `instances/`: normalized pipeline observations for reviewed sources.
- `curation/pilot_source_reviews.yaml`: review notes and discrepancies.
- `core_taxonomy_v1.yaml`: typed dimensions, components, and evidence rules.
- `paper_component_matrix.csv`: conservative component-level census.
- `completed_stratified_review.md`: synthesis of the 45-paper reviewed sample.
- `snapshot.yaml`: corpus and normalizer versions plus known limitations.

The 45 reviewed papers cover a central resting-state stratum plus ROI-to-ROI,
graph theory, task connectivity, longitudinal analysis, dynamic connectivity, and
machine-learning feature pipelines. The remaining 93 papers retain inherited
extractions that have not been checked against full text.

## Source roles

| Source class | Appropriate use |
| --- | --- |
| CONN/SPM documentation | software behavior and parameter semantics |
| methodological comparison or consensus | consequences and selection criteria |
| systematic review | evidence landscape and disagreement |
| application paper | precedent in a similar context |
| internal validation | combinations reproduced technically by CONN Pilot |

An application paper is not promoted to a universal default. Internal validation
does not establish external scientific validity.

## Updating the corpus

Executable guidance uses an immutable reviewed snapshot. New web searches can
identify candidates, but a candidate becomes actionable only after deduplication,
structured extraction, source verification, human methodological review, corpus
validation, and publication as a new version.

Full copyrighted papers are not redistributed here. The repository stores
bibliographic identifiers, hashes, structured observations, and review notes.
