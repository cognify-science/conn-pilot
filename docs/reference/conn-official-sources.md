# Official CONN sources for researchers and AI assistants

Verified on **2026-10-10**. This guide maps scientific questions to CONN's own
documentation, released source code, and primary methodological references.
Its [machine-readable index](conn-official-sources.json) contains stable source
identifiers, URLs, topics, and version relationships. It is a consultation
directory, not the executable parameter-selection corpus or a claim that a
paper justified a particular Pilot run.

## Provenance and version

The [official development page][development] identifies
[`alfnie/conn`][repository] as CONN's source repository. The upstream reference
for Pilot's validated **CONN 25.b** environment is [release `v25b`][release25b],
published 2026-02-22, resolving to commit
`87e4f24988cf3a9bf7aa81f41c705a2baf68540f`.
Code links below are pinned to this commit. This identifies the upstream
reference; it does **not** establish that every installed worker file has that
hash. An execution audit must also check its recorded software versions and,
where available, installed-file or package hashes.

The website and GitHub `master` are mutable. Consult them for learning and
updates, then verify release-specific behavior against the relevant source.
In particular, the `v25b` tree includes a manual named
`CONN_fMRI_Functional_connectivity_toolbox_manual_v22.pdf`, while the current
manual portal advertises release 2025/v25. Do not infer the manual's version
from the repository tag or substitute development code for a released default.
Use the [official manual portal][manual] and inspect the document's version.

## Which source answers which question?

| Question | Source to use | Boundary |
| --- | --- | --- |
| What does CONN implement in a particular release? | Released source, batch reference, manual, and changelog | Follow the actual code path and dependencies; a filename alone is not evidence of behavior. |
| What is the methodological rationale? | Official methods chapters and the primary papers they cite | A method's description does not make a parameter universally optimal. |
| What can CONN Pilot execute? | [Pilot methods](../science/statistical-methods.md), versioned `catalog/` and `contracts/`, and runtime capabilities | CONN Toolbox's broader feature set is not Pilot's supported API. |
| What was used in this study? | Frozen parameter decisions, generated batch, software versions, result and sample records | A website default or a source listed here does not prove that the study used it. |
| What do these results support? | Current statistical artifacts, QC evidence, prospective hypothesis, and study-specific literature | Toolbox documentation does not establish replication of a benchmark paper. |

Start with [SCIENTIST_CONTEXT.md](../../SCIENTIST_CONTEXT.md) for Pilot's
scientific scope. Read the upstream sources when explaining the underlying
algorithms, inherited defaults, or a methodological limitation.

## Scientific topic directory

