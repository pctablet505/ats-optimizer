"""Suggestion engine — generates actionable improvement recommendations."""

from src.analyzer.scorer import ScoreResult


def generate_suggestions(score_result: ScoreResult) -> list[str]:
    """Generate actionable suggestions based on the ATS score.

    Args:
        score_result: The result from ATSScorer.score().

    Returns:
        List of suggestion strings, ordered by priority.
    """
    suggestions = []
    breakdown = score_result.breakdown

    # ── Keyword suggestions ──────────────────────────────────

    if breakdown.keyword_match < 60:
        high_priority = [
            kw for kw in score_result.missing_keywords
            if kw.get("importance") == "high"
        ]
        if high_priority:
            kw_names = ", ".join(kw["keyword"] for kw in high_priority[:5])
            suggestions.append(
                f"CRITICAL: Add these missing high-priority keywords: {kw_names}"
            )

        medium_priority = [
            kw for kw in score_result.missing_keywords
            if kw.get("importance") == "medium"
        ]
        if medium_priority:
            kw_names = ", ".join(kw["keyword"] for kw in medium_priority[:5])
            suggestions.append(
                f"Add these missing keywords if applicable: {kw_names}"
            )
    elif breakdown.keyword_match < 80:
        missing_names = [kw["keyword"] for kw in score_result.missing_keywords[:5]]
        if missing_names:
            suggestions.append(
                f"Consider adding: {', '.join(missing_names)} to improve keyword match."
            )

    # ── Section suggestions ──────────────────────────────────

    if breakdown.section_completeness < 70:
        suggestions.append(
            "Your resume is missing key sections. Ensure you have: "
            "Professional Summary, Experience, Education, and Skills sections."
        )
    elif breakdown.section_completeness < 100:
        suggestions.append(
            "Consider adding Certifications or Projects sections if applicable."
        )

    # ── Density suggestions ──────────────────────────────────

    if breakdown.keyword_density < 50:
        suggestions.append(
            "Keywords appear too infrequently. Naturally weave them into "
            "your experience bullet points and summary."
        )
    elif breakdown.keyword_density > 90 and breakdown.keyword_match > 80:
        pass  # Density is fine
    elif breakdown.keyword_density < 70:
        suggestions.append(
            "Increase keyword usage by incorporating relevant terms into "
            "your experience descriptions and achievements."
        )

    # ── Experience suggestions ───────────────────────────────

    if breakdown.experience_relevance < 50:
        suggestions.append(
            "Your experience bullets don't align well with the job description. "
            "Rephrase bullets to highlight relevant achievements and technologies."
        )
    elif breakdown.experience_relevance < 70:
        suggestions.append(
            "Improve experience relevance by adding metrics and using action "
            "verbs that match the JD responsibilities."
        )

    # ── Formatting suggestions ───────────────────────────────

    if score_result.formatting_issues:
        for issue in score_result.formatting_issues:
            suggestions.append(f"Formatting: {issue}")

    # ── Overall encouragement ────────────────────────────────

    if score_result.overall_score >= 80:
        suggestions.append(
            "✅ Good ATS score! Minor tweaks can push it even higher."
        )
    elif score_result.overall_score >= 60:
        suggestions.append(
            "⚠️ Moderate ATS score. Focus on adding missing keywords and "
            "rephrasing experience bullets."
        )
    else:
        suggestions.append(
            "🔴 Low ATS score. This resume needs significant keyword additions "
            "and structural improvements before submitting."
        )

    return suggestions
