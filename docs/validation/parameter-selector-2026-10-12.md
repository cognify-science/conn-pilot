# Parameter-selector engineering validation — 12 October 2026

This validation covers `context-and-strict-normalization-v2.1` and its numeric
overflow repair. It checks the decision workflow, persistence and public MCP
responses. It does not establish scientific superiority over expert pipelines.

## Recorded test outcome

Tested implementation: [`00761211eb3cb0461c17e625c7d0556403983dd4`](https://github.com/cognify-science/conn-pilot/commit/00761211eb3cb0461c17e625c7d0556403983dd4).
The [GitHub validation run](https://github.com/cognify-science/conn-pilot/actions/runs/38250243968)
passed both jobs.

| Environment | Outcome |
| --- | --- |
| Windows, Python 3.12 | 151 tests discovered: 147 passed and the four database tests skipped because no disposable local PostgreSQL was configured. |
| Linux CI, Python 3.11 | The same portable suite passed; plugin packaging passed. |
| PostgreSQL 16 CI service | All four real-database tests passed, completing coverage of all 151 distinct tests. |
| Authenticated deployed MCP | Revision `context-and-strict-normalization-v2.1` confirmed; 14 current v2 decisions across two technical projects persisted and passed hash verification after JavaScript serialization. |

The integration scenario covers both analysis families and all seven parameter
decisions. The simulated interruption test explicitly verifies rollback before
retry; it is not a claim of testing arbitrary host power loss at every point.

Deployment checks reused two clearly labeled synthetic engineering projects on
the registered reference dataset. Both execution plans validated. The 14 prior
v1 audit records remained verified on the server and unchanged after creating
the new v2 decisions. Requests with unknown citations were rejected and did not
append a decision. The seven historical WU120 method decisions, its completed
result version, and the system's job-state counts were preserved. No CONN job or
subject/scientific acceptance decision was created by this validation.

**Engineering validation is complete for the boundaries above.** Scientific
performance assessment remains a separate benchmark; these test results do not
establish better parameter choices or stronger hypothesis evidence.

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
| Client serialization | An integral numeric value such as `8.0` can serialize as `8` in JavaScript without invalidating a new v2 audit; changing it to a boolean still fails integrity checks. |

The extended tests exposed numeric overflow: sufficiently long numeric text
could normalize to infinity. Conversion now rejects overflowing/nonfinite values
before they can become executable candidates or invalid JSONB content. Tests
also cover large numeric input that previously raised `OverflowError`.

Authenticated deployment testing additionally exposed a v1 hash-format problem:
JavaScript clients serialize integral floats as integers. The v2 audit format
normalizes those equivalent numeric representations before hashing; its format
is explicitly identified by `hash_encoding`. Original v1 records retain their
original hashes and are verified using the original encoder. For v1, verification
requires the original typed JSON representation rather than a reserialized
JavaScript copy. Existing decisions are not retrospectively rewritten.

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
