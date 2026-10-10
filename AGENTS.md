# Repository guidance for AI assistants

Read `SCIENTIST_CONTEXT.md` first. It is the scientific entry point and maps
common questions to the current methods, evidence, validation, and runtime
sources. Then read the relevant versioned contracts before making a claim.

When explaining underlying CONN algorithms or defaults, consult
`docs/reference/conn-official-sources.md` and its JSON index. Cite official
documentation or primary papers for methodology and release-pinned code for
exact implementation. Verify the runtime version and generated batch for an
executed setting. Do not equate upstream capabilities with Pilot support,
mutable `master` with a validated release, or these source IDs with corpus
evidence IDs.

CONN Pilot is research software for reproducible resting-state functional
connectivity workflows. Preserve the distinction between technical completion,
subject-level QC, statistical results, and scientific interpretation.

When helping a researcher:

- inspect the relevant contracts and versioned catalog before describing support;
- cite evidence identifiers returned by the system rather than inventing papers;
- treat literature frequency as descriptive evidence, not an automatic choice;
- show the design, contrast, thresholds, multiplicity policy, and resolved
  parameter record before job submission;
- never mark a subject `accept`, `exclude`, or `needs_review` without an explicit
  investigator decision;
- reuse projects and jobs when the API reports an existing compatible object;
- keep credentials, private host details, local paths, and source neuroimages out
  of commits, issues, logs, and conversations;
- run the relevant tests after changing contracts, execution, QC, or reporting.

The supported scientific scope is documented in `docs/science/`, and every MCP
tool is described in `docs/reference/mcp-tools.md`. Client setup is documented in
`docs/integrations/`. The executable contracts remain authoritative for the
current software version; authenticated runtime calls remain authoritative for
current resource and job state.
