# Public benchmark validation — October 2026

This report documents the first integral scientific validation of CONN Pilot on
three public resting-state fMRI benchmarks. It combines the frozen protocol,
technical execution, subject-level QC review, corrected second-level models,
statistical results, literature comparison, parameter-selection assessment, and
reproducibility outputs.

The accompanying [machine-readable result record](data/benchmark-results-2026-10.json)
contains the principal numerical values. Raw neuroimages, participant-level
derivatives, worker paths, credentials, internal project identifiers, and
operational recovery details are deliberately excluded from this repository.

## Study questions and frozen protocol

Six analyses were specified before inspecting their results:

| Dataset | Analysis | Prospective question |
| --- | --- | --- |
| WU120, 15 controls | PCC seed-to-voxel | Is PCC-centered default-mode connectivity positive at four predefined DMN coordinates? |
| WU120, 15 controls | PCC–MPFC ROI-to-ROI | Is PCC–MPFC connectivity positive? |
| Fibromyalgia, 10+10 initial sample | PCC seed-to-voxel | Is there a two-sided difference between fibromyalgia and control groups? |
| Fibromyalgia, 10+10 initial sample | PCC–MPFC ROI-to-ROI | Is there a two-sided PCC–MPFC group difference? |
| UCLA CNP, 10+10 initial sample | PCC seed-to-voxel | Is there a two-sided difference between schizophrenia and control groups? |
| UCLA CNP, 10+10 initial sample | PCC–MPFC ROI-to-ROI | Is there a two-sided PCC–MPFC group difference? |

The clinical comparisons were exploratory fixed-sample benchmarks. No formal
power claim was made. Technical completion and a small uncorrected p-value were
not defined as confirmation of a scientific hypothesis.

The protocol was frozen on 6 October 2026 with manifest SHA-256
`A11BF21719D32152442416F3FF2D9B0A362170EB780AAC5D0D0CD647FF6951AE`.
All six analyses used the same baseline:

| Component | Frozen value |
| --- | --- |
| Spatial pipeline | CONN default MNI pipeline |
| Smoothing | 8 mm FWHM |
| ART displacement threshold | 0.5 mm |
| ART global-signal threshold | z = 3 |
| Denoising | aCompCor |
| White-matter components | 5 |
| CSF components | 5 |
| Temporal band | 0.008–0.09 Hz |
| Linear detrending | order 1 |
| Despiking | disabled |
| Global-signal regression | disabled |
| Slice-time correction | omitted only when BIDS preflight confirmed that `SliceTiming` was absent and omission had been explicitly authorized |
| CONN sources | `networks.DefaultMode.PCC (1,-61,38)` and `networks.DefaultMode.MPFC (1,55,-3)` |
| Evidence corpus | `pipeline-review-2026-09-24-0.1.0-e133450a3d62` |

The evaluated runtime was MATLAB R2023b, SPM25, and CONN 25.b.

## Technical performance

All six full analyses reached technical completion and produced distinct,
versioned results. Calendar durations include power loss, connectivity loss,
queue waits, recovery, and retries; they are not estimates of pure MATLAB
compute time.

| Dataset and analysis | Attempts | Calendar duration | Selected artifacts | Uploaded size |
| --- | ---: | ---: | ---: | ---: |
| WU120 seed-to-voxel | 3 | 18 h 15 min | 119 | 58.3 MB |
| WU120 ROI-to-ROI | 2 | 44 h 30 min | 112 | 23.4 MB |
| Fibromyalgia seed-to-voxel | 3 | 52 h 03 min | 155 | 69.2 MB |
| Fibromyalgia ROI-to-ROI | 3 | 57 h 06 min | 147 | 30.5 MB |
| UCLA seed-to-voxel | 3 | 59 h 37 min | 155 | 69.5 MB |
| UCLA ROI-to-ROI | 3 | 62 h 06 min | 147 | 30.5 MB |

These durations expose an important limitation of this first validation: early
worker recovery behavior inflated elapsed time. They should not be used as a
runtime forecast. The later corrected clinical second-level recalculations each
completed in one attempt.

Before the full evaluation, two three-participant registrations exercised all
six analysis paths as a technical smoke gate. All completed. Their successful
attempts took approximately 69 minutes for each WU120 branch, 53 minutes for
each fibromyalgia branch, and 30–31 minutes for each UCLA branch. Those runs
tested executable wiring and artifact generation only.

## QC review and final samples

The review covered ART output, denoised time series, normalization, registration,
and consistency between the seed-to-voxel and ROI-to-ROI branches. The same QC
decision was applied to both branches of each dataset.

