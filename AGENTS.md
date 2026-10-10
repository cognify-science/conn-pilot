# Repository guidance for AI assistants

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

The supported scientific scope is documented in `docs/science/`. Client setup is
documented in `docs/integrations/`. The executable contracts remain authoritative
for the current software version.
