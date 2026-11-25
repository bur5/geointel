"""Answers to the GeoIntel expert questionnaire (site page "Lenses"), entered after review.

Each answer is a dict as produced by the questionnaire (``geointel-expert-answer-v1``). Answers
without a stated reason are ignored. Per scenario, yearly hazards are combined by geometric mean
and shown as a separate "expert panel" component with weight 1.
"""

import math

# Reviewed answers, newest last. Empty until the first expert replies.
RESPONSES: list[dict] = []


def _hazard(p: float, years: float) -> float:
    p = min(max(p, 1e-4), 0.999)
    return 1 - (1 - p) ** (1 / years)


def panel_component(key: str, responses: list[dict] | None = None) -> dict | None:
    hazards = []
    for response in RESPONSES if responses is None else responses:
        for answer in response.get("answers", []):
            if answer.get("scenario") != key or not str(answer.get("why") or "").strip():
                continue
            if answer.get("p1y") is not None:
                hazards.append(_hazard(float(answer["p1y"]), 1.0))
            elif answer.get("p5y") is not None:
                hazards.append(_hazard(float(answer["p5y"]), 5.0))
    if not hazards:
        return None
    mean = math.exp(sum(math.log(h) for h in hazards) / len(hazards))
    n = len(hazards)
    return {
        "kind": "panel",
        "annual": round(mean, 4),
        "low": round(min(hazards), 4),
        "high": round(max(hazards), 4),
        "weight": 1.0,
        "detail_ru": f"Анкета экспертов GeoIntel: ответов — {n}; среднее геометрическое.",
        "detail_en": f"GeoIntel expert questionnaire: {n} answer(s); geometric mean.",
        "url": None,
    }
