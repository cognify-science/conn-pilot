---
name: compare-conn-methods
description: Compare literature-supported CONN parameter options and record an investigator's methodological choice for a CONN Pilot project.
---

# Compare CONN methods

For a project parameter, call `get_project_parameter_guidance`; for broader questions use `list_guidance_topics`, `get_parameter_guidance`, `compare_method_options` and `get_evidence_record` as needed.

Present only executable values compatible with the project's dataset and pipeline contract. For every option show the reported value, applicable context, evidence identifiers and relevant papers. Distinguish explicit observations from inferred or unreported information. Frequency in the corpus is descriptive and must never become an automatic recommendation.

Compare options against the research question, TR, design and stated limitations. State where the corpus cannot determine scientific suitability. Ask the investigator to select the value and provide a rationale.

Before saving, call `validate_parameter_choice`. Persist the choice with `resolve_project_parameter` so the exact evidence snapshot, corpus version and rationale are bound atomically to the project. Do not call this mutation until the investigator has confirmed the value.