| Topic or researcher question | Official explanation | Released implementation entry points |
| --- | --- | --- |
| Study structure, subjects, sessions, conditions, covariates, and batch fields | [Manual][manual], [batch reference][batch], [module reference][module] | [`conn_batch.m`][src-batch], [`conn_importbids.m`][src-importbids], [`conn_bidsdir.m`][src-bidsdir] |
| Preprocessing order, realignment, slice timing, normalization, segmentation, and smoothing | [Preprocessing methods][preprocessing] | [`conn_setup_preproc.m`][src-preproc]; also verify the recorded SPM version and invoked SPM routines |
| ART outlier detection, motion and global-signal thresholds | [Preprocessing methods][preprocessing], [denoising and QC][denoising] | [`conn_art.m`][src-art], [`conn_setup_preproc.m`][src-preproc] |
| Nuisance regression, aCompCor, WM/CSF components, motion regressors, scrubbing, detrending, and filtering | [Denoising methods][denoising], [batch fields][batch], [CompCor paper][compcor-paper] | [`conn_process.m`][src-process], [`conn_filter.m`][src-filter] |
| GSR, anticorrelations, and how to interpret a preprocessing choice | [Denoising methods][denoising], [Chai et al.][anticorrelations-paper] | [`conn_process.m`][src-process], plus the executed confound list; a paper does not imply Pilot supports switching GSR on |
| ROI definitions, atlas labels, spatial extraction, and network seeds | [Manual][manual], [connectivity methods][connectivity], [batch reference][batch] | [`rois/`][src-rois], [`conn_batch.m`][src-batch], [`conn_process.m`][src-process]; record the specific ROI file and hash |
| Seed-to-voxel correlation, Fisher transformation, weighting, and analysis options | [Seed-based methods][seed], [batch reference][batch] | [`conn_process.m`][src-process], [`conn_batch.m`][src-batch] |
| ROI-to-ROI correlation and connection-level versus network-level inference | [ROI-to-ROI methods][roi], [inference methods][inference] | [`conn_process.m`][src-process], [`conn_glm.m`][src-glm], [`conn_fdr.m`][src-fdr] |
| Second-level design, covariates, contrasts, tests, effect estimates, and residual degrees of freedom | [General linear model][glm] | [`conn_designmatrix.m`][src-design], [`conn_glm.m`][src-glm]; inspect the actual generated model |
| Voxel/cluster/connection inference, correction for multiple comparisons, parametric and permutation approaches | [Inference methods][inference], [GLM][glm] | [`conn_glm.m`][src-glm], [`conn_fdr.m`][src-fdr], [`conn_randomise.m`][src-randomise]; verify the method and settings used in the result |
| Registration review, motion, denoising diagnostics, QC-FC, and sample inspection | [Denoising and QC][denoising], [QC methods paper][qc-paper] | [`conn_qaplots.m`][src-qaplots], [`conn_qascores.m`][src-qascores]; compare with [Pilot's QC exporter limits](../science/qc-manual.md) |
| Methods reporting, algorithm references, and reproducible attribution | [Describing analyses][reporting], [manual references][manual], [software citation][software25] | [`conn_reference.m`][src-reference], [preprocessing][src-reference-preproc], [denoising][src-reference-denoising], [first-level][src-reference-firstlevel], [second-level][src-reference-secondlevel], and [QC][src-reference-qualitycontrol] citation files, generated methods, and actual batch |
| Internal parallel processing and job stages | [CONN parallelization documentation][parallel] | [`conn_jobmanager.m`][src-jobs]; this is conceptual upstream documentation, not a Pilot deployment guide |
| Toolbox capabilities beyond Pilot: PPI, ICA, dynamic connectivity, multivariate and graph methods | [Connectivity methods hub][connectivity], [manual][manual] | Consult upstream for learning; first check Pilot's contract before proposing execution |
| Release changes and learning examples | [Release][release25b], [`change.log`][src-changelog], [tutorials][tutorials] | A tutorial's settings are examples, not automatic study recommendations |
| Clarification of a version-specific issue | [Official support page][support], [NITRC forum][forum], [upstream issues][issues] | Read the complete discussion, date and release; a forum answer is contextual advice, not a general validated rule |

These are entry points for source inspection, not a function-by-function
certification. Some operations delegate to SPM or other routines. Trace that
dependency and cite the matching version when it affects the answer.

## Core methodological reading

These references are linked from CONN's official methods or reference material.
They serve different purposes and should not be used interchangeably.

| Reference | Why consult it |
| --- | --- |
| [Whitfield-Gabrieli & Nieto-Castanon (2012), CONN toolbox][toolbox-paper] | Foundational description of the toolbox. Use current source and documentation for later features. DOI: `10.1089/brain.2012.0073`. |
| [Nieto-Castanon (2020), functional-connectivity methods handbook][handbook] | Method framework; the [online methods chapters][methods] provide the accessible topic map. DOI: `10.56441/hilbertpress.2207.6598`. |
| [Behzadi et al. (2007), CompCor][compcor-paper] | Origin and rationale of component-based nuisance correction. DOI: `10.1016/j.neuroimage.2007.04.042`. |
| [Chai et al. (2012), anticorrelations without GSR][anticorrelations-paper] | Evidence relevant to denoising and anticorrelation interpretation, with study-specific assumptions. DOI: `10.1016/j.neuroimage.2011.08.048`. |
| [Morfini, Whitfield-Gabrieli & Nieto-Castanon (2023), QC procedures][qc-paper] | Dedicated CONN quality-control methodology and inspection workflow. DOI: `10.3389/fnins.2023.1092125`. |
| [Nieto-Castanon & Whitfield-Gabrieli (2025), CONN Version 25][software25] | Software attribution, distinct from evidence for a methodological choice. DOI: `10.56441/hilbertpress.2538.3958`; RRID: `SCR_009550`. |

For a particular technique, continue to the primary references listed in its
official chapter and generated methods. This directory is not a systematic
review, a complete bibliography, or a replacement for study-specific papers.
Full-text availability must be checked; an abstract or citation cannot support
an exact parameter extraction that requires the methods or supplement.

## How an AI assistant should consult and cite these sources

1. Establish whether the question concerns CONN Toolbox, Pilot's wrapper, or a
   particular execution. Check Pilot's supported contract first.
2. Identify the actual software version and the study's frozen parameters.
   Distinguish explicit batch values from inherited defaults.
3. Read the relevant official chapter or manual section. For an exact default,
   computation, or version difference, inspect the matching released source and
   its called routines. Never infer a value from an unrelated example.
4. Cite the page or DOI for methodology; cite a release/commit, file, and relevant
   field or code section for implementation. For an executed setting, also cite
   the project/result version and batch or artifact record.
5. State what was directly verified, what is inferred, and what remains missing.
   If documentation, code, and runtime differ, describe the discrepancy instead
   of silently selecting the preferred source. Do not change a frozen analysis
   or upgrade software to resolve a documentation question.
6. For scientific conclusions, inspect subject QC, current sample/model,
   contrast direction, thresholds, multiplicity, effect and uncertainty, and
   the benchmark paper's actual population and methods.

An answer can use this compact provenance pattern:

> Claim: [specific statement]. Basis: [official page/DOI or released file and
> field], version [release/commit], consulted [date]. Pilot applicability:
> [supported / upstream only / unverified]. Executed evidence: [project/result
> version and batch or artifact, when available]. Limitation: [missing evidence
> or dependency affecting this claim].

The JSON index's identifiers are documentation references. They are **not**
CONN Pilot corpus `evidence_id` values. Registering these links does not import
papers into the selector, change its recommendations, or retrospectively
attribute benchmark parameter decisions to them. Follow
[evidence governance](../science/evidence-governance.md) for corpus changes.

## Maintaining the directory

On an upstream or Pilot version change, verify the official provenance link,
release tag and resolved commit, file existence, manual version, DOI metadata,
and Pilot support boundary. Update the guide and JSON together and record the
verification date. A live page is not archived here, and its present contents
may differ from the material consulted for an earlier execution. Preserve
execution-specific evidence and hashes in the reproducibility package.

CONN's own licensing applies to its code and documents. This directory links
to upstream material and does not redistribute full papers or grant rights to
CONN Pilot or benchmark data.

[development]: https://web.conn-toolbox.org/resources/conn-development
[repository]: https://github.com/alfnie/conn
[release25b]: https://github.com/alfnie/conn/releases/tag/v25b
[manual]: https://web.conn-toolbox.org/resources/conn-manual
[batch]: https://web.conn-toolbox.org/resources/conn-manual/conn_batch
[module]: https://web.conn-toolbox.org/resources/conn-manual/conn_module
[methods]: https://web.conn-toolbox.org/fmri-methods
[preprocessing]: https://web.conn-toolbox.org/fmri-methods/preprocessing-pipeline
[denoising]: https://web.conn-toolbox.org/fmri-methods/denoising-pipeline
[connectivity]: https://web.conn-toolbox.org/fmri-methods/connectivity-measures
[seed]: https://web.conn-toolbox.org/fmri-methods/connectivity-measures/seed-based
[roi]: https://web.conn-toolbox.org/fmri-methods/connectivity-measures/roi-to-roi
[glm]: https://web.conn-toolbox.org/fmri-methods/general-linear-model
[inference]: https://web.conn-toolbox.org/fmri-methods/cluster-level-inferences
[reporting]: https://web.conn-toolbox.org/resources/describing-conn-analyses
[parallel]: https://web.conn-toolbox.org/resources/hpc-configuration
[tutorials]: https://web.conn-toolbox.org/resources/conn-tutorials
[support]: https://web.conn-toolbox.org/resources/support
[forum]: https://www.nitrc.org/forum/forum.php?forum_id=1144
[issues]: https://github.com/alfnie/conn/issues
[src-batch]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_batch.m
[src-importbids]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_importbids.m
[src-bidsdir]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_bidsdir.m
[src-preproc]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_setup_preproc.m
[src-art]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_art.m
[src-process]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_process.m
[src-filter]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_filter.m
[src-rois]: https://github.com/alfnie/conn/tree/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/rois
[src-design]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_designmatrix.m
[src-glm]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_glm.m
[src-fdr]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_fdr.m
[src-randomise]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_randomise.m
[src-qaplots]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_qaplots.m
[src-qascores]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_qascores.m
[src-reference]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_reference.m
[src-reference-denoising]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_reference_denoising.txt
[src-reference-preproc]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_reference_preproc.txt
[src-reference-firstlevel]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_reference_firstlevel.txt
[src-reference-secondlevel]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_reference_secondlevel.txt
[src-reference-qualitycontrol]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_reference_qualitycontrol.txt
[src-jobs]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/conn_jobmanager.m
[src-changelog]: https://github.com/alfnie/conn/blob/87e4f24988cf3a9bf7aa81f41c705a2baf68540f/change.log
[toolbox-paper]: https://doi.org/10.1089/brain.2012.0073
[handbook]: https://doi.org/10.56441/hilbertpress.2207.6598
[compcor-paper]: https://doi.org/10.1016/j.neuroimage.2007.04.042
[anticorrelations-paper]: https://doi.org/10.1016/j.neuroimage.2011.08.048
[qc-paper]: https://doi.org/10.3389/fnins.2023.1092125
[software25]: https://doi.org/10.56441/hilbertpress.2538.3958
