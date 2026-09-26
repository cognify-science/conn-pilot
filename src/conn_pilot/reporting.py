from __future__ import annotations

import csv
import html
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any


def build_reproducibility_package(
    *,
    job: dict[str, Any],
    project: dict[str, Any],
    review: dict[str, Any],
    artifacts: list[dict[str, Any]],
    method_decisions: list[dict[str, Any]],
) -> tuple[bytes, dict[str, Any]]:
    """Build a compact, machine-readable audit package without copying raw imaging data."""
    created_at = datetime.now(timezone.utc).isoformat()
    subject_rows = review["subject_quality"]["subjects"]
    report = {
        "schema_version": "conn_pilot_reproducibility_package_v1",
        "created_at": created_at,
        "job": {
            "id": job["id"],
            "result_version": job.get("result_version"),
            "state": job.get("state"),
            "summary": job.get("result_summary"),
        },
        "project": {
            "id": project["id"],
            "pipeline_id": project["pipeline_id"],
            "pipeline_version": project["pipeline_version"],
            "spec": project["spec"],
        },
        "review": review,
        "method_decisions": method_decisions,
        "artifacts": [
            {key: value for key, value in artifact.items() if key != "object_key"}
            for artifact in artifacts
        ],
    }
    methods = _methods_markdown(project, review, method_decisions)
    report_html = _report_html(report)
    decisions_csv = _decisions_csv(subject_rows)
    dataset_description = {
        "Name": project["spec"].get("project", {}).get("name", "CONN Pilot derivatives"),
        "BIDSVersion": "1.10.0",
        "DatasetType": "derivative",
        "GeneratedBy": [
            {
                "Name": "CONN Pilot",
                "Version": str(project["pipeline_version"]),
                "Description": "Versioned CONN analysis with human-reviewed subject QC",
            }
        ],
        "SourceDatasets": [{"URL": f"urn:conn-pilot:dataset:{project['dataset_id']}"}],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("report.html", report_html)
        package.writestr("report.json", _json(report))
        package.writestr("methods.md", methods)
        package.writestr("parameters.json", _json(project["spec"].get("parameters", {})))
        package.writestr("literature.json", _json(method_decisions))
        package.writestr("subject-decisions.csv", decisions_csv)
        package.writestr("dataset_description.json", _json(dataset_description))
        package.writestr(
            "artifact-manifest.json",
            _json(report["artifacts"]),
        )
    manifest = {
        "schema_version": "conn_pilot_reproducibility_package_manifest_v1",
        "created_at": created_at,
        "job_id": job["id"],
        "result_version": job.get("result_version"),
        "sample_version": review["sample"]["version"],
        "second_level_output_version": (
            (review["second_level"].get("active_recalculation") or {}).get("output_version")
        ),
        "included_subject_ids": review["sample"]["included_subject_ids"],
        "excluded_subject_ids": review["sample"]["excluded_subject_ids"],
        "files": [
            "report.html", "report.json", "methods.md", "parameters.json",
            "literature.json", "subject-decisions.csv", "dataset_description.json",
            "artifact-manifest.json",
        ],
    }
    return buffer.getvalue(), manifest


def _methods_markdown(
    project: dict[str, Any], review: dict[str, Any], decisions: list[dict[str, Any]]
) -> str:
    spec = project["spec"]
    included = ", ".join(review["sample"]["included_subject_ids"]) or "none"
    excluded = ", ".join(review["sample"]["excluded_subject_ids"]) or "none"
    lines = [
        "# Reproducible methods",
        "",
        f"Pipeline: `{project['pipeline_id']} {project['pipeline_version']}`.",
        f"Research question: {spec.get('project', {}).get('research_question', '')}",
        f"Effective sample: {included}.",
        f"Excluded subjects: {excluded}.",
        f"Sample version: `{review['sample']['version']}`.",
        f"Second-level status: `{review['second_level']['status']}`.",
        "",
        "## Parameters and evidence",
        "",
    ]
    for item in decisions:
        lines.append(
            f"- `{item.get('parameter_path') or item.get('component_id')}` = "
            f"`{json.dumps(item.get('selected_value'), ensure_ascii=False)}`; "
            f"{item.get('rationale', '')} Evidence: {', '.join(item.get('evidence_ids', []))}."
        )
    return "\n".join(lines) + "\n"


def _decisions_csv(subjects: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["subject_id", "decision", "justification", "decided_by", "decided_at"])
    for item in subjects:
        decision = item.get("decision") or {}
        writer.writerow([
            item.get("subject_id"), decision.get("decision"), decision.get("justification"),
            decision.get("decided_by"), decision.get("decided_at"),
        ])
    return output.getvalue()


def _report_html(report: dict[str, Any]) -> str:
    project = report["project"]["spec"].get("project", {})
    review = report["review"]
    rows = []
    for item in review["subject_quality"]["subjects"]:
        decision = item.get("decision") or {}
        metrics = html.escape(json.dumps(item.get("metrics", {}), ensure_ascii=False))
        rows.append(
            "<tr><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                html.escape(str(item.get("subject_id", ""))),
                html.escape(str(decision.get("decision", "needs_review"))), metrics,
            )
        )
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>CONN Pilot report</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17202a}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd1d1;padding:.6rem;text-align:left}}
code{{white-space:pre-wrap}}.badge{{display:inline-block;padding:.25rem .5rem;background:#eef2ff;border-radius:.4rem}}</style></head>
<body><h1>{html.escape(str(project.get('name','CONN Pilot report')))}</h1>
<p>{html.escape(str(project.get('research_question','')))}</p>
<p>Result version: <code>{html.escape(str(report['job'].get('result_version')))}</code></p>
<p>Sample version: <code>{html.escape(str(review['sample']['version']))}</code></p>
<p>Second level: <span class=\"badge\">{html.escape(str(review['second_level']['status']))}</span></p>
<h2>Subject quality review</h2><table><thead><tr><th>Subject</th><th>Decision</th><th>Metrics</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table><h2>Audit record</h2>
<p>This report binds technical completeness, subject decisions, the effective sample and the active second-level version.</p>
</body></html>"""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