| Dataset | Initial sample | Final sample | Decision summary |
| --- | ---: | ---: | --- |
| WU120 | 15 | 15 | All participants retained. Some scans required closer motion review, but combined evidence did not justify exclusion. |
| Fibromyalgia | 20 (10+10) | 18 (9+9) | Two participants excluded after extensive contiguous artifact sequences were confirmed visually. One retained participant had residual motion that limits sensitivity. |
| UCLA schizophrenia | 20 (10+10) | 16 (8+8) | Four participants excluded for severe temporal artifacts. Two retained participants had substantial residual motion that limits sensitivity. |

This validation reviewed 55 unique participants. Exclusions were scientific QC
decisions made after combined inspection, not automatic consequences of a
single threshold. The paired analytical branches retained identical final
samples, supporting within-dataset comparability.

WU120 tSNR and DVARS were exported as zero in the initial summary. Those fields
were treated as unavailable and were not compared with the clinical datasets.
Zero must not be interpreted as a measured signal-quality value.

The [QC manual](qc-manual.md) additionally documents a legacy exporter limitation:
the contiguous-outlier summary is derived from regressor columns rather than
acquisition-volume indices. Temporal contiguity therefore requires the visual
ART trace or volume-indexed verification. The clinical QC decisions used combined
visual inspection and must not be reproduced from that summary field alone.

## Second-level integrity correction

The first four post-QC clinical recalculations appeared successful but still
used the original 20-participant covariates. The generator had reused existing
CONN covariate names, allowing CONN to select the original covariates. CONN
Pilot was corrected to create execution-unique covariate aliases, and the
computational-revision identifier was advanced so legacy calculations could not
block corrected runs.

The repaired outputs were checked against their actual design matrices:

| Analysis | Participants | Design matrix | Rank | Residual df |
| --- | ---: | ---: | ---: | ---: |
| Fibromyalgia seed-to-voxel | 18 (9+9) | 18 × 2 | 2 | 16 |
| Fibromyalgia ROI-to-ROI | 18 (9+9) | 18 × 2 | 2 | 16 |
| UCLA seed-to-voxel | 16 (8+8) | 16 × 2 | 2 | 14 |
| UCLA ROI-to-ROI | 16 (8+8) | 16 × 2 | 2 | 14 |

This incident demonstrates why technical exit status alone is insufficient. A
future release should make participant count, design rank, contrast dimensions,
and residual degrees of freedom mandatory automatic success invariants.

## Statistical results

### WU120 positive control

PCC seed-to-voxel connectivity was positive at all four coordinates specified
before result inspection:

| Region | MNI coordinate | Fisher z | t(14) | Two-sided p |
| --- | --- | ---: | ---: | ---: |
| PCC | `[1,-61,38]` | 0.9566 | 17.600 | 6.04 × 10⁻¹¹ |
| MPFC | `[1,55,-3]` | 0.2928 | 4.888 | 2.40 × 10⁻⁴ |
| Left lateral parietal | `[-39,-77,33]` | 0.2636 | 4.068 | 1.15 × 10⁻³ |
| Right lateral parietal | `[47,-67,29]` | 0.2899 | 4.590 | 4.21 × 10⁻⁴ |

All four remained significant after Bonferroni correction for the four
predefined coordinates. PCC–MPFC ROI-to-ROI connectivity was also positive:
Fisher `z=0.3338`, `t(14)=6.139`, two-sided `p=2.57×10⁻⁵`.

These results support the prospective WU120 functional checks. They validate
preservation of a canonical DMN signal; they are not a direct replication of
the primary motion-method question in the WU120 source publications.

### Fibromyalgia

For the PCC seed contrast fibromyalgia > control, the largest absolute statistic
was at MNI `[-66,-2,-18]`: Fisher `z=0.2146`, `t(16)=5.587`, uncorrected
two-sided `p=4.09×10⁻⁵`. No voxel survived FDR `q<0.05`, and the peak was not
significant under whole-volume Bonferroni correction.

The PCC–MPFC group difference was Fisher `z=0.1073`, `t(16)=1.434`, two-sided
`p=0.171`.

The benchmark therefore provides no corrected statistical support for the
restricted clinical questions. The uncorrected temporal peak and positive
PCC–MPFC direction remain exploratory observations.

### UCLA schizophrenia

For the PCC seed contrast schizophrenia > control, the largest absolute
statistic was at MNI `[-4,-60,64]`: Fisher `z=0.4162`, `t(14)=6.257`,
uncorrected two-sided `p=2.10×10⁻⁵`. No voxel survived FDR `q<0.05`, and the
peak was not significant under whole-volume Bonferroni correction.

The PCC–MPFC group difference was Fisher `z=0.1111`, `t(14)=0.642`, two-sided
`p=0.531`.

The benchmark therefore provides no corrected statistical support for the
restricted clinical questions. Small final groups and residual motion reduce
sensitivity.

## Comparison with the source literature

