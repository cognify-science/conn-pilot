from __future__ import annotations

from typing import Any


HYPOTHESIS_STATUSES = {
    "not_evaluable_quality",
    "not_evaluable_inference",
    "inconclusive",
    "evidence_compatible",
    "evidence_not_compatible",
}


def build_experiment_quality_report(
    *, job: dict[str, Any], project: dict[str, Any], review: dict[str, Any]
) -> dict[str, Any]:
    """Assess quality and hypothesis evidence without overstating scientific claims."""
    spec = project.get("spec") or {}
    project_spec = spec.get("project") or {}
    result_summary = job.get("result_summary") or {}
    result_version = job.get("result_version")
    sample = review.get("sample") or {}
    sample_version = sample.get("version")
    subjects = (review.get("subject_quality") or {}).get("subjects") or []
    included = sample.get("included_subject_ids") or []
    excluded = sample.get("excluded_subject_ids") or []

    gates = _quality_gates(review)
    quality_blockers = [gate["reason"] for gate in gates if not gate["passed"]]
    quality_permits_interpretation = not quality_blockers
    cautions = _quality_cautions(spec, review)
    hypothesis = _hypothesis_definition(spec)
    sample_adequacy_established = bool(hypothesis.get("sample_adequacy"))
    assessment = _hypothesis_assessment(
        result_summary=result_summary,
        result_version=result_version,
        sample_version=sample_version,
        hypothesis=hypothesis,
        quality_permits_interpretation=quality_permits_interpretation,
        quality_blockers=quality_blockers,
        cautions=cautions,
    )
    scientific = review.get("scientific_acceptance") or {}

    return {
        "schema_version": "conn_pilot_experiment_quality_report_v1",
        "job_id": job.get("id"),
        "project_id": project.get("id"),
        "result_version": result_version,
        "sample_version": sample_version,
        "research_question": project_spec.get("research_question"),
        "hypothesis": hypothesis,
        "quality_assessment": {
            "status": (
                "sufficient_for_interpretation"
                if quality_permits_interpretation
                else "insufficient_for_interpretation"
            ),
            "permits_hypothesis_assessment": quality_permits_interpretation,
            "sample_adequacy_established": sample_adequacy_established,
            "permits_confirmatory_claim": (
                quality_permits_interpretation and sample_adequacy_established
            ),
            "gates": gates,
            "blocking_reasons": quality_blockers,
            "cautions": cautions,
            "subject_count": len(subjects),
            "included_subject_count": len(included),
            "excluded_subject_count": len(excluded),
        },
        "hypothesis_assessment": assessment,
        "investigator_scientific_decision": {
            "status": scientific.get("status", "needs_review"),
            "decision": scientific.get("current_decision"),
            "note": (
                "La aceptación científica del investigador se informa por separado y no se "
                "interpreta automáticamente como confirmación de la hipótesis."
            ),
        },
        "interpretation_policy": {
            "technical_completion_is_not_hypothesis_confirmation": True,
            "statistical_significance_alone_is_not_validation": True,
            "absence_of_significance_is_not_proof_of_no_effect": True,
            "allowed_hypothesis_statuses": sorted(HYPOTHESIS_STATUSES),
        },
    }


def _quality_gates(review: dict[str, Any]) -> list[dict[str, Any]]:
    technical = review.get("technical_completeness") or {}
    subject_quality = review.get("subject_quality") or {}
    sample = review.get("sample") or {}
    second_level = review.get("second_level") or {}
    included = sample.get("included_subject_ids") or []
    return [
        {
            "id": "technical_completeness",
            "passed": bool(technical.get("passed")),
            "reason": "La ejecución o los artefactos técnicos requeridos están incompletos.",
            "evidence": technical.get("details", {}),
        },
        {
            "id": "subject_quality_review",
            "passed": bool(subject_quality.get("complete")),
            "reason": "La revisión de calidad por sujeto todavía tiene decisiones pendientes.",
            "evidence": {
                "unresolved_subject_ids": subject_quality.get("unresolved_subject_ids", [])
            },
        },
        {
            "id": "non_empty_effective_sample",
            "passed": bool(included),
            "reason": "La muestra efectiva no contiene sujetos aceptados.",
            "evidence": {"included_subject_count": len(included)},
        },
        {
            "id": "current_second_level",
            "passed": second_level.get("status") == "current" and not second_level.get("blocked"),
            "reason": "El resultado de segundo nivel no corresponde a la muestra efectiva vigente.",
            "evidence": {
                "status": second_level.get("status"),
                "blocked": bool(second_level.get("blocked")),
            },
        },
    ]


