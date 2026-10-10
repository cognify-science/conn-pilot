# Architecture and trust boundaries

CONN Pilot is split into five cooperating layers. The split keeps model reasoning,
scientific decisions, deterministic execution, and protected data from silently
substituting for one another.

## Layers

1. **AI client.** Translates a research question into tool calls, summarizes
   evidence, and explains alternatives. It does not generate free-form MATLAB for
   execution and it cannot bypass the server contract.
2. **MCP control plane.** Authenticates the researcher, stores projects and
   decisions, validates every transition, queues work, and returns typed records.
3. **Versioned scientific catalog.** Defines the executable families, stages,
   supported values, compatibility limits, and the mapping from a project field
   to a CONN batch field.
4. **Evidence corpus.** Stores structured observations from papers separately
   from methodological appraisal and internal technical validation.
5. **Worker and deterministic engine.** Materialize an immutable execution plan,
   stage protected copies of BIDS inputs, generate the batch, run MATLAB/SPM/CONN,
   and publish selected outputs.

## Data boundary

The worker makes outbound HTTPS requests. Raw T1w and BOLD images, local paths,
MATLAB licenses, and host credentials remain local. The control plane receives:

- a path-free dataset and acquisition inventory;
- project parameters and their provenance;
- progress and health events;
- selected QC images, metrics, statistical outputs, manifests, and hashes.

This boundary reduces disclosure; it does not make uploaded derivatives anonymous.
Investigators remain responsible for institutional data-governance requirements.

## Identity boundary

Each remote request is scoped to the OAuth subject. The server verifies issuer,
audience, expiry, signature, and the `conn-pilot:use` permission. Projects, jobs,
artifacts, QC decisions, and scientific decisions are retrieved through that
subject. Administrative and worker credentials are separate from researcher OAuth.

## Decision boundary

The client can propose. The control plane can validate and persist. The engine can
execute only a validated contract. The following are independent records:

- a literature observation;
- an AI explanation or proposal;
- a selected parameter with rationale and evidence snapshot;
- an executable plan;
- a technical result;
- a subject-level QC decision;
- a scientific interpretation.

Keeping these records separate is a core design property, not a presentation
choice.
