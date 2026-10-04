---
name: design-conn-experiment
description: Design a supported CONN Pilot sandbox experiment when a researcher asks what analyses are available or wants to turn a research question into a seed-to-voxel or ROI-to-ROI project.
---

# Design a CONN experiment

Start with `get_product_capabilities`; treat its response as the current source of truth for datasets, pipelines and limitations. Use `list_available_seeds` to resolve regions by name. Do not invent seed identifiers.

Elicit only decisions that change the scientific specification: research question, pipeline family, seeds, design, groups, covariates, contrasts and an optional operationalized hypothesis. Never infer group membership, covariate values, contrast weights or hypothesis direction.

Use `compose_pipeline` to create the draft. Then call `list_unresolved_project_parameters`. Route parameter questions to the method-comparison workflow and leave the project unsubmitted until every required parameter has an investigator-confirmed evidence record.

Before proposing execution, call `validate_project` and `generate_execution_plan`. Explain the effective sample, pipeline graph and limitations. The current beta uses only registered sandbox datasets, one session per subject, built-in CONN regions, and either one sample or two independent groups. A technically valid three-subject sandbox is not evidence of adequate statistical power.
