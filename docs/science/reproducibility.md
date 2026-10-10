# Reproducibility outputs

Each run preserves enough information to distinguish the requested experiment,
the generated execution plan, the local attempt, and the reviewed result.

## Versioned records

- project specification and research question;
- pipeline and stage versions;
- dataset inventory without local paths;
- acquisition preflight decisions;
- selected parameter values, rationales, evidence IDs, and corpus snapshots;
- generated MATLAB batch hash;
- CONN/SPM/MATLAB compatibility metadata;
- job events, attempt count, and result version;
- artifact identities and content hashes;
- subject QC evidence and append-only decisions;
- sample version and second-level model version;
- experiment-quality report and scientific decision.

## Reproducibility package

`generate_reproducibility_package` produces a versioned archive containing JSON,
HTML, and PDF reports; methods; parameter provenance; literature identifiers;
QC evidence; current statistical artifacts; and a file manifest with hashes.

The package captures what CONN Pilot did and what the researcher decided. It does
not bundle raw neuroimages, replace the original BIDS dataset, or guarantee that
licensed external software and atlas resources may be redistributed.

## Recovery and repeatability

The remote job is a durable intent. Local MATLAB executions are replaceable
attempts. Internet loss can delay synchronization while MATLAB continues. After a
power loss, the supervisor may start a clean attempt for the same remote job ID.
Artifact registration is content-addressed so result publication can be repeated
without creating conflicting identities.
