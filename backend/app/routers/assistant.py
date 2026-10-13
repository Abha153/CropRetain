"""
Global Farm Assistant -- multilingual, voice-first entry point.

Flow (mirrors the architecture requested for the multilingual upgrade):

    text (any supported language)
        -> app.i18n.nlu.parse()            language-neutral intent + entities
        -> intent-specific handler          real business logic per intent,
                                             OR an honest "I don't have that
                                             data" response -- never a guess
        -> app.i18n.templates                native-language response text

Positioning note (see README): this is a deterministic, rule-based
multilingual intent engine -- not a general-purpose LLM. It's fast,
transparent, works offline, and never hallucinates: any intent it can't
genuinely answer from real CropRetain data returns an explicit "I don't have
enough reliable data" message instead of making something up.

Critically: if the crop or location can't be identified, this NEVER
silently substitutes a default (no more silent "Tomato" / "Bilaspur") --
it returns a `clarification_needed` field and a native-language question,
and the frontend must ask the user rather than guessing. The same is true
of the *intent itself* now: an unmatched question returns
NEEDS_CLARIFICATION (clarification_needed="intent") instead of being
silently treated as a market recommendation.

Each intent below is wired to the SAME real CropRetain service another page
uses -- never a second copy of the calculation:
  MARKET_RECOMMENDATION / PROFIT_CALCULATION -> market.compare_markets
  MARKET_COMPARISON                          -> market.compare_markets,
                                                 filtered to the two named markets
  PRICE_LOOKUP                               -> market._get_price
  PRICE_FORECAST                             -> forecast.get_forecast (price_predictor)
  TRANSPORT                                  -> transport_optimizer.estimate_transport_cost
  BUYER_SEARCH                               -> real BuyerDemand rows (models.BuyerDemand)
  WEATHER                                    -> weather_service.get_weather
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import schemas, models
from app.i18n.nlu import parse
from app.i18n.crop_terms import localized_crop_name
from app.i18n.location_terms import find_all_markets_in_text
from app.i18n.intents import (
    DISEASE_HELP, QUALITY, TRANSPORT, GENERAL_AGRICULTURE_QUERY,
    MARKET_COMPARISON, PRICE_LOOKUP, PRICE_FORECAST, PROFIT_CALCULATION,
    BUYER_SEARCH, WEATHER, FARMPOOL, NEEDS_CLARIFICATION,
)
from app.i18n.templates import (
    render_market_recommendation, render_clarify_crop, render_clarify_location,
    render_no_data, render_disease_help, render_transport, render_quality_pointer,
    render_price_lookup, render_profit, render_buyer_search_found, render_buyer_search_none,
    render_market_comparison, render_weather, render_weather_unavailable,
    render_clarify_intent, render_clarify_two_markets,
    render_price_forecast, render_price_forecast_unavailable, render_farmpool,
)
from app.i18n.languages import FULLY_SUPPORTED, catalog_as_dicts
from app.routers.market import compare_markets, _get_price
from app.routers.forecast import get_forecast
from app.services.transport_optimizer import estimate_transport_cost, shared_transport_plan
from app.services.weather_service import get_weather
from app.mock_data.locations import nearest_markets

router = APIRouter(prefix="/assistant", tags=["assistant"])

DEFAULT_QUANTITY_KG = 500.0

# Intents CropRetain can genuinely answer WITHOUT needing crop+location (a
# real image-analysis pointer, or an honest refusal) -- these skip the
# clarification-required flow below entirely.
NO_ENTITY_NEEDED_INTENTS = {QUALITY, GENERAL_AGRICULTURE_QUERY}


@router.get("/languages")
def assistant_languages():
    """Full language capability matrix -- the frontend's single source of
    truth for which languages to offer and what each one actually supports."""
    return {"languages": catalog_as_dicts(), "fully_supported": FULLY_SUPPORTED}


@router.post("/ask")
def ask(payload: schemas.AssistantAsk, db: Session = Depends(get_db)):
    language = payload.language if payload.language else "en"
    native = language in FULLY_SUPPORTED
    effective_language = language if native else "en"

    parsed = parse(
        payload.question, language=language,
        known_crop=payload.known_crop, known_quantity_kg=payload.known_quantity_kg,
        known_location=payload.known_location,
    )
    intent = parsed["intent"]

    base_response = {
        "understood_language": language,
        "native_response": native,
        "intent": intent,
        "crop": parsed["crop"],
        "quantity_kg": parsed["quantity_kg"],
        "location": parsed["location"],
        "quantity_assumed": False,
        "clarification_needed": None,
        "market_options": [],
    }

    def with_fallback_note(text: str) -> str:
        if not native:
            return text + " (Full understanding for this language is still limited -- English/Hindi work best.)"
        return text

    # --- Ambiguous / unmatched question: ask, never guess an intent. ---
    if intent == NEEDS_CLARIFICATION:
        text = with_fallback_note(render_clarify_intent(effective_language))
        return {**base_response, "answer": text, "clarification_needed": "intent"}

    # --- Intents CropRetain genuinely cannot answer: say so, never hallucinate. ---
    if intent == DISEASE_HELP:
        text = with_fallback_note(render_disease_help(effective_language, parsed["crop"]))
        return {**base_response, "answer": text}

    if intent == GENERAL_AGRICULTURE_QUERY:
        text = with_fallback_note(render_no_data(effective_language, parsed["crop"]))
        return {**base_response, "answer": text}

    if intent == QUALITY:
        text = with_fallback_note(render_quality_pointer(effective_language, parsed["crop"]))
        return {**base_response, "answer": text}

    # --- WEATHER: needs a location only (no crop) -- real weather_service,
    # same LIVE/DEMO/UNAVAILABLE contract used by the Weather card. No GPS
    # coordinates are available in a text conversation, so this resolves by
    # location name only (which still correctly returns DEMO for CropRetain's
    # seeded demo locations, or UNAVAILABLE rather than inventing weather). ---
    if intent == WEATHER:
        location = parsed["location"]
        if not location:
            text = with_fallback_note(render_clarify_location(effective_language))
            return {**base_response, "answer": text, "clarification_needed": "location"}
        weather = get_weather(latitude=None, longitude=None, location_name=location)
        if weather["status"] == "UNAVAILABLE":
            text = with_fallback_note(render_weather_unavailable(effective_language, location))
            return {**base_response, "answer": text}
        current = weather.get("current") or {}
        forecast_days = weather.get("forecast") or []
        today = forecast_days[0] if forecast_days else {}
        status_label = {"en": "Live", "hi": "लाइव"}.get(effective_language, "Live") if weather["status"] == "LIVE" else \
                       {"en": "Demo", "hi": "डेमो"}.get(effective_language, "Demo")
        text = with_fallback_note(render_weather(
            effective_language,
            status_label=status_label,
            location=weather["location"]["name"] or location,
            condition=current.get("condition", "-"),
            temp_max=today.get("temp_max", current.get("temperature", "-")),
            temp_min=today.get("temp_min", "-"),
            rain_prob=today.get("rainfall_probability", 0),
            humidity=current.get("humidity", "-"),
            source=weather["source"] or "-",
        ))
        return {**base_response, "answer": text, "weather_status": weather["status"]}

    # --- Every remaining intent needs a real crop. Never guess. ---
    if "crop" in parsed["missing"]:
        text = with_fallback_note(render_clarify_crop(effective_language))
        return {**base_response, "answer": text, "clarification_needed": "crop"}
    crop_display = localized_crop_name(parsed["crop"], effective_language)

    # --- BUYER_SEARCH: real active BuyerDemand rows for this crop -- never
    # a fabricated buyer. Location is used to narrow results when known,
    # but (unlike the market intents) isn't required: "who wants my onion"
    # is answerable crop-only. ---
    if intent == BUYER_SEARCH:
        query = db.query(models.BuyerDemand).filter(
            models.BuyerDemand.status == "ACTIVE",
            models.BuyerDemand.crop == parsed["crop"],
        )
        demands = query.order_by(models.BuyerDemand.updated_at.desc()).limit(5).all()
        if not demands:
            text = with_fallback_note(render_buyer_search_none(effective_language, crop_display))
            return {**base_response, "answer": text}
        # Real verification status per buyer -- never invented. Same mapping
        # used by marketplace badges (app/routers/buyer_verification.py).
        from app.routers.buyer_verification import display_info as _verification_display_info
        buyer_ids = {d.buyer_id for d in demands if d.buyer}
        verifications = {
            v.buyer_id: v for v in db.query(models.BuyerVerification)
            .filter(models.BuyerVerification.buyer_id.in_(buyer_ids)).all()
        }
        buyer_list = ", ".join(
            f"{d.buyer.company_name} ({d.required_quantity_kg:.0f} kg"
            + (f", {d.delivery_location}" if d.delivery_location else "") + ")"
            + f" [{_verification_display_info(verifications.get(d.buyer_id)).get('label')}]"
            for d in demands if d.buyer
        )
        text = with_fallback_note(render_buyer_search_found(
            effective_language, count=len(demands), crop=crop_display, buyer_list=buyer_list,
        ))
        return {**base_response, "answer": text}

    # --- FARMPOOL: real shared-transport simulation with nearby farmers. ---
    if intent == FARMPOOL:
        origin = parsed["location"] or payload.known_location
        if not origin:
            text = with_fallback_note(render_clarify_location(effective_language))
            return {**base_response, "answer": text, "clarification_needed": "location"}

        destination_candidates = find_all_markets_in_text(payload.question)
        if len(destination_candidates) >= 2:
            destination = next((m for m in destination_candidates if m != origin), destination_candidates[1])
        else:
            nearest = nearest_markets(origin)
            destination = nearest[0]["name"] if nearest else origin

        quantity_kg = parsed["quantity_kg"] or DEFAULT_QUANTITY_KG
        quantity_assumed = parsed["quantity_kg"] is None
        plan = shared_transport_plan(
            crop=parsed["crop"],
            location=origin,
            quantity_kg=quantity_kg,
            destination_market=destination,
        )
        answer = with_fallback_note(render_farmpool(
            effective_language,
            quantity=f"{quantity_kg:.0f}",
            crop=crop_display,
            location=origin,
            market=destination,
            individual_cost=f"{plan['your_individual_transport_cost']:,.0f}",
            shared_cost=f"{plan['your_shared_transport_cost']:,.0f}",
            savings=f"{plan['estimated_savings']:,.0f}",
            savings_pct=f"{plan['savings_pct']:.1f}",
            partner_count=len(plan.get('pool_partners', [])),
        ))
        return {
            **base_response,
            "answer": answer,
            "quantity_kg": quantity_kg,
            "quantity_assumed": quantity_assumed,
            "pool_plan": plan,
        }

    # --- MARKET_COMPARISON: two explicitly named markets, compared against
    # each other via the same compare_markets() engine, filtered down to
    # just those two. Requires a known origin location (from earlier
    # conversation context) to compute distance/transport -- this is
    # deliberately NOT inferred from the two compared-market names
    # themselves, since that would conflate "where I'm selling from" with
    # "which markets I'm comparing". ---
    if intent == MARKET_COMPARISON:
        markets_named = find_all_markets_in_text(payload.question)
        if len(markets_named) < 2:
            from app.i18n.location_terms import MARKET_ALIASES
            names = list(MARKET_ALIASES.keys())
            text = with_fallback_note(render_clarify_two_markets(effective_language, names[0], names[1]))
            return {**base_response, "answer": text, "clarification_needed": "two_markets"}
        if not payload.known_location:
            text = with_fallback_note(render_clarify_location(effective_language))
            return {**base_response, "answer": text, "clarification_needed": "location"}

        quantity_kg = parsed["quantity_kg"] or DEFAULT_QUANTITY_KG
        quantity_assumed = parsed["quantity_kg"] is None
        comparison = compare_markets(crop=parsed["crop"], quantity_kg=quantity_kg, location=payload.known_location, db=db)
        options_by_market = {o["market"]: o for o in comparison.get("options", [])}
        market_a, market_b = markets_named[0], markets_named[1]
        if market_a not in options_by_market or market_b not in options_by_market:
            text = with_fallback_note(render_no_data(effective_language, crop=crop_display))
            return {**base_response, "answer": text, "quantity_kg": quantity_kg, "quantity_assumed": quantity_assumed}
        a, b = options_by_market[market_a], options_by_market[market_b]
        better = market_a if a["net_profit"] >= b["net_profit"] else market_b
        text = with_fallback_note(render_market_comparison(
            effective_language, quantity=f"{quantity_kg:.0f}", crop=crop_display,
            market_a=market_a, price_a=a["modal_price_per_kg"], distance_a=a["distance_km"],
            transport_a=f"{a['transport_cost']:,.0f}", net_a=f"{a['net_profit']:,.0f}",
            market_b=market_b, price_b=b["modal_price_per_kg"], distance_b=b["distance_km"],
            transport_b=f"{b['transport_cost']:,.0f}", net_b=f"{b['net_profit']:,.0f}",
            better_market=better,
        ))
        return {**base_response, "answer": text, "quantity_kg": quantity_kg, "quantity_assumed": quantity_assumed,
                "market_options": [a, b]}

    # --- PRICE_LOOKUP: current price only (live government price where
    # available, else honestly-labelled demo data, else "no record") --
    # distinct from PRICE_FORECAST below. Needs a market, not a farmer
    # origin, so it's checked before the origin-location requirement. ---
    if intent == PRICE_LOOKUP:
        market = parsed["location"]
        if not market:
            text = with_fallback_note(render_clarify_location(effective_language))
            return {**base_response, "answer": text, "clarification_needed": "location"}
        outcome = _get_price(db, parsed["crop"], market)
        # A price is present whenever data_source is set -- "live" (status
        # "ok") or "demo" (status "demo_fallback", covering a confirmed
        # no-government-record selection, an unreachable/erroring live API,
        # or live mode simply not being configured -- see market._get_price's
        # own docstring for the full status contract). `status` only needs
        # checking directly for the one genuinely price-less outcome left
        # ("unavailable": nothing live or demo exists for this pair at all).
        if outcome.get("data_source"):
            tag = "live government price" if outcome["data_source"] == "live" else "\U0001F7E1 demo data"
            price_line = f"\u20b9{outcome['modal_price']}/kg ({tag}, range \u20b9{outcome['min_price']}-\u20b9{outcome['max_price']})"
            # Multi-source attribution: only meaningful for a live result --
            # demo data has no "source" in this sense. See
            # mandi_directory.fetch_price_result's docstring for how
            # `sources`/`source_conflict` are decided (data.gov.in and
            # Agmarknet are queried concurrently and combined, never one
            # silently overriding the other).
            sources = outcome.get("sources") or []
            if outcome["data_source"] == "live" and len(sources) > 1:
                price_line += f" -- found in both {' and '.join(sources)}"
                if outcome.get("source_conflict"):
                    per_source = ", ".join(
                        f"{src}: \u20b9{vals['modal_price']}/kg"
                        for src, vals in (outcome.get("source_values") or {}).items()
                        if vals.get("modal_price") is not None
                    )
                    price_line += f"; these sources disagree ({per_source}) -- showing the most recent observation"
                price_line += f". Sources: {' + '.join(sources)}."
            elif outcome["data_source"] == "live" and sources:
                price_line += f". Source: {sources[0]}."
        else:
            price_line = outcome.get("message") or "No price data available for this selection."
        text = with_fallback_note(render_price_lookup(
            effective_language, crop=crop_display, market=market, price_line=price_line,
        ))
        return {**base_response, "answer": text}

    # --- PRICE_FORECAST: real deterministic trend model via forecast.get_forecast
    # (same function the Price Forecast page calls) -- never re-implemented here. ---
    if intent == PRICE_FORECAST:
        market = parsed["location"]
        if not market:
            text = with_fallback_note(render_clarify_location(effective_language))
            return {**base_response, "answer": text, "clarification_needed": "location"}
        result = get_forecast(crop=parsed["crop"], market=market, db=db)
        if not result["available"]:
            result = get_forecast(crop=parsed["crop"], market=market, include_demo=True, db=db)
        if not result["available"]:
            text = with_fallback_note(render_price_forecast_unavailable(effective_language, crop_display, market))
            return {**base_response, "answer": text}
        demo_note = ""
        if result["is_demo"]:
            demo_note = {
                "en": " (based on CropRetain's demo price series, not live mandi data)",
                "hi": " (क्रॉपरिटेन की डेमो भाव श्रृंखला पर आधारित, लाइव मंडी डेटा नहीं)",
            }.get(effective_language, " (demo data)")
        text = with_fallback_note(render_price_forecast(
            effective_language, crop=crop_display, market=market,
            current=result["current_price"], days=len(result["forecast_series"]),
            low=result["predicted_price_low"], high=result["predicted_price_high"],
            trend=result["trend_direction"], demo_note=demo_note,
        ))
        return {**base_response, "answer": text}

    # --- Every remaining intent (MARKET_RECOMMENDATION, PROFIT_CALCULATION,
    # TRANSPORT, FARMPOOL) needs a real origin location too. Never guess. ---
    if "location" in parsed["missing"]:
        text = with_fallback_note(render_clarify_location(effective_language))
        return {**base_response, "answer": text, "clarification_needed": "location"}

    quantity_kg = parsed["quantity_kg"]
    quantity_assumed = quantity_kg is None
    if quantity_assumed:
        quantity_kg = DEFAULT_QUANTITY_KG

    comparison = compare_markets(crop=parsed["crop"], quantity_kg=quantity_kg, location=parsed["location"], db=db)
    if comparison.get("insufficient_data") or not comparison.get("options"):
        answer = with_fallback_note(render_no_data(effective_language, crop=crop_display))
        return {**base_response, "answer": answer, "quantity_kg": quantity_kg, "quantity_assumed": quantity_assumed}
    best = comparison["options"][0]

    # --- TRANSPORT: real transport_optimizer calculation, not a market pitch. ---
    if intent == TRANSPORT:
        transport_cost = estimate_transport_cost(best["distance_km"], quantity_kg)
        answer = with_fallback_note(render_transport(
            effective_language, quantity=f"{quantity_kg:.0f}", crop=crop_display,
            location=parsed["location"], market=best["market"], distance=best["distance_km"],
            transport_cost=f"{transport_cost:,.0f}",
        ))
        return {**base_response, "answer": answer, "quantity_kg": quantity_kg, "quantity_assumed": quantity_assumed}

    # --- PROFIT_CALCULATION: real net_profit from the same recommendation
    # engine, with its own honest wording pointing to the Profit Calculator
    # for a full cost breakdown (labour/packaging/storage aren't known here). ---
    if intent == PROFIT_CALCULATION:
        answer = with_fallback_note(render_profit(
            effective_language, quantity=f"{quantity_kg:.0f}", crop=crop_display,
            location=parsed["location"], market=best["market"],
            net_profit=f"{best['net_profit']:,.0f}", price=best["modal_price_per_kg"],
            transport=f"{best['transport_cost']:,.0f}",
        ))
        return {**base_response, "answer": answer, "quantity_kg": quantity_kg, "quantity_assumed": quantity_assumed,
                "recommended_market": best["market"], "market_options": comparison["options"]}

    # --- Default: MARKET_RECOMMENDATION and FARMPOOL (no dedicated FarmPool
    # service call here yet -- see MVP_AUDIT.md; still resolves through the
    # real market-comparison engine rather than the previous MARKET_RECOMMENDATION
    # catch-all default, since a market answer is genuinely relevant to it). ---
    answer = render_market_recommendation(
        effective_language,
        quantity=f"{quantity_kg:.0f}", crop=crop_display, market=best["market"],
        location=parsed["location"], net_profit=f"{best['net_profit']:,.0f}",
        price=best["modal_price_per_kg"], distance=best["distance_km"],
        transport=f"{best['transport_cost']:,.0f}",
    )
    if quantity_assumed:
        assumed_note = {
            "en": f" (assumed {DEFAULT_QUANTITY_KG:.0f} kg since no quantity was mentioned)",
            "hi": f" (मात्रा नहीं बताई गई, इसलिए {DEFAULT_QUANTITY_KG:.0f} किलो मान लिया गया)",
        }.get(effective_language, f" (assumed {DEFAULT_QUANTITY_KG:.0f} kg)")
        answer += assumed_note
    answer = with_fallback_note(answer)

    return {
        **base_response,
        "answer": answer,
        "quantity_kg": quantity_kg,
        "quantity_assumed": quantity_assumed,
        "recommended_market": best["market"],
        "market_options": comparison["options"],
    }
