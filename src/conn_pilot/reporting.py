from __future__ import annotations

import csv
import html
import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .qc_evidence import normalize_metrics


def build_reproducibility_package(
    *,
    job: dict[str, Any],
    project: dict[str, Any],
    review: dict[str, Any],
    artifacts: list[dict[str, Any]],
    method_decisions: list[dict[str, Any]],
    quality_report: dict[str, Any] | None = None,
    attachments: list[dict[str, Any]] | None = None,
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
            "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"),
            "elapsed_seconds": _elapsed_seconds(job),
        },
        "project": {
            "id": project["id"],
            "pipeline_id": project["pipeline_id"],
            "pipeline_version": project["pipeline_version"],
            "spec": project["spec"],
        },
        "review": review,
        "experiment_quality": quality_report,
        "scientific_audit": (quality_report or {}).get("automatic_audit", {}),
        "method_decisions": method_decisions,
        "artifacts": [
            {key: value for key, value in artifact.items() if key != "object_key"}
            for artifact in artifacts
        ],
    }
    methods = _methods_markdown(project, review, method_decisions)
    report_html = _report_html(report)
    report_pdf = _report_pdf(report)
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
        package.writestr("report.pdf", report_pdf)
        package.writestr("report.json", _json(report))
        package.writestr("experiment-quality.json", _json(quality_report or {}))
        package.writestr("scientific-audit.json", _json(report["scientific_audit"]))
        package.writestr("statistical-results.json", _json({
            "result_version": job.get("result_version"), "sample_version": review["sample"]["version"],
            "second_level_output_version": report["scientific_audit"].get("second_level_output_version"),
            "models": report["scientific_audit"].get("models", []),
        }))
        package.writestr("methods.md", methods)
        package.writestr("parameters.json", _json(project["spec"].get("parameters", {})))
        package.writestr("literature.json", _json(method_decisions))
        package.writestr("subject-decisions.csv", decisions_csv)
        package.writestr("dataset_description.json", _json(dataset_description))
        package.writestr(
            "artifact-manifest.json",
            _json(report["artifacts"]),
        )
        for attachment in attachments or []:
            package.writestr(str(attachment["path"]), attachment["content"])
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
            "report.html", "report.pdf", "report.json", "experiment-quality.json",
            "scientific-audit.json", "statistical-results.json",
            "methods.md", "parameters.json",
            "literature.json", "subject-decisions.csv", "dataset_description.json",
            "artifact-manifest.json",
            *[str(item["path"]) for item in attachments or []],
        ],
        "embedded_artifact_count": len(attachments or []),
        "embedded_artifact_bytes": sum(len(item["content"]) for item in attachments or []),
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
    quality = report.get("experiment_quality") or {}
    quality_state = quality.get("quality_assessment") or {}
    hypothesis = quality.get("hypothesis_assessment") or {}
    audit = quality.get("automatic_audit") or {}
    audit_html = html.escape(json.dumps({
        "model_integrity": audit.get("model_integrity", {"status": "unavailable"}),
        "pending_items": audit.get("pending_items", []),
        "qc_evidence": audit.get("qc_evidence", []),
        "limitations": audit.get("limitations", []),
    }, ensure_ascii=False, indent=2))
    model_rows = []
    for model in audit.get("models", []):
        design, stats = model.get("design") or {}, model.get("statistics") or {}
        cells = [model.get("contrast_name"), model.get("source_identity") or design.get("input_source_indices"),
                 design.get("row_count"), design.get("rank"), design.get("residual_degrees_of_freedom"),
                 design.get("status"), stats.get("status"), (stats.get("multiplicity") or {}).get("family_size"),
                 stats.get("minimum_adjusted_p_value")]
        model_rows.append("<tr>"+"".join("<td>"+html.escape(str(value if value is not None else "n/a"))+"</td>" for value in cells)+"</tr>")
    rows = []
    for item in review["subject_quality"]["subjects"]:
        decision = item.get("decision") or {}
        metrics = html.escape(json.dumps(normalize_metrics(item.get("metrics", {})), ensure_ascii=False))
        rows.append(
            "<tr><td>{}</td><td>{}</td><td><code>{}</code></td></tr>".format(
                html.escape(str(item.get("subject_id", ""))),
                html.escape(str(decision.get("decision", "needs_review"))), metrics,
            )
        )
    return f"""<!doctype html><html><head><meta charset=\"utf-8\"><title>CONN Pilot report</title>
<style>body{{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;color:#17202a}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd1d1;padding:.6rem;text-align:left}}
code,pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.badge{{display:inline-block;padding:.25rem .5rem;background:#eef2ff;border-radius:.4rem}}</style></head>
<body><h1>{html.escape(str(project.get('name','CONN Pilot report')))}</h1>
<p>{html.escape(str(project.get('research_question','')))}</p>
<p>Result version: <code>{html.escape(str(report['job'].get('result_version')))}</code></p>
<p>Sample version: <code>{html.escape(str(review['sample']['version']))}</code></p>
<p>Second level: <span class=\"badge\">{html.escape(str(review['second_level']['status']))}</span></p>
<h2>Calidad e hipótesis</h2>
<p>Calidad para interpretar: <span class=\"badge\">{html.escape(str(quality_state.get('status', 'not_assessed')))}</span></p>
<p>Afirmación confirmatoria permitida: <strong>{'sí' if quality_state.get('permits_confirmatory_claim') else 'no'}</strong></p>
<p>Hipótesis: <span class=\"badge\">{html.escape(str(hypothesis.get('status', 'not_assessed')))}</span></p>
<p>{html.escape(str(hypothesis.get('conclusion', 'No evaluada.')))}</p>
<h2>Automatic scientific audit</h2><pre>{audit_html}</pre>
<table><thead><tr><th>Contrast</th><th>Source</th><th>N</th><th>Rank</th><th>Residual df</th><th>Model</th><th>Statistics</th><th>Tests</th><th>Minimum q</th></tr></thead>
<tbody>{''.join(model_rows)}</tbody></table>
<p>Statistical estimates, testing families, corrections and artifact hashes are in statistical-results.json.
An unavailable metric is not zero. Exploratory summaries do not establish hypothesis support.</p>
<h2>Subject quality review</h2><table><thead><tr><th>Subject</th><th>Decision</th><th>Metrics</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table><h2>Audit record</h2>
<p>This report binds technical completeness, subject decisions, the effective sample and the active second-level version.</p>
</body></html>"""


