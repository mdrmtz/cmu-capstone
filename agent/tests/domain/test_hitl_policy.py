from __future__ import annotations

from a11y_fixer.domain.hitl_policy import assess_risk


def test_high_risk_rule_routes_to_human_even_with_perfect_score() -> None:
    assessment = assess_risk(rule="color-contrast", file_path="src/app/pages/product/product.component.html", rubric_score=20.0, p_ik=1.0)
    assert assessment.route == "human"
    assert assessment.high_risk_rule is True
    assert any("HIGH_RISK_RULES" in reason for reason in assessment.reasons)


def test_low_confidence_routes_to_human() -> None:
    assessment = assess_risk(rule="button-name", file_path="src/app/pages/blog/blog.component.html", rubric_score=10.0, p_ik=0.9)
    assert assessment.route == "human"
    assert assessment.low_confidence is True


def test_low_p_ik_routes_to_human() -> None:
    assessment = assess_risk(rule="button-name", file_path="src/app/pages/blog/blog.component.html", rubric_score=20.0, p_ik=0.5)
    assert assessment.route == "human"
    assert assessment.low_confidence is True


def test_high_blast_radius_file_routes_to_human() -> None:
    assessment = assess_risk(rule="image-alt", file_path="src/index.html", rubric_score=20.0, p_ik=1.0)
    assert assessment.route == "human"
    assert assessment.high_blast_radius is True


def test_low_risk_rule_high_confidence_narrow_file_routes_auto() -> None:
    assessment = assess_risk(rule="image-alt", file_path="src/app/pages/about/about.component.html", rubric_score=20.0, p_ik=1.0)
    assert assessment.route == "auto"
    assert assessment.high_risk_rule is False
    assert assessment.high_blast_radius is False
    assert assessment.low_confidence is False
