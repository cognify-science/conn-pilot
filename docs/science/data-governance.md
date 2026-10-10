# Data governance, ethics, and licensing

CONN Pilot separates public software documentation, identity-scoped metadata,
local source data, and controlled result artifacts. Scientific reproducibility
does not override participant consent, data-use agreements, institutional
policy, or third-party licenses.

## Data locations and disclosure

Source BIDS neuroimages remain on an authorized worker. The control plane stores
a sanitized inventory, scientific specifications, job state, decisions, and
selected artifacts. This public repository does not contain raw neuroimages,
worker dataset registries, execution databases, private paths, participant-level
QC images, or credentials.

The public benchmark sources are listed in
[preloaded datasets](preloaded-datasets.md). Their OpenNeuro accession, snapshot,
license, citation, known issues, and ethics statements remain authoritative for
the source data. CONN Pilot does not relicense those datasets.

## Researcher responsibilities

Before registering institutional data or exporting participant-level material,
the researcher or institution must determine:

- whether consent permits the proposed processing and sharing;
- whether data are adequately de-identified;
- whether the data-use agreement permits remote metadata or derivative transfer;
- whether cross-border or cloud processing restrictions apply;
- which parties may inspect QC images and derivatives;
- how long records and exports may be retained;
- how incidents and withdrawal requests will be handled;
- how the source dataset, software, atlas, and papers must be cited.

An authenticated account and a successful job do not establish ethical or legal
permission to analyze a dataset.

## Public benchmark manifests

Exact participant lists improve computational reproduction but can also enable
linkage across public phenotypic records. The public documentation therefore
reports cohort composition and aggregate QC. Exact selection manifests and
participant-level evidence belong in a controlled reproducibility package unless
a dataset-specific review concludes that public release is appropriate.

For an independently reproduced benchmark, the controlled manifest should record:

- OpenNeuro accession and exact snapshot or DOI;
- stable source participant identifiers;
- inclusion and exclusion rules;
- selected sessions, tasks, runs, and files;
- source file hashes or a reproducible retrieval manifest;
- all post-QC decisions with rationale and version;
- resulting sample version.

## Derived artifacts

Statistical maps, ROI matrices, QC screenshots, and denoised summaries can remain
sensitive or fall under source-data terms. Before public release, each artifact
class should be reviewed for identifiability, licensing, scientific necessity,
and disclosure risk. A checksum may be public even when the corresponding
controlled archive is not.

## Software and citation

This repository uses a proprietary research-preview license. CONN Toolbox,
MATLAB, SPM, OpenNeuro datasets, atlases, and cited papers are separate works.
Their licenses and citation requirements must be followed independently. The
software citation is defined in [`CITATION.cff`](../../CITATION.cff).
