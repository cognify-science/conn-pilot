# MCP scientific tool reference

The authenticated MCP server exposes 40 tools in the current release. Tool
availability and visible resources remain identity-scoped; runtime discovery is
authoritative. This reference explains scientific purpose and mutation boundary,
not private infrastructure.

## Read-only discovery

| Tool | Scientific purpose |
| --- | --- |
| `get_product_capabilities` | Report supported scope, versions, and current product constraints. |
| `list_pipelines` | List executable, versioned pipeline contracts. |
| `list_datasets` | List datasets visible to the authenticated identity. |
| `inspect_dataset` | Return a path-free inventory and acquisition metadata. |
| `list_available_seeds` | Search the executable seed and ROI catalog. |
| `get_pipeline_builder_capabilities` | Describe supported graph nodes and composition rules. |
| `get_project_pipeline_graph` | Show the bound graph for an existing project. |
| `preview_pipeline_change` | Show preserved and invalidated stages before a change. |
| `get_system_health` | Report control-plane, storage, and worker readiness. |

## Project construction and validation

| Tool | Boundary |
| --- | --- |
| `start_available_flow` | Creates a guided project from a supported flow after explicit study inputs. |
| `compose_pipeline` | Creates a project from a validated modular composition. |
| `create_project` | Creates a project from an explicit supported specification. |
| `run_available_flow` | Validates and submits the supported guided flow; inspect the project first. |
| `validate_project` | Read-only validation of design, parameters, metadata, and contracts. |
| `generate_execution_plan` | Read-only frozen-plan preview, including versions and preflight. |

Creation tools persist a scientific object but do not themselves justify its
design. `run_available_flow` crosses from design into execution and should be
used only after the investigator has reviewed the frozen specification.

## Execution and monitoring

| Tool | Boundary |
| --- | --- |
| `submit_job` | Enqueues one durable job for a validated project. |
| `retry_job` | Creates a controlled retry only when the server marks it recoverable. |
| `get_job_status` | Reads remote job state and result version. |
| `get_job_progress` | Reads supervisor, MATLAB activity, subjects, phases, and durable milestones. |
| `get_job_logs` | Reads sanitized events and error context. |
| `list_results` | Lists registered result artifacts and versions. |
| `get_result_download_url` | Creates a short-lived authorized artifact download URL. |

Repeated submission is guarded against compatible duplicates, but clients should
always inspect the existing project and job before asking to submit or retry.

## QC, sample, inference, and scientific decisions

| Tool | Boundary |
| --- | --- |
| `get_qc_summary` | Read aggregate QC evidence without making a decision. |
| `get_subject_qc` | Read participant-level metrics, images, and recorded decisions. |
| `set_subject_qc_decision` | Append an investigator `accept`, `exclude`, or `needs_review` decision and rationale. |
| `request_second_level_recalculation` | Create a new model for the reviewed sample while preserving earlier versions. |
| `get_second_level_recalculation` | Read recalculation state and output version. |
| `get_experiment_quality_report` | Read the layered technical, QC, sample, inference, and hypothesis assessment. |
| `record_scientific_decision` | Append the investigator's interpretation for a current result and sample version. |
| `generate_reproducibility_package` | Export the current versioned method, evidence, QC, results, decisions, and hashes. |

The three decision tools never authorize an AI assistant to decide on behalf of
an investigator by default. They persist explicit, attributable judgments.

## Literature and parameter decisions

| Tool | Boundary |
| --- | --- |
| `list_guidance_topics` | Read available parameter topics and corpus version. |
| `get_parameter_guidance` | Read context-filtered, literature-reported options. |
| `compare_method_options` | Compare supported alternatives and their evidence records. |
| `get_evidence_record` | Read one normalized bibliographic evidence record. |
| `validate_parameter_choice` | Check a literature component's reported-value alignment; does not enforce the project's executable contract. |
| `record_method_decision` | Persist selected value, rationale, evidence IDs, and snapshot. |
| `list_method_decisions` | Read exact project-level parameter provenance and frozen selection audits when available. |
| `list_unresolved_project_parameters` | Read parameters still blocking validation. |
| `get_project_parameter_guidance` | Read executable candidates, all mapped evidence assessments, context alignment and reasons for ineligibility. |
| `resolve_project_parameter` | Enforce executable compatibility and an explicit normalized citation match; persist the investigator's choice with a frozen audit. |

Guidance calls return evidence and constraints. They do not rank a value as
universally optimal. Mutation calls require a value and rationale and preserve
the evidence snapshot used at decision time.

For `resolver_revision=context-and-strict-normalization-v2`, inspect
`evidence_assessments`, contextual differences and unassessed dimensions before
presenting alternatives. Inspect `selection_audit_status` in parameter-resolution
status reads; a context change requires renewed review for an audited choice.
Older deployed services and historical decisions may lack these fields. Verify
the response revision rather than assuming the repository version is deployed.
See [parameter-selection semantics](../science/parameter-selection.md).

## Recommended read sequence for an AI assistant

1. `get_product_capabilities`, `list_datasets`, `list_pipelines`,
   `list_available_seeds`, and `get_system_health`.
2. Inspect the chosen dataset and supported design before creating a project.
3. Read the project graph, unresolved parameters, guidance, and evidence.
4. Validate the project and show the execution plan before submission.
5. Monitor status and progress; consult logs only when needed.
6. After completion, read QC before recording any participant decision.
7. Recalculate the second level if the sample changes.
8. Read the quality report before recording a scientific interpretation.
9. Generate the package only for the current result and sample version.

The copyable [assistant bootstrap prompt](../integrations/assistant-bootstrap-prompt.md)
encodes the same safety and scientific-separation rules for supported clients.
