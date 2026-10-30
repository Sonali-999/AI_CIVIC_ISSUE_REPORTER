"""
ai_service.py
-------------
Complaint analysis: photograph in, structured complaint out.

    photograph -> category (trained CNN)
               -> department (deterministic routing table)
               -> title + description (category templates)

This module previously sent every image to a hosted multimodal LLM. It now runs
entirely on this machine against the fine-tuned classifier in
civic_classifier.py. The public shape of the result is unchanged - Title,
Category, Department, Description - so the rest of the application did not need
to change its expectations.

WHY THIS IS BETTER FOR THIS SYSTEM
==================================
  * No API key, no per-complaint cost, no rate limit.
  * Works offline - a municipal office with poor connectivity can still accept
    reports.
  * Deterministic: the same photograph always produces the same complaint text.
    That matters because the text is bound into the CivicHash-512 integrity
    digest, so a non-deterministic generator would make a record's own hash
    irreproducible.
  * The citizen's photograph never leaves the server, which is consistent with
    the encrypt-at-rest guarantee the rest of the system makes.
"""

from __future__ import annotations

from .civic_classifier import ModelNotTrainedError, classify, is_available, warm_up
from .issue_text import make_description, make_title, pretty_category
from .security_audit import log_security_event


def analyze_complaint(
    image_path: str,
    user_note: str | None = None,
    location: str | None = None,
) -> dict:
    """
    Analyse a submitted photograph and produce the complaint fields.

    Parameters
    ----------
    image_path : path to the citizen's uploaded photograph
    user_note  : optional free text the citizen typed
    location   : reverse-geocoded address, folded into the title and description

    Returns
    -------
    dict with keys: title, category, raw_category, department, description,
    confidence, low_confidence, top_k, model

    Raises
    ------
    ModelNotTrainedError : when no checkpoint has been trained yet
    """
    prediction = classify(image_path)

    raw_category = prediction["category"]
    category = pretty_category(raw_category)
    department = prediction["department"]
    confidence = prediction["confidence"]
    low_confidence = prediction["low_confidence"]

    title = make_title(raw_category, location)
    description = make_description(
        raw_category,
        location=location,
        user_note=user_note,
        confidence=confidence,
        low_confidence=low_confidence,
    )

    log_security_event(
        "COMPLAINT_CLASSIFIED",
        f"category={raw_category}, department={department}, "
        f"confidence={confidence:.3f}, low_confidence={low_confidence}",
    )

    return {
        "title": title,
        "category": category,
        "raw_category": raw_category,
        "department": department,
        "description": description,
        "confidence": confidence,
        "low_confidence": low_confidence,
        "top_k": prediction["top_k"],
        "model": prediction.get("model", ""),
    }


__all__ = [
    "analyze_complaint",
    "is_available",
    "warm_up",
    "ModelNotTrainedError",
]
