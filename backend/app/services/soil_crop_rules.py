"""
Sourced crop-suitability reference data for the Soil Advisor.

HONESTY RULES FOR THIS FILE
---------------------------
* Every claim below is attached to a source id in SOURCES. Nothing here is
  an unattributed "common knowledge" threshold.
* Published sources DISAGREE with each other (e.g. soybean pH 6.0-7.5 in one
  source, "optimal 5.5-6.5" in another). They are therefore stored as
  separate claims, never merged or averaged into one invented threshold.
* A crop/factor with no cited claim is simply absent. The engine reports it
  as "not assessed", it is never guessed.
* Only the crops listed in CROP_RULES have rules. The rest of the catalogue
  (Tomato, Wheat, Potato, Onion, Maize, Groundnut, Sugarcane) is
  intentionally NOT covered until a citable source is added here.
* None of these sources is specific to Chhattisgarh. TNAU is Tamil Nadu's
  agricultural university; Vikaspedia and NSDC are national-level material.
  See REGIONAL_LIMITATION. These rules are a screening aid, not a
  substitute for a Soil Health Card, a soil test or advice from the local
  KVK / state agriculture department.
* Texture mapping: farmers pick one of TEXTURE_CLASSES. Where a source
  gives a range of textures ("sandy loam to clayey") the classes inside
  that range are listed explicitly; that interpretation is ours and is
  flagged on the claim via `interpreted=True`.

Sources were read on 2026-10-17. URLs may change; re-verify before relying
on them.
"""

TEXTURE_CLASSES = [
    "sandy", "sandy_loam", "loam", "silty_clay_loam",
    "clay_loam", "sandy_clay", "clay",
]
SEASONS = ["kharif", "rabi", "zaid"]
IRRIGATION_LEVELS = ["rainfed", "limited", "assured"]

REGIONAL_LIMITATION = (
    "The cited sources are not specific to Chhattisgarh or to any one "
    "district (TNAU is Tamil Nadu's agricultural university; Vikaspedia and "
    "NSDC are national-level material). Treat results as a first screening "
    "and confirm with a Soil Health Card, a soil test or your local KVK."
)

SOURCES = {
    "tnau_paddy_oneliner": {
        "title": "Paddy (Oryza sativa) oneliner - Botany & Production Technologies (Dr. Vanangamudi, TNAU)",
        "publisher": "Tamil Nadu Agricultural University (author material, hosted on SlideShare)",
        "url": "https://www.slideshare.net/slideshow/paddy-oneliner-botany-and-production-technologies-pdf/276445545",
        "region_scope": "Tamil Nadu",
    },
    "tnau_paddy_organic": {
        "title": "Organic Farming - Paddy: climate and soil",
        "publisher": "TNAU Agritech Portal",
        "url": "https://agritech.tnau.ac.in/org_farm/orgfarm_prac_agri_paddy_climate.html",
        "region_scope": "Tamil Nadu",
    },
    "tnau_soybean": {
        "title": "Horticulture - Vegetables: Soybean",
        "publisher": "TNAU Agritech Portal",
        "url": "https://agritech.tnau.ac.in/horticulture/horti_vegetables_soybean.html",
        "region_scope": "Tamil Nadu portal; sowing dates stated for northern India",
    },
    "nsdc_soybean": {
        "title": "Soybean Production Technology (preview)",
        "publisher": "NSDC India (Skill Council for Agriculture material)",
        "url": "https://nsdcindia.org/scmp/assets/image/1913597640-20_SoybeanProductionTechnology_preview.pdf",
        "region_scope": "India (national)",
    },
    "vikaspedia_soybean": {
        "title": "A comprehensive guide to soybean cultivation",
        "publisher": "Vikaspedia (package of practices - oilseeds)",
        "url": "https://en.vikaspedia.in/viewcontent/agriculture/crop-production/package-of-practices/oilseeds/a-comprehensive-guide-to-soybean-cultivation?lgn=en",
        "region_scope": "India (national)",
    },
    "vikaspedia_chickpea": {
        "title": "Chick pea (package of practices - pulses)",
        "publisher": "Vikaspedia",
        "url": "https://en.vikaspedia.in/viewcontent/agriculture/crop-production/package-of-practices/pulses/chick-pea?lgn=en",
        "region_scope": "India (national); sowing time stated for North India",
    },
}

