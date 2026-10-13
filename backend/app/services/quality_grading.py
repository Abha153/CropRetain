"""
Crop quality assessment from an actual uploaded image.

HONESTY NOTE (see README): this is a heuristic pixel-statistics analyzer,
NOT a trained computer-vision / deep-learning model. It genuinely opens and
analyzes the bytes of whatever image the user uploads (color distribution,
brightness, texture variance, and how well the dominant color matches the
expected color range for the selected crop) -- it does not fabricate a
result from the filename or crop name alone the way the previous
placeholder implementation did. Every field in the response is derived
from the real uploaded pixels. It is intentionally labeled `demo_mode`
throughout the API and UI so it is never mistaken for a trained model.

Swapping in a real CNN/ViT classifier later means replacing `_score_image()`
below with a model inference call -- the request/response contract
(`analyze_image()`) does not need to change.
"""
import io
from typing import Optional

from PIL import Image, ImageFilter

MAX_IMAGE_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

# Approximate expected dominant hue range (degrees, 0-360) for each crop's
# ripe/harvest-ready produce, used only to score color-match -- a simple,
# transparent heuristic, not a trained model.
EXPECTED_HUE_RANGES = {
    "Tomato": [(0, 20), (340, 360)],
    "Paddy (Rice)": [(35, 55)],
    "Wheat": [(35, 50)],
    "Potato": [(25, 48)],
    "Onion": [(270, 330), (0, 30)],
    "Soybean": [(55, 95)],
    "Maize": [(42, 60)],
    "Chana (Gram)": [(28, 48)],
    "Groundnut": [(22, 42)],
    "Sugarcane": [(70, 150)],
    "Cotton": [(0, 360)],  # near-white; scored on low saturation instead, see below
    "Chickpea": [(28, 48)],
    "Pigeon Pea": [(35, 55)],
    "Mustard": [(45, 65)],
    "Lentil": [(15, 40)],
    "Green Peas": [(75, 130)],
    "Brinjal": [(270, 320)],
    "Chilli": [(0, 15), (345, 360)],
    "Okra": [(75, 130)],
    "Cabbage": [(75, 130)],
    "Cauliflower": [(0, 360)],  # near-white; scored on low saturation instead
}
LOW_SATURATION_CROPS = {"Cotton", "Cauliflower"}


class InvalidImageError(Exception):
    pass


def validate_upload(content_type: str, size_bytes: int):
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise InvalidImageError(f"Unsupported file type '{content_type}'. Please upload a JPG, PNG, or WEBP image.")
    if size_bytes > MAX_IMAGE_BYTES:
        raise InvalidImageError(f"Image is too large ({size_bytes / 1_048_576:.1f} MB). Maximum size is 8 MB.")
    if size_bytes == 0:
        raise InvalidImageError("The uploaded file is empty.")


def _hue_in_ranges(hue: float, ranges) -> bool:
    return any(lo <= hue <= hi for lo, hi in ranges)


