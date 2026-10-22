# Soil Advisor

An explainable crop-suitability screen linked to CropRetain's existing market comparison.

## What it does
`POST /soil/advise` takes any of: `soil_ph`, `soil_texture`, `season`, `irrigation` (at least one of pH/texture/season is required), plus an optional pair `quantity_kg` + `location`.

For each crop that has cited rules (**Paddy (Rice), Soybean, Chana (Gram)**) it returns, check by check, whether the input falls inside what the cited sources report, with the source for each check. There is no invented score: results read "2 of 3 checks matched".

If `quantity_kg` and `location` are given, each crop also carries the estimated net return from the **existing** `market._compare_markets_core` → `transport_optimizer.net_profit_breakdown` path. The Soil Advisor adds no financial calculation of its own.

`GET /soil/options` lists the allowed input values and known locations.

## Data labels
| Label | Meaning here |
|---|---|
| `ESTIMATED` | Rule-check result; estimated net return (always an estimate) |
| `LIVE` / `DEMO` | Price data behind a market, per market, exactly as the market comparison reports it |
| `UNAVAILABLE` | Crop with no cited rules, or no market data for the crop |

Inputs are echoed with `provenance: USER_PROVIDED`.

## Sources and their limits
Rules live in `backend/app/services/soil_crop_rules.py`; every claim has a source id (TNAU Agritech, NSDC, Vikaspedia). Sources were read on 2026-10-17.
- **None is specific to Chhattisgarh or a district.** Treat output as a first screen; confirm with a Soil Health Card, soil test or the local KVK.
- **Sources disagree** (e.g. soybean pH 6.0–7.5 vs "optimal 5.5–6.5"). They are kept as separate claims; the UI shows which ranges contain the value and warns when sources disagree.
- Soybean's texture claim "sandy loam to clayey" is expanded to explicit classes by us and flagged `interpreted`.
- Paddy has no season rule (none was verified), so season is reported as not assessed for paddy.
- Water requirements are shown as notes with their source, never pass/fail, because mapping "rainfed/limited/assured" to millimetres would need an invented conversion.
- The other 7 catalogue crops are `UNAVAILABLE` until a citable source is added to `soil_crop_rules.py`.

## Soil-test rating (`POST /soil/health-check`)
Takes any of `organic_carbon` (%), `nitrogen`, `phosphorus`, `potassium` (kg/ha), `ph`, `ec` (at least one) and rates each against one cited chart (TNAU Soil Rating Chart, read 2026-10-22): low / medium / high for nutrients, class names for pH and EC. `needs_attention` lists low nutrients and non-normal pH/EC; values you did not give appear under `not_provided`, never estimated.
- The chart is inconsistent in places, and the result says so rather than guessing: organic-carbon "medium" is printed as 0.5-7.5 % but "high" starts above 0.75 %, so we read medium as 0.5-0.75 % (flagged `interpreted`); pH 8.5-8.9 has no class (`unclassified`); the chart does not say which class the exact EC values 1, 2 and 4 belong to (we use [1,2), [2,4], >4, flagged).
- EC is printed by the source as "milli mhos/cm2"; confirm the unit on your own report.
- It gives **no fertiliser quantities** (none are cited). It is Tamil Nadu material, not Chhattisgarh-specific; confirm with your Soil Health Card or KVK.
- Not yet connected to the crop screen in `/soil/advise`, and no UI yet.

## Not included
Photo- or sensor-based soil detection, district-specific rules, crop-specific nutrient requirements, fertiliser doses, yield prediction, and cultivation-cost accounting (net return excludes seed, fertiliser, labour and irrigation costs).

## Auth
Unauthenticated, like `/market/compare` and `/advisor/recommend` which it builds on; the frontend route is farmer-only. Nothing is stored.

## Translations
The 54 new UI keys (`navSoil`, `soil.*`) were drafted by an AI assistant for all 14 non-English locales and **need native-speaker review** (especially Odia, Assamese, Bhojpuri, Maithili). Server-supplied source titles stay in English.

## Tests
`backend/tests/test_soil_advisor.py` (25 tests) and `backend/tests/test_soil_health.py` (rating boundaries, chart-gap flags, no-dose, endpoint validation): citation integrity, disagreeing sources, UNAVAILABLE handling, input validation, and that net-return figures equal an independent `net_profit_breakdown` call.
