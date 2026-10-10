# Scientific questions and established answers

This FAQ is a claim boundary for scientists and their AI assistants. Detailed
mechanisms are in the [module reference](scientific-modules.md), exact methods
in [statistical methods](statistical-methods.md), and current numerical results
in the [benchmark report](benchmark-validation-2026-10.md).

## What does CONN Pilot contribute beyond CONN Toolbox?

CONN Toolbox performs the numerical preprocessing, denoising, connectivity, QA,
and group estimation. CONN Pilot adds constrained experiment design, executable
contracts, literature provenance, deterministic batch generation, durable remote
job intent, QC decisions, sample versioning, hypothesis-aware reporting, and
reproducibility export. The AI client explains and coordinates; it does not
replace CONN's numerical algorithms.

## Who chose the benchmark parameters?

The benchmark used a frozen investigator-authorized shared baseline. CONN Pilot
linked each of seven choices to explicit observations and retained decision
records. CONN Toolbox itself did not read papers or optimize those values. The
comparison with one reserved expert baseline established agreement for the
comparable values. It did not establish independent autonomous optimization.

## Can I see exactly which papers informed an executed project?

Yes, if the project belongs to your authenticated identity. Retrieve
`list_method_decisions(project_id)` for the values, rationales, evidence IDs,
corpus version, and stored snapshots. Use `get_evidence_record(pmid)` to inspect
the normalized paper record. Do not substitute a list of all corpus papers for
the exact sources used by a project.

The repository's bibliographic inventory is in
[`corpus_manifest.csv`](../../knowledge/pipeline_review/corpus_manifest.csv).
Its [evidence-corpus guide](evidence-corpus.md) explains the 138 indexed papers,
45 reviewed instances, and inherited material. Full copyrighted PDFs are not
served by these tools or redistributed in this repository.

## Does the corpus make the selected method scientifically optimal?

No optimality claim has been established. The resolver validates executable
compatibility and explicit evidence matching. Scientific applicability, risk of
bias, alternatives, and uncertainty require appraisal. The
[selector evaluation protocol](parameter-selector-evaluation.md) defines frozen
expert, paper-specific, and CONN-reference arms needed to test performance.

## Were the source papers reproduced?

The validation reproduced a supported analysis workflow on subsets of public
source data. WU120 recovered a prospective PCC/default-mode positive control.
That question differs from the main motion-method question in its source
publications. The fibromyalgia and UCLA subsets used restricted PCC tests and
small final samples, while source studies used larger or different analyses.
Those clinical runs did not establish statistical reproduction of the papers.

## Why can an uncorrected clinical peak be small while the result is inconclusive?

Selecting the strongest voxel from a large tested volume creates a multiplicity
problem. In the final clinical benchmarks no voxel survived FDR q<0.05, and
the reported peaks failed whole-volume Bonferroni correction. Small groups,
residual motion, and different estimands further limit interpretation. An
uncorrected peak is an exploratory observation, not corrected support.

## Is non-significance evidence that the disease has no connectivity effect?

The present benchmark cannot establish that. It did not perform an equivalence
test, demonstrate adequate power or precision, or analyze the complete source
cohort and all source-paper estimands. The scientific result is inconclusive for
the restricted clinical questions in these subsets.

## Does a completed job automatically generate a scientific conclusion?

Technical completion confirms expected files and stages. A current quality
report additionally requires completed QC and a current reviewed sample/model.
Hypothesis classification then requires structured, version-matched contrast,
effect, test or interval, and multiplicity evidence. The current release does
not automatically extract every such field from every CONN model; a finished
job may legitimately remain `not_evaluable_inference`.

The hypothesis evaluator applies an alpha rule to a p-value or adjusted p-value.
A confidence interval can satisfy evidence completeness, but an interval alone
does not currently provide the p-value required by that decision-rule evaluator.
The investigator's interpretation remains an independent record.

The report's sample-adequacy flag records the presence of a documented argument;
it does not independently calculate or validate statistical power. Review that
argument and its assumptions before making a confirmatory claim.

## What did the second-level bug affect?

Initial post-QC clinical recalculations reused covariate names and apparently
completed while retaining the original 20-participant model. The CONN Pilot
generator was corrected to use execution-unique aliases. Corrected models used
18 and 16 participants, with inspected ranks and residual degrees of freedom.
Final public statistics are from the corrected models. Actual design-matrix
integrity still needs review because it is not yet an automatic success gate.

## Are all computational settings explicit?

The seven literature-backed choices, detrending, despiking, sources, effects,
contrasts, and preflight branch are explicit. Some other CONN fields inherit
toolbox defaults, including within-condition weighting and aspects of ROI
extraction and analysis geometry. Exact reproduction requires the saved project,
generated batch, source inventory, and pinned software versions. The
[methods appendix](statistical-methods.md) records this limitation.

## Does ROI-to-ROI take longer than seed-to-voxel?

The benchmark calendar durations do not answer that question: queue waits,
outages, retries, and repeated preprocessing were included. The present engine
does not automatically reuse all upstream derivatives across separate projects.
Pure compute-time comparisons require comparable uninterrupted runs and phase
timing. A long active stage alone does not establish a stall.

## What happens after a power or internet interruption?

Internet loss can delay synchronization while MATLAB continues. After power
loss, the durable remote intent can create a clean local attempt with the same
remote job identity. Stage reuse depends on compatible preserved outputs; the
product does not promise continuation at the exact interrupted instruction.
Scientific/input failures remain explicit terminal errors. Recovery is described
in [resilient-worker semantics](../resilient-worker.md).

## Can I reproduce everything from GitHub alone?

GitHub contains code, contracts, corpus metadata, public aggregate results,
protocol identity, and package checksums. Exact participant manifests, raw BIDS
inputs, participant-level QC evidence, and some large derivatives require the
authorized data/export workflow. The [reproducibility checklist](reproducibility.md)
specifies what an independent audit needs.

## What remains before stronger scientific claims?

- Independent external scientist evaluation.
- Complete parameter-level methodological appraisal.
- Frozen comparator arms and sensitivity analysis for the selector.
- Adequate prospective sample size or precision for substantive clinical claims.
- Automatic checks of actual model counts, rank, contrasts, and residual df.
- More complete capture of inherited CONN defaults and structured inference.
- Correct availability flags and volume-indexed verification of legacy QC metrics.

These are research and implementation limits, not missing answers that an AI
assistant should fill with assumptions.
