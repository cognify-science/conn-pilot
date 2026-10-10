# Execution preflight and parameter resolution

CONN Pilot evaluates execution-time requirements before starting MATLAB. The
preflight is deterministic and never asks CONN to open an interactive dialog.

Each requirement is recorded as one of:

- `resolved`: exact dataset metadata is available;
- `resolved_with_omission`: an investigator-authorized policy omits the step;
- `unresolved`: execution is blocked and the available resolution options are
  returned to the client-side literature advisor;
- `not_applicable`: the selected pipeline does not require the value.

For BIDS slice timing, the engine applies metadata inheritance from dataset root
through subject and session directories. When `SliceTiming` is available it is
materialized next to each protected staged NIfTI and CONN uses the BIDS value.
When it is unavailable, the engine never guesses an acquisition order. It offers
three resolutions: provide the exact values, retrieve the exact protocol from
dataset documentation or literature, or explicitly omit slice-timing correction.

The generated `preflight.json`, `project.execution.yaml`, MATLAB batch and run
manifest preserve the decision, source, confidence, rationale and scientific
consequence. The worker receives only a fully resolved execution contract.

The worker publishes a path-free acquisition metadata inventory to the control
plane. Codex or ChatGPT can use that inventory with the investigator's model to
search literature and propose a cited resolution. The control service and CONN
worker do not require a model-provider API key for this process.
