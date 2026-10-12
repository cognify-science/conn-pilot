# Parameter-selector engineering validation — 12 October 2026

This validation covers `context-and-strict-normalization-v2` and its numeric
overflow repair. It checks the decision workflow, persistence and public MCP
responses. It does not establish scientific superiority over expert pipelines.

## Coverage

| Boundary | Evidence exercised |
| --- | --- |
| Both supported workflows | Every offered option for all seven guided parameters in seed-to-voxel and ROI-to-ROI, using the frozen reviewed corpus. |
| Value interpretation | Units, ambiguous intervals, signs, inferred/missing evidence, invalid identifiers, Nyquist and text/numeric overflow. |
| Context and history | Changed acquisition TR, dataset fingerprint, question, seeds, sample/contrast and executable contract; a newer corpus preserves a historical audit. |
| MCP | Create synthetic projects, retrieve guidance, resolve seven choices, retrieve decisions and generate a validated execution plan. Changed context blocks submission. |
| Export | A reproducibility ZIP retains the exact citations and selection audits; hashes verify after JSON serialization. |
| PostgreSQL 16 | JSONB round-trip and a fresh service retain all choices; schema migration is idempotent; legacy decisions remain audit-unavailable; owner isolation is enforced. |
| Interruption | A simulated failure after inserting a decision rolls back both the decision and project mutation; the next attempt succeeds. |

The extended tests exposed numeric overflow: sufficiently long numeric text
could normalize to infinity. Conversion now rejects overflowing/nonfinite values
before they can become executable candidates or invalid JSONB content. Tests
also cover large numeric input that previously raised `OverflowError`.

## Reproduction

Run the portable suite from a checkout with dependencies installed:

```sh
python -m unittest discover -s tests -q
python scripts/package_plugin.py
```

The `parameter-postgres` job in `.github/workflows/test.yml` provisions a
disposable PostgreSQL 16 database and runs:

```sh
python -m unittest discover -s tests -p test_parameter_postgres.py -v
```

Without `CONN_PILOT_TEST_DATABASE_URL`, only the four real-database tests skip;
they must pass in their separate CI job. They accept only a loopback database
named `conn_pilot_test`, create a unique isolated schema, and remove only that
schema afterward. Never point these tests at a research database.

Synthetic choices and exports are test fixtures. They do not constitute
investigator decisions about benchmark subjects or hypotheses. Neither this
test suite nor the selector test scenarios execute MATLAB/CONN.

## Scientific interpretation

Passing these checks supports software reliability, provenance consistency and
the stated decision boundaries. Citation extraction accuracy, rationale quality,
expert-rated applicability, downstream QC and outcome stability require the
separate [scientific evaluation protocol](../science/parameter-selector-evaluation.md).

Deployment verification must additionally inspect authenticated MCP responses:
the guidance revision and evidence assessments must be present. A successful
GitHub run alone does not attest to the deployed service version.
