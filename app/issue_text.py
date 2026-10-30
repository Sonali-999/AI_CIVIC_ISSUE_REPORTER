"""
issue_text.py
-------------
Generates the complaint Title and Description from a predicted category.

WHY TEMPLATES AND NOT A LANGUAGE MODEL
======================================
The CNN in civic_classifier.py answers "what kind of issue is this?". It cannot
write prose. Previously a hosted LLM wrote the title and description, which cost
an API call per complaint and meant a network outage blocked reporting.

For municipal complaints the prose is highly formulaic - a title naming the
issue and its location, and a description stating the civic impact. That is
exactly the shape templates handle well, and it buys three things a generative
model does not: the output is deterministic (the same photo always yields the
same complaint text, which matters because the text is bound into the
CivicHash-512 integrity digest), it needs no network, and it cannot hallucinate
detail that is not in the photograph.

Every template states impact on hygiene, safety or environment, matching the
field definitions in the project's system prompt.
"""

from __future__ import annotations

# ── Per-concept copy ─────────────────────────────────────────────────────────
# Matched by substring against the predicted category, so a model class named
# "garbage_dump" still resolves to the garbage entry. Order matters: the first
# matching key wins, so more specific concepts are listed before general ones.
TEMPLATES: dict[str, dict[str, str]] = {
    "pothole": {
        "label": "Pothole",
        "title": "Pothole damaging the road surface",
        "impact": (
            "A pothole has formed in the road surface, narrowing the usable "
            "carriageway and forcing vehicles to swerve. It poses an immediate "
            "accident risk to two-wheelers and pedestrians, and will widen "
            "further once rainwater collects in it."
        ),
    },
    "crack": {
        "label": "Road Crack",
        "title": "Cracked road surface requiring repair",
        "impact": (
            "The road surface has cracked and is deteriorating. Untreated "
            "cracks admit water into the sub-base and develop into potholes, "
            "so early resurfacing prevents a far costlier repair later."
        ),
    },
    "road": {
        "label": "Damaged Road",
        "title": "Damaged road surface reported",
        "impact": (
            "The road surface is damaged and unsafe for normal traffic. This "
            "slows vehicle movement, raises the risk of accidents, and will "
            "worsen under continued load and rainfall."
        ),
    },
    "dead_animal": {
        "label": "Dead Animal",
        "title": "Dead animal requiring immediate removal",
        "impact": (
            "A dead animal is lying in a public space. This is an urgent public "
            "health hazard: decomposition attracts flies, stray dogs and "
            "vermin, spreads disease, and produces a severe stench for nearby "
            "residents. Immediate removal and disinfection are required."
        ),
    },
    "garbage": {
        "label": "Garbage",
        "title": "Uncollected garbage accumulating in public space",
        "impact": (
            "Solid waste has accumulated in a public area and has not been "
            "cleared. It breeds flies, mosquitoes and rodents, produces foul "
            "odour, and contaminates surrounding soil and drains, presenting a "
            "direct public-hygiene risk to residents nearby."
        ),
    },
    "waste": {
        "label": "Waste Dumping",
        "title": "Waste dumped in unauthorised location",
        "impact": (
            "Waste has been dumped outside designated collection points. Beyond "
            "the hygiene risk from pests and odour, the material blocks "
            "pedestrian movement and leaches contaminants into nearby drains "
            "and groundwater."
        ),
    },
    "plastic": {
        "label": "Plastic Waste",
        "title": "Plastic waste littering public area",
        "impact": (
            "Plastic waste is scattered across a public area. It does not "
            "degrade, obstructs storm drains and causes waterlogging during "
            "rain, and is frequently ingested by stray and grazing animals."
        ),
    },
    "dump": {
        "label": "Illegal Dumping",
        "title": "Illegal dumping of waste",
        "impact": (
            "Waste has been dumped illegally at an unauthorised location. It "
            "attracts vermin and stray animals, generates foul odour affecting "
            "nearby residents, and contaminates soil and drainage. Illegal "
            "dumping sites also grow rapidly once established, as the presence "
            "of existing waste invites further dumping."
        ),
    },
    "sewer": {
        "label": "Sewer Overflow",
        "title": "Sewer overflow requiring urgent attention",
        "impact": (
            "A sewer line is overflowing or damaged, releasing untreated waste "
            "into a public area. This is a serious public-health emergency "
            "carrying cholera, typhoid and hepatitis risk, contaminating the "
            "street surface and any water source it reaches. Containment and "
            "disinfection are required urgently."
        ),
    },
    "sewage": {
        "label": "Sewage Overflow",
        "title": "Sewage overflow in public area",
        "impact": (
            "Untreated sewage is overflowing into a public area. This is a "
            "serious health emergency carrying cholera, typhoid and hepatitis "
            "risk, contaminating both the street surface and any water source "
            "it reaches. Containment is required urgently."
        ),
    },
    "drain": {
        "label": "Blocked Drainage",
        "title": "Blocked drain requiring clearance",
        "impact": (
            "The drain is blocked and no longer carrying flow. Stagnant water "
            "behind the blockage breeds mosquitoes and will flood the "
            "surrounding street during the next heavy rainfall."
        ),
    },
    "waterlog": {
        "label": "Waterlogging",
        "title": "Waterlogging obstructing public movement",
        "impact": (
            "Standing water has collected and is not draining away. It blocks "
            "safe pedestrian and vehicle movement, conceals road defects "
            "beneath the surface, and becomes a mosquito breeding site within "
            "days if left standing."
        ),
    },
    "flood": {
        "label": "Flooding",
        "title": "Flooding reported in public area",
        "impact": (
            "Flood water has entered a public area, obstructing movement and "
            "risking damage to adjacent property. Submerged road defects and "
            "open drains are hidden beneath the water, creating a serious "
            "hazard to anyone attempting to pass."
        ),
    },
    "water": {
        "label": "Water Supply Issue",
        "title": "Water supply issue requiring attention",
        "impact": (
            "A fault in the water supply infrastructure has been reported. "
            "Beyond wasting treated water, a persistent leak undermines the "
            "road surface around it and risks contaminating the supply."
        ),
    },
    "streetlight": {
        "label": "Streetlight",
        "title": "Non-functional streetlight",
        "impact": (
            "The streetlight is not working, leaving this stretch unlit after "
            "dark. Unlit streets raise the risk of road accidents and reduce "
            "safety for pedestrians, particularly women and elderly residents "
            "travelling at night."
        ),
    },
    "light": {
        "label": "Street Lighting",
        "title": "Street lighting fault reported",
        "impact": (
            "A street lighting fault has left this area inadequately lit, "
            "reducing night-time visibility and public safety for pedestrians "
            "and road users."
        ),
    },
    "wire": {
        "label": "Exposed Wiring",
        "title": "Exposed electrical wiring - safety hazard",
        "impact": (
            "Electrical wiring is exposed in a public area. This is a "
            "life-threatening electrocution hazard, especially during rain or "
            "waterlogging, and demands immediate isolation of the supply."
        ),
    },
    "pole": {
        "label": "Damaged Pole",
        "title": "Damaged electric pole reported",
        "impact": (
            "An electric pole is damaged or leaning. A collapse would cut "
            "supply to the locality and bring live conductors down into a "
            "public space, so inspection is required urgently."
        ),
    },
    "electric": {
        "label": "Electrical Fault",
        "title": "Electrical infrastructure fault",
        "impact": (
            "A fault in public electrical infrastructure has been reported, "
            "presenting both a supply interruption and a safety risk to anyone "
            "nearby."
        ),
    },
    "tree": {
        "label": "Fallen Tree",
        "title": "Fallen tree obstructing public space",
        "impact": (
            "A fallen tree or heavy branch is obstructing a public space. It "
            "blocks movement, may have brought overhead cables down with it, "
            "and risks further collapse until cleared."
        ),
    },
    "vandalism": {
        "label": "Vandalism",
        "title": "Vandalism of public property",
        "impact": (
            "Public property has been defaced or damaged. Beyond the repair "
            "cost borne by the municipality, visible neglect encourages "
            "further vandalism and degrades the character of the area."
        ),
    },
    "parking": {
        "label": "Illegal Parking",
        "title": "Illegally parked vehicle obstructing access",
        "impact": (
            "A vehicle is parked illegally and is obstructing the carriageway "
            "or footpath. This forces pedestrians into moving traffic and can "
            "block emergency-vehicle access to the street."
        ),
    },
    "construction": {
        "label": "Construction Debris",
        "title": "Construction debris left in public space",
        "impact": (
            "Construction material or debris has been left in a public space. "
            "It obstructs movement, generates airborne dust affecting "
            "respiratory health, and blocks drainage when washed into inlets."
        ),
    },
}

