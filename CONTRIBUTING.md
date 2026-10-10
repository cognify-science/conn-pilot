# Contributing to CONN Pilot

CONN Pilot welcomes issue reports, validation results, documentation fixes, and
carefully scoped code contributions from the scientific community.

## Before proposing a change

Open an issue that states the scientific or operational problem, the affected
contract or pipeline version, the expected behavior, and the evidence needed to
evaluate the change. Do not include participant data, protected health
information, credentials, private host details, or local filesystem paths.

Changes to preprocessing, denoising, seeds, ROIs, contrasts, thresholds, or QC
rules require a clear scientific rationale and tests of the executable contract.
A literature citation alone does not establish that a setting is appropriate for
every dataset or design.

## Development checks

Use Python 3.11 or later, install the project in an isolated environment, and run:

```powershell
python -m unittest discover -s tests -q
python scripts/package_plugin.py
git diff --check
```

Keep each change auditable. Update schemas, documentation, and tests together
when behavior changes. Preserve backward compatibility or introduce a new
versioned contract.

By submitting a contribution, you agree that it may be used in this proprietary
research-preview project under terms established by the repository owner. A
public contribution does not grant a general license to the rest of the source.
