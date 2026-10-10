# External scientist pilot protocol

## Objective

Check whether an independent scientist can use an authenticated MCP-capable
assistant to inspect, review, and report a supported analysis without manually
editing MATLAB or YAML. The optional visual portal may assist, but the scientific
workflow must remain accessible through MCP.

## Participants and sessions

- Three to five researchers with functional fMRI experience.
- Individual sessions of 45-60 minutes.
- Record the AI client, version, and institutional connection constraints.
- A facilitator records times and intervenes only after a three-minute block.
- Use an authorized prepared small result; do not wait for a new full run during
  the session.

## Tasks

1. Inspect current capabilities and explain two parameter choices using exact
   evidence records and applicability limits.
2. Open an existing supported result and distinguish technical completion from
   scientific readiness.
3. Inspect every participant's QC evidence, including missing/unreliable fields.
4. Record explicit QC decisions with rationales; preserve uncertainty when needed.
5. Request a new second level if the sample changes and verify the new version.
6. Explain effect, inference, multiplicity, sample adequacy, and limitations;
   record an attributable scientific decision when justified.
7. Export the package and locate methods, decisions, evidence, QC, results, and hashes.
8. Answer at least one scientific question using MCP and repository context
   without relying on the optional portal.

## Measurements

Record time per task and overall, facilitator interventions, errors, unresolved
blocks, ambiguous language, and whether the participant correctly understands
parameter provenance, QC, model currency, and inference. Collect confidence
ratings from 1 to 5 plus open comments. High confidence without correct
understanding is not success.

Do not collect credentials or unrelated participant information in the usability
record. Use consented, authorized material and an isolated researcher identity.

## Prespecified acceptance criteria

- At least four of five researchers, or all if only three or four participate,
  complete all eight tasks.
- Median completion time is below 45 minutes with at most one intervention per
  participant.
- Every exclusion has a rationale and correct version binding.
- Every participant identifies the effective sample and current second-level state.
- At least 80% rate reproducibility confidence as 4 or 5 and demonstrate correct
  provenance retrieval.
- No cross-identity disclosure or lost decision occurs.
- No participant interprets technical success or significance alone as proof.

## Closure

Export the session package and record each finding as a blocker, scientific
error, operational error, or usability improvement. A blocker or scientific error
requires correction before additional sessions. This protocol is prepared;
independent external sessions have not yet established its success criteria.