def _report_pdf(report: dict[str, Any]) -> bytes:
    """Render a compact archival PDF; detailed machine-readable evidence remains in JSON."""
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="CONN Pilot reproducibility report",
        author="CONN Pilot",
    )
    project = report["project"]["spec"].get("project", {})
    review = report["review"]
    quality = report.get("experiment_quality") or {}
    quality_state = quality.get("quality_assessment") or {}
    hypothesis = quality.get("hypothesis_assessment") or {}
    audit = quality.get("automatic_audit") or {}
    story = [
        Paragraph(html.escape(str(project.get("name", "CONN Pilot report"))), styles["Title"]),
        Paragraph(html.escape(str(project.get("research_question", ""))), styles["BodyText"]),
        Spacer(1, 5 * mm),
        Paragraph("Version binding", styles["Heading2"]),
        Paragraph(
            f"Result: <font name='Courier'>{html.escape(str(report['job'].get('result_version')))}</font><br/>"
            f"Sample: <font name='Courier'>{html.escape(str(review['sample']['version']))}</font><br/>"
            f"Second level: {html.escape(str(review['second_level']['status']))}",
            styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Calidad e hipótesis", styles["Heading2"]),
        Paragraph(
            f"Calidad para interpretar: {html.escape(str(quality_state.get('status', 'not_assessed')))}<br/>"
            f"Afirmación confirmatoria permitida: {'sí' if quality_state.get('permits_confirmatory_claim') else 'no'}<br/>"
            f"Hipótesis: {html.escape(str(hypothesis.get('status', 'not_assessed')))}<br/>"
            f"{html.escape(str(hypothesis.get('conclusion', 'No evaluada.')))}",
            styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Automatic scientific audit", styles["Heading2"]),
        Paragraph(
            f"Executed model: {html.escape(str((audit.get('model_integrity') or {}).get('status', 'unavailable')))}<br/>"
            f"Pending: {html.escape(', '.join(audit.get('pending_items', [])) or 'See detailed audit')}<br/>"
            "Missing measurements are unavailable, not zero. Estimates, testing families, "
            "correction scope and artifact hashes are recorded in statistical-results.json. "
            "Exploratory summaries do not establish hypothesis support.", styles["BodyText"],
        ),
        Spacer(1, 5 * mm),
        Paragraph("Subject quality review", styles["Heading2"]),
    ]
    rows = [["Subject", "Decision", "Outliers", "tSNR", "DVARS mean"]]
    for item in review["subject_quality"]["subjects"]:
        decision = item.get("decision") or {}
        metrics = normalize_metrics(item.get("metrics") or {})
        rows.append([
            str(item.get("subject_id", "")),
            str(decision.get("decision") or "needs_review"),
            _metric(metrics, "outlier_percent", suffix="%"),
            _metric(metrics, "tsnr_median"),
            _metric(metrics, "dvars_mean"),
        ])
    table = Table(rows, repeatRows=1, colWidths=[35 * mm, 35 * mm, 28 * mm, 28 * mm, 35 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#AAB4C3")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
    ]))
    story.extend([table, Spacer(1, 5 * mm)])
    model_rows = [["Contrast / source", "N / rank", "df", "Model / stats", "Tests", "Min q"]]
    for model in audit.get("models", []):
        design, stats = model.get("design") or {}, model.get("statistics") or {}
        source = model.get("source_identity") or design.get("input_source_indices", [])
        model_rows.append([
            Paragraph(html.escape(str(model.get("contrast_name", "n/a")))+"<br/>"+html.escape(str(source)), styles["BodyText"]),
            f"{design.get('row_count', 'n/a')} / {design.get('rank', 'n/a')}",
            str(design.get("residual_degrees_of_freedom", "n/a")),
            Paragraph(html.escape(str(design.get("status", "unverified")))+"<br/>"+html.escape(str(stats.get("status", "unavailable"))), styles["BodyText"]),
            str((stats.get("multiplicity") or {}).get("family_size", "n/a")),
            _metric(stats, "minimum_adjusted_p_value"),
        ])
    if len(model_rows) > 1:
        model_table = Table(model_rows, repeatRows=1, colWidths=[60*mm, 20*mm, 12*mm, 40*mm, 15*mm, 14*mm])
        model_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF8")),
            ("GRID", (0, 0), (-1, -1), .5, colors.HexColor("#AAB4C3")),
            ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        story.extend([Paragraph("Executed models and exploratory statistics", styles["Heading2"]), model_table,
                      Paragraph("Min q is within-model BH only; ROI intervals and individual effects are in statistical-results.json.", styles["BodyText"]), Spacer(1, 5*mm)])
    included = ", ".join(review["sample"]["included_subject_ids"]) or "none"
    excluded = ", ".join(review["sample"]["excluded_subject_ids"]) or "none"
    story.extend([
        Paragraph("Effective sample", styles["Heading2"]),
        Paragraph(
            f"Included: {html.escape(included)}<br/>Excluded: {html.escape(excluded)}",
            styles["BodyText"],
        ),
        Spacer(1, 4 * mm),
        Paragraph(
            "This report binds technical completeness, subject decisions, the effective sample "
            "and the active second-level version. The ZIP also contains the detailed audit record.",
            styles["BodyText"],
        ),
    ])
    def page_footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#C7CED9"))
        canvas.line(16 * mm, 11 * mm, A4[0] - 16 * mm, 11 * mm)
        canvas.setFillColor(colors.HexColor("#596273"))
        canvas.setFont("Helvetica", 7)
        canvas.drawString(16 * mm, 7 * mm, f"Generated {report['created_at']}")
        canvas.drawRightString(A4[0] - 16 * mm, 7 * mm, f"Page {document.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_footer, onLaterPages=page_footer)
    return buffer.getvalue()


def _metric(metrics: dict[str, Any], name: str, *, suffix: str = "") -> str:
    value = metrics.get(name)
    if value is None:
        return "n/a"
    if isinstance(value, float):
        if name == "minimum_adjusted_p_value":
            return f"{value:.3g}"
        return f"{value:.3f}{suffix}"
    return f"{value}{suffix}"


def _elapsed_seconds(job: dict[str, Any]) -> float | None:
    try:
        start = datetime.fromisoformat(str(job["started_at"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(job["finished_at"]).replace("Z", "+00:00"))
        seconds = (end-start).total_seconds()
        return seconds if seconds >= 0 else None
    except (ValueError, KeyError, TypeError):
        return None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n"