# Catalogue crop name (must match app.mock_data.crops) -> sourced claims.
#   ph:       list of {min, max, source, label}
#   texture:  list of {classes, source, label, interpreted}
#   season:   list of {seasons, source, label}
#   water:    informational notes only -- these produce notes, never a
#             pass/fail check, because mapping a farmer's "rainfed/limited/
#             assured" answer onto millimetres would require an invented
#             conversion.
CROP_RULES = {
    "Paddy (Rice)": {
        "ph": [
            {"min": 5.5, "max": 6.5, "source": "tnau_paddy_oneliner", "label": "optimal"},
            {"min": 5.0, "max": 6.5, "source": "tnau_paddy_organic", "label": "high yield"},
        ],
        "texture": [
            {"classes": ["clay_loam"], "source": "tnau_paddy_oneliner",
             "label": "best soil", "interpreted": False},
            {"classes": ["sandy_clay", "clay"], "source": "tnau_paddy_organic",
             "label": "suitable (alluvial, sandy clay and clayey soils)", "interpreted": False},
        ],
        "season": [],  # no season claim was verified for Chhattisgarh/national use
        "water": [
            {"code": "paddy_high_water", "source": "tnau_paddy_oneliner",
             "applies_to": ["rainfed", "limited"],
             "params": {"low_l": 3000, "high_l": 5000},
             "text": "Paddy needs about 3,000-5,000 litres of water per kg of grain "
                     "(TNAU). Check that rainfall or irrigation can cover this."},
        ],
    },
    "Soybean": {
        "ph": [
            {"min": 6.0, "max": 7.5, "source": "tnau_soybean", "label": "recommended"},
            {"min": 6.0, "max": 7.5, "source": "nsdc_soybean", "label": "most suitable"},
            {"min": 5.5, "max": 6.5, "source": "nsdc_soybean", "label": "optimal"},
        ],
        "texture": [
            {"classes": ["loam"], "source": "tnau_soybean",
             "label": "well-drained fertile loam", "interpreted": False},
            {"classes": ["sandy_loam", "loam", "clay_loam", "silty_clay_loam", "sandy_clay", "clay"],
             "source": "vikaspedia_soybean",
             "label": "sandy loam to clayey soils with medium water-holding capacity",
             "interpreted": True},
        ],
        "season": [
            {"seasons": ["kharif"], "source": "tnau_soybean",
             "label": "sown from the third week of June to first fortnight of July (northern India)"},
        ],
        "water": [
            {"code": "soybean_water_stages", "source": "nsdc_soybean",
             "applies_to": ["rainfed", "limited"],
             "params": {"low_mm": 400, "high_mm": 500},
             "text": "Soybean needs about 400-500 mm of water in a season, most "
                     "critically at germination, flowering and pod filling "
                     "(NSDC). Waterlogging also harms the crop (TNAU)."},
        ],
    },
    "Chana (Gram)": {
        "ph": [
            {"min": 6.0, "max": 8.0, "source": "vikaspedia_chickpea", "label": "best suited"},
        ],
        "texture": [
            {"classes": ["loam", "silty_clay_loam"], "source": "vikaspedia_chickpea",
             "label": "well-drained deep loams or silty clay loams", "interpreted": False},
        ],
        "season": [
            {"seasons": ["rabi"], "source": "vikaspedia_chickpea",
             "label": "winter-season crop"},
        ],
        "water": [
            {"code": "chana_mostly_rainfed", "source": "vikaspedia_chickpea",
             "applies_to": ["rainfed"], "params": {},
             "text": "Chickpea is mostly grown rainfed; where irrigation exists, "
                     "a pre-sowing irrigation is advised (Vikaspedia)."},
        ],
    },
}