def _quality_cautions(spec: dict[str, Any], review: dict[str, Any]) -> list[dict[str, Any]]:
    cautions: list[dict[str, Any]] = []
    hypothesis = spec.get("hypothesis") or {}
    if not hypothesis.get("sample_adequacy"):
        cautions.append(
            {
                "id": "sample_adequacy_not_established",
                "message": (
                    "No se documentó potencia, precisión objetivo ni otro criterio previo de "
                    "adecuación muestral; el mínimo técnico de ejecución no demuestra potencia científica."
                ),
            }
        )
    if (review.get("sample") or {}).get("excluded_subject_ids"):
        cautions.append(
            {
                "id": "sample_changed_after_qc",
                "message": (
                    "La muestra cambió después del control de calidad; deben considerarse sesgo de "
                    "selección y sensibilidad a las exclusiones."
                ),
            }
        )
    return cautions


def _hypothesis_definition(spec: dict[str, Any]) -> dict[str, Any]:
    explicit = spec.get("hypothesis") if isinstance(spec.get("hypothesis"), dict) else {}
    contrasts = (spec.get("design") or {}).get("contrasts") or []
    return {
        "statement": explicit.get("statement")
        or (spec.get("project") or {}).get("research_question"),
        "target_contrast": explicit.get("target_contrast"),
        "expected_direction": explicit.get("expected_direction"),
        "decision_rule": explicit.get("decision_rule"),
        "sample_adequacy": explicit.get("sample_adequacy"),
        "available_contrasts": [
            {
                "name": item.get("name"),
                "effects": item.get("effects", []),
                "weights": item.get("weights", []),
                "rationale": item.get("rationale"),
            }
            for item in contrasts
            if isinstance(item, dict)
        ],
        "fully_operationalized": bool(
            explicit.get("statement")
            and explicit.get("target_contrast")
            and explicit.get("expected_direction")
            and explicit.get("decision_rule")
        ),
    }


def _hypothesis_assessment(
    *,
    result_summary: dict[str, Any],
    result_version: Any,
    sample_version: Any,
    hypothesis: dict[str, Any],
    quality_permits_interpretation: bool,
    quality_blockers: list[str],
    cautions: list[dict[str, Any]],
) -> dict[str, Any]:
    if not quality_permits_interpretation:
        return _assessment(
            "not_evaluable_quality",
            "La calidad o vigencia de los resultados no permite evaluar la hipótesis.",
            quality_blockers,
            None,
            False,
        )

    inference = result_summary.get("hypothesis_assessment")
    if not isinstance(inference, dict):
        return _assessment(
            "not_evaluable_inference",
            (
                "Los controles de calidad permiten revisar el análisis, pero no hay evidencia "
                "inferencial estructurada y versionada para verificar la hipótesis."
            ),
            _missing_inference_requirements(hypothesis, None, cautions),
            None,
            False,
        )

    bound = (
        inference.get("result_version") == result_version
        and inference.get("sample_version") == sample_version
    )
    evidence = inference.get("evidence") if isinstance(inference.get("evidence"), dict) else {}
    complete_evidence = _complete_inferential_evidence(evidence)
    if not bound or not complete_evidence:
        return _assessment(
            "not_evaluable_inference",
            "La evidencia inferencial existe, pero está incompleta o no corresponde a las versiones vigentes.",
            _missing_inference_requirements(hypothesis, inference, cautions),
            evidence or None,
            False,
        )

    if not hypothesis.get("fully_operationalized"):
        return _assessment(
            "inconclusive",
            (
                "Hay evidencia inferencial utilizable, pero la hipótesis no posee contraste, "
                "dirección y regla de decisión predefinidos suficientes para clasificarla."
            ),
            _missing_inference_requirements(hypothesis, inference, cautions),
            evidence,
            False,
        )

    status, evaluation_error = _evaluate_evidence(hypothesis, evidence)
    if evaluation_error:
        return _assessment(
            "not_evaluable_inference",
            "La evidencia inferencial no satisface la regla de decisión registrada.",
            [evaluation_error, *[item["message"] for item in cautions]],
            evidence,
            False,
        )
    assert status is not None
    narrative = {
        "evidence_compatible": "La evidencia es compatible con la hipótesis especificada.",
        "evidence_not_compatible": (
            "La evidencia significativa tiene dirección opuesta a la hipótesis especificada."
        ),
        "inconclusive": (
            "La evidencia no alcanza la regla de decisión; esto no demuestra ausencia de efecto."
        ),
    }[status]
    return _assessment(
        str(status),
        str(narrative),
        [item["message"] for item in cautions],
        evidence,
        status in {"evidence_compatible", "evidence_not_compatible", "inconclusive"},
    )


