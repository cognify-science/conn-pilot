# Quality control and scientific inference

CONN Pilot reports four separate states because each answers a different question.

## 1. Technical completion

The engine checks the expected CONN project, first-level outputs, second-level
model, manifests, and selected artifacts. This establishes that the declared job
completed. It says nothing about data quality or a hypothesis.

## 2. Subject quality

For each subject, the system can expose ART summaries and images for registration,
normalization, segmentation, outliers, and denoising, together with tSNR, DVARS,
retained volumes, and outlier runs when available. A researcher may record
`accept`, `exclude`, or `needs_review`. Exclusion requires a rationale.

No subject is automatically excluded merely because a metric is unusual. The
system may flag evidence for inspection, but the scientific decision remains an
auditable record.

## 3. Current statistical model

Changing the accepted sample invalidates the old group result. The prior result is
retained, marked stale, and cannot be scientifically accepted for the new sample.
A second-level recalculation creates a new sample version and model version while
reusing compatible first-level outputs.

## 4. Hypothesis evidence

`get_experiment_quality_report` first asks whether technical completeness, QC, and
sample-version consistency permit interpretation. It then checks whether the
hypothesis was operationalized with:

- a target contrast;
- an expected direction;
- a decision rule;
- a multiplicity method;
- version-matched inferential evidence, including an effect estimate.

The report can classify the evidence as not evaluable, inconclusive, compatible,
or not compatible. “Compatible” means compatible with the registered hypothesis
under the declared rule; it does not prove that hypothesis true. A non-significant
result is not automatically evidence of no effect.

Small benchmark samples are suitable for testing execution and reporting. They do
not acquire adequate statistical power merely because the pipeline completed.
