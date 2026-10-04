---
name: review-conn-results
description: Review CONN Pilot quality, subjects, sample versions, hypothesis evidence and reproducibility outputs after an analysis finishes.
---

# Review CONN results

Use `get_qc_summary` first. Keep technical completeness, subject quality, second-level currency and scientific acceptance separate in every explanation.

Call `get_subject_qc` to retrieve ART metrics, native CONN QA and temporary signed image URLs. Review each subject with the investigator. Record only their decision through `set_subject_qc_decision`: `accept`, `exclude` or `needs_review`. Every exclusion needs a specific justification. Never decide exclusion solely from one metric or threshold.

If the accepted sample changes, call `request_second_level_recalculation` with the current result and sample versions. Wait for `get_second_level_recalculation` to succeed before allowing scientific acceptance.

Use `get_experiment_quality_report` to state whether quality permits interpretation and whether versioned evidence is compatible with the operationalized hypothesis. Use its wording and limitations. Never convert a successful run, a p-value or absence of significance into proof that a hypothesis is true or false.

Call `record_scientific_decision` only with the investigator's explicit rationale. Finish with `generate_reproducibility_package` and, when individual artifacts are needed, `get_result_download_url`. This beta has no review portal; all decisions occur through authenticated MCP tools.
