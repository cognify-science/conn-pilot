# Research-preview readiness

This page records readiness as of 10 October 2026. It replaces the earlier
three-participant-only roadmap. Historical runs remain evidence for the
specific inputs and software versions on which they were performed.

| Capability | Current evidence | Remaining limit |
| --- | --- | --- |
| Supported execution | Seed-to-voxel and ROI-to-ROI smoke and full benchmark completion | Narrow one-session resting-state contract |
| Scientific QC | Visual and numerical review over 55 unique benchmark participants | No universal automatic exclusion criterion |
| Sample recalculation | Corrected final clinical samples, model inspection, and preserved earlier versions | Matrix rank and degrees of freedom still require reviewer inspection |
| Evidence-backed parameters | Seven decisions with frozen evidence snapshots | Full parameter-level appraisal and comparator evaluation remain pending |
| Reproducibility | Six final packages and published aggregate values/hashes | Exact participant manifests and large derivatives remain controlled |
| Recovery | Persistent intent, orphan detection, repeated publication, and interruption regression tests | Field validation covers one worker setup, not every infrastructure failure |
| AI access | Authenticated MCP plus client-specific guides | Client capability and administrator policy must be checked at setup time |
| External scientist usability | Protocol and task sequence prepared | Independent external sessions remain pending |

## Exit criteria for an external pilot

A scientist should be able to discover current capabilities, inspect a dataset,
review the supported design, resolve parameters with evidence, validate the plan,
submit once, review QC, recalculate the sample, interpret current statistics, and
export an auditable package through an authenticated MCP-capable assistant.

A scientific conclusion additionally requires an adequate design and sample,
version-matched inferential evidence, a prospective decision rule, and explicit
limitations. Operational success alone does not satisfy that criterion.

The [public benchmark report](science/benchmark-validation-2026-10.md) is the
current performance record. The [validation matrix](beta-validation-matrix.md)
separates implementation checks from scientific validation. External sessions
should follow the [pilot protocol](external-pilot-protocol.md).