GENERIC = {
    "label": "Civic Issue",
    "title": "Civic issue reported by citizen",
    "impact": (
        "A civic issue has been reported in a public area and requires "
        "inspection by the responsible department. Left unattended it risks "
        "affecting public hygiene, safety and the local environment."
    ),
}


def _template(category: str) -> dict[str, str]:
    """Find the copy block for a category, falling back to generic text."""
    key = category.strip().lower().replace("-", "_").replace(" ", "_")
    for needle, block in TEMPLATES.items():
        if needle in key:
            return block
    return GENERIC


def pretty_category(category: str) -> str:
    """Human-facing name for a raw model class label."""
    block = _template(category)
    if block is GENERIC:
        return category.replace("_", " ").strip().title() or GENERIC["label"]
    return block["label"]


def make_title(category: str, location: str | None = None) -> str:
    """
    Build the complaint title.

    The location, when known, is appended so the title alone is enough for a
    department to dispatch a crew without opening the full record.
    """
    title = _template(category)["title"]
    if location:
        # Keep titles to a single readable line - use the first, most specific
        # component of the reverse-geocoded address.
        place = location.split(",")[0].strip()
        if place:
            return f"{title} near {place}"
    return title


def make_description(
    category: str,
    location: str | None = None,
    user_note: str | None = None,
    confidence: float | None = None,
    low_confidence: bool = False,
) -> str:
    """
    Build the complaint description.

    Assembles the impact statement, the reported location, anything the citizen
    typed, and - when the classifier was unsure - an explicit note asking the
    department to confirm the category rather than quietly trusting it.
    """
    parts = [_template(category)["impact"]]

    if location:
        parts.append(f"Reported location: {location}.")

    note = (user_note or "").strip()
    if note:
        parts.append(f'Citizen note: "{note}".')

    if confidence is not None:
        detail = (
            f"Automatically classified as {pretty_category(category)} "
            f"with {confidence:.0%} confidence."
        )
        if low_confidence:
            detail += (
                " Confidence is below the review threshold - please verify the "
                "category and reassign the department if necessary."
            )
        parts.append(detail)

    return " ".join(parts)
