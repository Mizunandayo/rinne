"""Material priors from mean vertex colour. basis: "heuristic-v1"."""

from __future__ import annotations

import colorsys
from dataclasses import dataclass
from typing import Final

MaterialName = str

#: density kg/m3, friction, restitution
PROPERTIES: Final[dict[MaterialName, tuple[float, float, float]]] = {
    "cardboard": (150.0, 0.55, 0.05),
    "wood": (600.0, 0.50, 0.20),
    "plastic": (950.0, 0.35, 0.40),
    "metal": (2700.0, 0.42, 0.25),
    "glass": (2500.0, 0.30, 0.30),
    "fabric": (300.0, 0.70, 0.05),
    "unknown": (500.0, 0.50, 0.15),
}

_MASS_FLOOR: Final = 1e-4
_MASS_CEILING: Final = 5000.0
_VOLUME_FLOOR: Final = 1e-6


@dataclass(frozen=True)
class MaterialEstimate:
    """Everything a SceneDescription body needs, plus how much to trust it."""

    name: MaterialName
    basis: str
    confidence: float
    density_kilograms_per_cubic_meter: float
    mass_kilograms: float
    friction: float
    restitution: float


def classify(mean_rgb: tuple[float, float, float] | None) -> tuple[MaterialName, float]:
    """First match wins, in the documented order.

    Order matters: the cardboard and wood rules share a hue range and are
    separated by value, so cardboard must be tested first or every brown thing
    becomes wood.
    """
    if mean_rgb is None:
        return "unknown", 0.10

    red, green, blue = (channel / 255.0 for channel in mean_rgb)
    hue_turns, value, saturation = colorsys.rgb_to_hsv(red, green, blue)
    hue = hue_turns * 360.0

    if 15.0 <= hue <= 45.0 and 0.20 <= saturation <= 0.65 and 0.35 <= value <= 0.80:
        return "cardboard", 0.60
    if 15.0 <= hue <= 45.0 and saturation > 0.30 and value < 0.45:
        return "wood", 0.50
    if saturation < 0.12 and value > 0.75:
        return "plastic", 0.45
    if saturation < 0.10 and 0.35 <= value <= 0.70:
        return "metal", 0.35
    if saturation > 0.45:
        return "plastic", 0.50
    return "unknown", 0.15


def estimate(
    mean_rgb: tuple[float, float, float] | None,
    *,
    volume_cubic_meters: float,
    solid_fraction: float,
) -> MaterialEstimate:
    """Classify, then derive mass from the measured volume.

    The solid fraction is a documented guess at how much of the bounding
    surface is actually material rather than air. Day 8's refit loop replaces
    it with a number measured against a real object on a real scale.
    """
    name, confidence = classify(mean_rgb)
    density, friction, restitution = PROPERTIES[name]

    effective_volume = max(volume_cubic_meters * solid_fraction, _VOLUME_FLOOR)
    mass = min(max(density * effective_volume, _MASS_FLOOR), _MASS_CEILING)

    return MaterialEstimate(
        name=name,
        basis="heuristic-v1",
        confidence=confidence,
        density_kilograms_per_cubic_meter=density,
        mass_kilograms=round(mass, 6),
        friction=friction,
        restitution=restitution,
    )