def _score_image(img: Image.Image, crop: str) -> dict:
    """Real, deterministic analysis of the actual uploaded image pixels."""
    img = img.convert("RGB")
    width, height = img.size

    # Downsample for fast, stable statistics -- doesn't change the actual
    # analysis outcome meaningfully, just avoids scanning multi-megapixel images.
    thumb = img.resize((120, 120))
    hsv = thumb.convert("HSV")

    pixels_rgb = list(thumb.getdata())
    pixels_hsv = list(hsv.getdata())
    n = len(pixels_rgb)

    # Brightness: mean of RGB, 0-255 -> 0-100
    brightness = sum(sum(p) / 3 for p in pixels_rgb) / n
    brightness_pct = round((brightness / 255) * 100, 1)

    # Saturation: mean S channel, 0-255 -> 0-100
    saturation = sum(p[1] for p in pixels_hsv) / n
    saturation_pct = round((saturation / 255) * 100, 1)

    # Texture/sharpness proxy: apply an edge filter and measure the mean
    # edge intensity -- a very blurry/flat photo scores low, a photo with
    # natural produce texture/detail scores higher.
    edges = thumb.convert("L").filter(ImageFilter.FIND_EDGES)
    edge_pixels = list(edges.getdata())
    texture_score = min(sum(edge_pixels) / len(edge_pixels) / 60 * 100, 100)
    texture_pct = round(texture_score, 1)

    # Color match: fraction of pixels whose hue falls in the crop's expected
    # range (hue channel in PIL's HSV mode is 0-255, convert to degrees).
    ranges = EXPECTED_HUE_RANGES.get(crop, [(0, 360)])
    if crop in LOW_SATURATION_CROPS:
        # near-white produce: score by LOW saturation instead of hue match
        low_sat_count = sum(1 for p in pixels_hsv if p[1] < 90)
        color_match_pct = round((low_sat_count / n) * 100, 1)
    else:
        matches = 0
        for p in pixels_hsv:
            hue_deg = (p[0] / 255) * 360
            if p[1] < 25:  # near-grey pixel, skip from color-match calc
                continue
            if _hue_in_ranges(hue_deg, ranges):
                matches += 1
        saturated_count = sum(1 for p in pixels_hsv if p[1] >= 25)
        color_match_pct = round((matches / saturated_count) * 100, 1) if saturated_count else 0.0

    # Brightness penalty: too dark or blown-out photos are penalized
    if 35 <= brightness_pct <= 85:
        brightness_score = 100
    else:
        brightness_score = max(0, 100 - abs(60 - brightness_pct) * 2)

    composite = round(
        0.45 * color_match_pct + 0.30 * brightness_score + 0.25 * min(texture_pct, 100), 1
    )
    composite = max(5.0, min(composite, 98.0))

    return {
        "width": width, "height": height,
        "brightness_pct": brightness_pct,
        "saturation_pct": saturation_pct,
        "texture_pct": round(min(texture_pct, 100), 1),
        "color_match_pct": color_match_pct,
        "composite_score": composite,
    }


def analyze_image(crop: str, image_bytes: bytes) -> dict:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.verify()  # sanity-check it's a real image
        img = Image.open(io.BytesIO(image_bytes))  # re-open after verify() (which consumes the file)
    except Exception:
        raise InvalidImageError("Could not read this file as an image. Please upload a valid JPG, PNG, or WEBP.")

    stats = _score_image(img, crop)
    score = stats["composite_score"]

    if score >= 82:
        grade = "A"
    elif score >= 62:
        grade = "B"
    else:
        grade = "C"

    observations = [
        f"Brightness: {stats['brightness_pct']}% ({'well-lit' if 35 <= stats['brightness_pct'] <= 85 else 'too dark or overexposed -- try better lighting'})",
        f"Color match to expected {crop} tone: {stats['color_match_pct']}%",
        f"Surface texture/detail: {stats['texture_pct']}% ({'clear detail' if stats['texture_pct'] > 40 else 'looks soft/blurry -- try a sharper, closer photo'})",
        f"Image resolution: {stats['width']}x{stats['height']}px",
    ]

    suitable_for = {
        "A": "Export and premium retail buyers",
        "B": "Retail and wholesale markets",
        "C": "Local mandi or food processing",
    }[grade]

    return {
        "crop": crop,
        "quality_grade": grade,
        "visual_quality_score": score,
        "confidence": round(min(0.55 + stats["texture_pct"] / 300, 0.9), 2),
        "detected_notes": observations,
        "suitable_for": suitable_for,
        "demo_mode": True,
        "analysis_method": "Heuristic pixel color/brightness/texture analysis of your actual uploaded photo -- not a trained deep-learning model.",
        "image_meta": {"width": stats["width"], "height": stats["height"]},
    }


def no_image_fallback(crop: str) -> dict:
    """Used only if a caller explicitly asks for a result with no image at
    all (kept for backward compatibility with any older integration) --
    always clearly marked as not based on a real photo."""
    return {
        "crop": crop,
        "quality_grade": "B",
        "visual_quality_score": 70.0,
        "confidence": 0.0,
        "detected_notes": ["No image was provided -- this is a placeholder result, not an analysis."],
        "suitable_for": "Retail and wholesale markets",
        "demo_mode": True,
        "analysis_method": "No image provided -- upload a photo for a real pixel-based assessment.",
        "image_meta": None,
    }
