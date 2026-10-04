---
name: run-conn-analysis
description: Validate, submit and monitor a CONN Pilot analysis when a researcher asks to run, retry or check an existing seed-to-voxel or ROI-to-ROI project.
---

# Run a CONN analysis

Call `validate_project` and `generate_execution_plan` before submission. If the project has unresolved parameters, use `list_unresolved_project_parameters` and report the exact next decision instead of bypassing it.

When the user has asked to execute a complete project, call `run_available_flow`. Repeating this call may reuse an existing queued, running or successful job. Report whether the job was reused.

Use `get_job_status` for progress and `get_job_logs` when a phase fails or stalls. Do not submit duplicate projects or retry a failed job repeatedly. Use `retry_job` once only when the failure is reported as recoverable; otherwise explain the recorded error.

On success, report the result version and direct the workflow to subject-level QC. Do not describe technical completion as scientific acceptance or hypothesis confirmation.
