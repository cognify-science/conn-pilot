# Scientific glossary

This glossary defines terms as they are used by CONN Pilot. It does not replace
the terminology of CONN Toolbox, SPM, BIDS, or the cited methodological sources.

| Term | Meaning in CONN Pilot |
| --- | --- |
| aCompCor | Regression of principal components estimated from anatomical noise regions. The validated pipelines use configurable white-matter and CSF component counts. |
| ART | Artifact Detection Tools outputs used by CONN for scan-level motion and global-signal outlier identification. |
| BIDS | Brain Imaging Data Structure used for registered raw inputs and acquisition metadata inheritance. |
| Catalog | Versioned definitions of supported pipelines, stages, analysis families, and CONN regions. |
| Composition | Ordered, typed graph of versioned stages resolved from a validated pipeline template. |
| Contrast | Named linear combination of between-subject effects, with ordered effect names and matching weights. |
| Corpus snapshot | Immutable version of the normalized literature evidence available when a method decision was recorded. |
| Dataset inventory | Sanitized metadata describing available participants, sessions, modalities, TR, and acquisition fields without worker paths. |
| Decision rule | Prospectively registered alpha, multiplicity method, target contrast, and expected direction used to classify evidence. |
| Denoising | Regression and temporal filtering performed after preprocessing and before connectivity estimation. |
| DVARS | Summary of temporal changes in image intensity. It is an inspection aid and not an automatic exclusion rule. |
| Evidence compatible | The current version-matched statistical evidence passes the registered rule in the expected direction. It does not prove the hypothesis true. |
| Execution plan | Immutable resolution of project, dataset, parameters, preflight, stages, versions, and worker assignment. |
| Fisher z | Fisher transformation of a correlation coefficient used by CONN for supported first-level connectivity estimates. |
| First level | Participant-level connectivity estimation after preprocessing and denoising. |
| Framewise displacement | Motion-change summary whose formula depends on the method. CONN Pilot's field `outlier_fd_threshold_mm` maps to the ART displacement threshold; equivalence to a particular published FD definition must be verified. |
| Global-signal threshold | Standardized whole-brain signal-change threshold used by ART for scan-level outlier detection; it is distinct from global-signal regression. |
| GSR | Global-signal regression. It is disabled in the current executable contract. |
| Hypothesis | Structured statement linked to a target contrast, expected direction, decision rule, and optional sample-adequacy argument. |
| MCP | Model Context Protocol interface through which authenticated assistants call CONN Pilot tools. |
| Method decision | Investigator-confirmed parameter value stored with rationale, exact evidence identifiers, and corpus version. |
| MNI space | Standard stereotactic space targeted by the validated preprocessing template. |
| Multiplicity | Method used to account for multiple statistical tests, such as FDR or Bonferroni correction. |
| PCC | Posterior cingulate cortex; the benchmark seed is the built-in `networks.DefaultMode.PCC` source. |
| Preflight | Deterministic resolution of execution requirements that depend on acquisition metadata, including slice timing. |
| Project | Versioned scientific intent: question, dataset reference, sample, regions, design, contrasts, hypotheses, and parameter records. |
| QC decision | Append-only investigator judgment of `accept`, `exclude`, or `needs_review` for one participant and result version. |
| Reproducibility package | Versioned export containing methods, provenance, QC decisions, current result records, reports, artifacts, and hashes. |
| Result version | Content-derived identity of one published technical result. |
| ROI-to-ROI | Fisher-transformed bivariate connectivity between selected pairs of ROI time series in the validated pipeline. |
| Sample version | Hash-derived identity of the ordered effective participant sample after QC. |
| Scrubbing | Inclusion of scan-level ART outlier regressors during denoising. |
| Second level | Group model over participant-level connectivity estimates. |
| Seed-to-voxel | Fisher-transformed bivariate correlation between a seed time series and every target voxel in the validated pipeline. |
| Slice-timing omission | Explicitly authorized removal of slice-time correction when exact `SliceTiming` metadata is unavailable. It is never inferred silently. |
| Technical completion | Confirmation that required stages and artifacts exist. It carries no automatic claim about QC or a hypothesis. |
| tSNR | Temporal signal-to-noise summary used as supporting QC evidence when validly exported. |
| Worker | Authorized execution service that holds local data and runs MATLAB/SPM/CONN while communicating outbound with the control plane. |