def _assessment(
    status: str,
    conclusion: str,
    limitations: list[str],
    evidence: dict[str, Any] | None,
    conclusion_permitted: bool,
) -> dict[str, Any]:
    return {
        "status": status,
        "conclusion": conclusion,
        "conclusion_permitted": conclusion_permitted,
        "evidence": evidence,
        "limitations": limitations,
        "supports_hypothesis": (
            True if status == "evidence_compatible"
            else False if status == "evidence_not_compatible"
            else None
        ),
        "validation_language": (
            "La evidencia puede describirse como compatible con la hipótesis; no prueba su verdad."
            if status == "evidence_compatible"
            else "No corresponde afirmar que la hipótesis fue validada."
        ),
    }


def _complete_inferential_evidence(evidence: dict[str, Any]) -> bool:
    has_effect = isinstance(evidence.get("effect_estimate"), (int, float))
    interval = evidence.get("confidence_interval")
    has_interval = (
        isinstance(interval, dict)
        and isinstance(interval.get("low"), (int, float))
        and isinstance(interval.get("high"), (int, float))
        and isinstance(interval.get("level"), (int, float))
    )
    has_test = isinstance(evidence.get("p_value"), (int, float))
    multiplicity = evidence.get("multiplicity")
    has_multiplicity = isinstance(multiplicity, dict) and bool(multiplicity.get("method"))
    return bool(
        evidence.get("contrast_name")
        and has_effect
        and (has_interval or has_test)
        and has_multiplicity
    )


def _evaluate_evidence(
    hypothesis: dict[str, Any], evidence: dict[str, Any]
) -> tuple[str | None, str | None]:
    if evidence.get("contrast_name") != hypothesis.get("target_contrast"):
        return None, "El contraste de la evidencia no coincide con el contraste objetivo de la hipótesis."
    rule = hypothesis.get("decision_rule") or {}
    alpha = rule.get("alpha")
    if not isinstance(alpha, (int, float)) or isinstance(alpha, bool) or not 0 < float(alpha) <= 1:
        return None, "La regla de decisión no contiene un alfa válido."
    multiplicity = evidence.get("multiplicity") or {}
    expected_method = str(rule.get("multiplicity_method", "")).strip().casefold()
    observed_method = str(multiplicity.get("method", "")).strip().casefold()
    if expected_method != observed_method:
        return None, "El método de multiplicidad aplicado no coincide con el predefinido."
    uncorrected = expected_method in {"none", "uncorrected", "raw"}
    p_value = evidence.get("p_value") if uncorrected else multiplicity.get("adjusted_p_value")
    if not isinstance(p_value, (int, float)) or isinstance(p_value, bool) or not 0 <= float(p_value) <= 1:
        label = "p_value" if uncorrected else "multiplicity.adjusted_p_value"
        return None, f"La evidencia no contiene un {label} válido para aplicar la regla."
    effect = float(evidence["effect_estimate"])
    direction = hypothesis.get("expected_direction")
    direction_matches = (
        (direction == "positive" and effect > 0)
        or (direction == "negative" and effect < 0)
        or (direction == "nonzero" and effect != 0)
    )
    if float(p_value) > float(alpha):
        return "inconclusive", None
    return ("evidence_compatible" if direction_matches else "evidence_not_compatible"), None


def _missing_inference_requirements(
    hypothesis: dict[str, Any],
    inference: dict[str, Any] | None,
    cautions: list[dict[str, Any]],
) -> list[str]:
    missing: list[str] = []
    if not hypothesis.get("fully_operationalized"):
        missing.append(
            "Falta operacionalizar la hipótesis con contraste objetivo, dirección esperada y regla de decisión."
        )
    if not inference:
        missing.append(
            "Falta extraer el efecto, su incertidumbre, la prueba estadística y la corrección por multiplicidad."
        )
    else:
        evidence = inference.get("evidence") if isinstance(inference.get("evidence"), dict) else {}
        if not _complete_inferential_evidence(evidence):
            missing.append(
                "La evidencia debe incluir contraste, estimación del efecto, intervalo o prueba y método de multiplicidad."
            )
    missing.extend(item["message"] for item in cautions)
    return missing