| Benchmark | Literature target | Observed correspondence | Assessment |
| --- | --- | --- | --- |
| WU120 | Power and colleagues primarily characterized motion artifacts and censoring strategies. | Canonical PCC-centered DMN and PCC–MPFC connectivity were recovered, and QC was sensitive to motion. | High as a functional positive control; moderate as a paper reproduction because the primary question differs. |
| Fibromyalgia `ds004144` | The full dataset contains 33 patients and 33 controls. A later broad, multivariate analysis reported effects involving DMN, SMN, VIS, and DAN. | The 9+9 final subset and restricted PCC tests had no corrected group result. There is thematic DMN overlap and an uncorrected temporal peak. | Low-to-moderate qualitative correspondence; no statistical reproduction. |
| UCLA CNP `ds000030` | Publications use larger samples and broader connectomic, cortico-subcortical, or dynamic models. | The 8+8 final subset showed no corrected PCC seed or PCC–MPFC group difference. | Low correspondence; this was not a direct reproduction of those models. |

Relevant sources include [Power et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC3849338/),
the [fibromyalgia dataset descriptor](https://doi.org/10.1038/s41597-022-01677-9),
a [later full-cohort fibromyalgia analysis](https://www.sciencedirect.com/science/article/pii/S0925443924005581),
the [UCLA CNP descriptor](https://www.nature.com/articles/sdata2016110),
an [activity/cognition analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC8279516/),
and a [cerebello-thalamo-cortical analysis](https://www.nature.com/articles/s41467-018-06350-7).

## Parameter-selection performance

The six projects contained 42 versioned parameter-decision records, representing
seven unique choices repeated over the shared baseline. Each record contained a
selected value, rationale, evidence identifiers, evidence-corpus version, and an
explicit-observation marker.

| Decision | Selected value | Explicit evidence observations per project |
| --- | ---: | ---: |
| Smoothing | 8 mm | 22 |
| FD threshold | 0.5 mm | 4 |
| Global-signal threshold | z = 3 | 5 |
| White-matter components | 5 | 7 |
| CSF components | 5 | 7 |
| Temporal band | 0.008–0.09 Hz | 24 |
| GSR | disabled | 3 |

The selected baseline agreed with the reserved expert configuration for every
comparable parameter. Slice-timing omission was metadata-dependent and therefore
not comparable. The PCC/MPFC sources answered a different question than the
amygdala sources in the expert sandbox and were also not comparable.

The current evidence supports traceability, consistency, executability, and
agreement with one reserved expert baseline. It does not establish that the
selector can discriminate among reasonable alternatives or outperform CONN
defaults, paper-specific methods, or blinded experts. That requires pre-frozen
comparator arms and parameter-sensitivity analyses.

## Reproducibility outputs

Six final packages were generated after QC and second-level correction. They are
available through the controlled result-export workflow rather than this public
source repository.

| Package | SHA-256 |
| --- | --- |
| WU120 seed-to-voxel | `FD8A7968EB418D6E8DC468D8EA192EEB71B0B23E2A8DBB3F82F35D26C998E8D7` |
| WU120 ROI-to-ROI | `8DBAFF6B0E56671384972D9DE22BA9CE972CB29836562018909CE40E5BF24DC7` |
| Fibromyalgia seed-to-voxel | `D0212B98785841201EE90C9D4DA67ED2C9293CF12DFE74CDEDDB7264E7690136` |
| Fibromyalgia ROI-to-ROI | `2740E8A8D51B8BAC2B480F4FFEA66AC15050D48227D028C6926DB3D918D2EB1D` |
| UCLA seed-to-voxel | `DEEF3CACC48940B4595F3AA97E311141A39644B52033AEBED88558D66F4AEEB4` |
| UCLA ROI-to-ROI | `A32C8AD33F02377C4E0751D2B3613EB49FE6937300F625B07987338D97528C40` |

Seed-to-voxel packages omitted the large `spmT_0001.nii` maps because of the
package-size policy. The maps used for scientific review were preserved in the
controlled evaluation archive. A package hash verifies the exported archive;
it does not independently validate scientific interpretation.

## Overall conclusion

CONN Pilot carried three benchmarks from frozen questions and parameters through
validated execution, subject QC, sample revision, corrected second-level models,
scientific interpretation, and versioned export. It recovered the WU120 DMN
positive control and detected a silent mismatch between the declared post-QC
sample and the actual design matrix.

Scientific performance was uneven. The positive control shows that the automated
pipeline preserves an expected functional-connectivity signal. The two clinical
benchmarks did not reproduce published group findings under these small samples
and narrow contrasts. Their results are inconclusive, not evidence that the
published effects are false.

The defensible claim is that CONN Pilot provides an auditable automated workflow
for supported exploratory analyses. This validation does not establish autonomous
paper replication or universal parameter optimality. Direct replication requires
the complete cohorts, paper-specific covariates, atlases, contrasts, corrections,
and statistical models, all frozen before result inspection.
