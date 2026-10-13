"""Canonical, language-neutral intents the assistant can recognize."""

MARKET_RECOMMENDATION = "MARKET_RECOMMENDATION"
MARKET_COMPARISON = "MARKET_COMPARISON"
PRICE_LOOKUP = "PRICE_LOOKUP"
PRICE_FORECAST = "PRICE_FORECAST"
PROFIT_CALCULATION = "PROFIT_CALCULATION"
FARMPOOL = "FARMPOOL"
BUYER_SEARCH = "BUYER_SEARCH"
TRANSPORT = "TRANSPORT"
WEATHER = "WEATHER"
QUALITY = "QUALITY"
DISEASE_HELP = "DISEASE_HELP"
GENERAL_AGRICULTURE_QUERY = "GENERAL_AGRICULTURE_QUERY"
# Returned when nothing matched confidently -- see detect_intent(). NOT a
# real capability; the router must respond with a clarification question,
# never treat this as MARKET_RECOMMENDATION.
NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"

# keyword -> intent, per language. Matching is substring-based on the lowered
# input. This is intentionally simple (no ML dependency, no external LLM
# call) but it is a real, testable, language-neutral classifier -- every
# language below maps to the SAME canonical intent constants, so the engine
# behind it never branches on language.
INTENT_KEYWORDS = {
    # Checked first and most specific: genuine plant-health questions must
    # NOT be misrouted into a market recommendation (this was a real gap --
    # "my tomato leaves are turning yellow" used to silently become a sell
    # recommendation because everything unmatched fell through to
    # MARKET_RECOMMENDATION). CropRetain has no diagnostic data source for
    # this, so it is handled with an explicit, honest "I don't have that"
    # response rather than a market answer -- see assistant.py.
    DISEASE_HELP: {
        "en": ["disease", "turning yellow", "leaves are yellow", "yellow leaves", "pest", "fungus", "wilting", "spots on", "insect", "infection"],
        "hi": ["बीमारी", "रोग", "पत्तियां पीली", "पत्ते पीले", "कीट", "फफूंद"],
        "mr": ["रोग", "पाने पिवळी", "कीड"],
        "bho": ["बेमारी", "पात पीयर"],
    },
    QUALITY: {
        "en": ["quality grade", "improve quality", "grade my crop", "quality assessment"],
        "hi": ["गुणवत्ता", "क्वालिटी"],
        "mr": ["गुणवत्ता"],
    },
    TRANSPORT: {
        "en": [
            "transport cost", "how much will transport", "truck cost", "shipping cost", "delivery cost",
            # Follow-up phrasings asking the assistant to EXPLAIN a transport
            # figure it already gave, rather than a fresh cost question --
            # these used to fall through to the MARKET_RECOMMENDATION
            # default and silently re-answer the original question instead
            # of explaining the calculation (e.g. "why is transport so
            # cheap" never matched any TRANSPORT keyword).
            "why is transport", "why transport", "transport so cheap", "transport so low",
            "how is transport calculated", "how transport is calculated", "explain transport",
            "explain the transport", "transport calculation", "how did you calculate transport",
        ],
        "hi": ["परिवहन खर्च", "ढुलाई", "ट्रक का खर्च", "परिवहन इतना कम", "परिवहन कैसे तय"],
        "mr": ["वाहतूक खर्च", "वाहतूक इतकी कमी", "वाहतूक कशी"],
        "bho": ["ढुलाई खर्चा"],
    },
    FARMPOOL: {
        "en": ["shared transport", "share transport", "farmpool", "pool truck", "share truck"],
        "hi": ["साझा परिवहन", "ट्रक साझा"],
        "mr": ["सामायिक वाहतूक"],
        "bho": ["साझा गाड़ी"],
    },
    # Checked before MARKET_RECOMMENDATION and before PRICE_FORECAST: "compare
    # X and Y" or "X vs Y" is a request to compare two *named* markets
    # against each other, which is a distinct, narrower question from "where
    # should I sell" (MARKET_RECOMMENDATION, no markets named yet -- CropRetain
    # picks the best one) or "what will the price be" (PRICE_FORECAST, one
    # market, future time). The handler in assistant.py additionally requires
    # two real market names to actually be found in the text before treating
    # this as resolved -- otherwise it clarifies rather than guessing which
    # two markets were meant.
    MARKET_COMPARISON: {
        "en": ["compare", " vs ", " vs. ", "versus", "which is better", "which market is better", "difference between"],
        "hi": ["तुलना", "मुकाबला", "कौन सा बेहतर"],
        "mr": ["तुलना", "कोणते चांगले"],
    },
    # Checked before PRICE_FORECAST: asking for the price *right now* is a
    # different, simpler, real capability (app.routers.market._get_price --
    # live government price where available, else honestly-labelled demo
    # data) from asking what the price *will be* (PRICE_FORECAST, the
    # deterministic trend model). These keyword sets are deliberately
    # disjoint from PRICE_FORECAST's ("tomorrow"/"forecast"/etc.) so a
    # single message can't match both.
    PRICE_LOOKUP: {
        "en": ["current price", "today's price", "todays price", "price today", "what is the price", "what's the price", "market price", "current rate", "today's rate", "todays rate"],
        "hi": ["आज का भाव", "अभी का भाव", "वर्तमान भाव", "आज का दाम"],
        "mr": ["आजचा भाव", "सध्याचा भाव"],
        "bho": ["आज के भाव"],
    },
    # Checked before MARKET_RECOMMENDATION: a plain weather question has
    # nothing to do with selling and must not be answered with a market
    # comparison. Routed to the same weather_service used everywhere else
    # in CropRetain (LIVE Open-Meteo / DEMO seeded / UNAVAILABLE) -- no second
    # weather client.
    WEATHER: {
        "en": ["weather", "rain", "will it rain", "temperature", "forecast for tomorrow weather", "humidity", "climate today"],
        "hi": ["मौसम", "बारिश", "बरसात"],
        "mr": ["हवामान", "पाऊस"],
        "bho": ["मउसम", "बरखा"],
    },
    # Checked before MARKET_RECOMMENDATION: this is the assistant's primary,
    # fully-implemented capability, so an ambiguous "where/should I sell +
    # mentions profit" phrasing should resolve here rather than to a
    # narrower intent.
    MARKET_RECOMMENDATION: {
        "en": ["where should i sell", "where to sell", "best market", "sell my"],
        "hi": ["कहाँ बेचूं", "कहाँ बेचनी", "कहाँ बेचें", "बेचने पर", "बेचना चाहिए", "सबसे अच्छा भाव"],
        "mr": ["कुठे विकावी", "कुठे विकू", "विकल्यास"],
        "bn": ["কোথায় বিক্রি"],
        "ta": ["எங்கு விற்க"],
        "te": ["ఎక్కడ అమ్మాలి"],
        "gu": ["ક્યાં વેચવું"],
        "kn": ["ಎಲ್ಲಿ ಮಾರಾಟ"],
        "ml": ["എവിടെ വിൽക്കണം"],
        "pa": ["ਕਿੱਥੇ ਵੇਚਾਂ"],
        "or": ["କେଉଁଠାରେ ବିକ୍ରି"],
        "as": ["ক'ত বিক্ৰী"],
        "ur": ["کہاں بیچوں"],
        "bho": ["कहाँ बेची", "कहाँ बेचीं"],
        "mai": ["कतय बेची"],
    },
    PRICE_FORECAST: {
        "en": ["forecast", "tomorrow", "next week", "future price", "predict"],
        "hi": ["आगे", "कल", "भविष्य", "अनुमान"],
        "mr": ["उद्या", "भविष्य", "अंदाज"],
        "bn": ["আগামীকাল", "ভবিষ্যত", "পূর্বাভাস"],
        "ta": ["நாளை", "எதிர்கால", "முன்னறிவிப்பு"],
        "te": ["రేపు", "భవిష్యత్తు", "అంచనా"],
        "gu": ["આવતીકાલે", "ભવિષ્ય", "આગાહી"],
        "kn": ["ನಾಳೆ", "ಭವಿಷ್ಯ", "ಮುನ್ಸೂಚನೆ"],
        "ml": ["നാളെ", "ഭാവി", "പ്രവചനം"],
        "pa": ["ਕੱਲ੍ਹ", "ਭਵਿੱਖ", "ਅਨੁਮਾਨ"],
        "bho": ["काल्ह", "भविष्य", "अनुमान"],
    },
    PROFIT_CALCULATION: {
        "en": ["profit", "calculate", "how much will i make", "net"],
        "hi": ["मुनाफा", "लाभ", "फायदा", "कितना कमाऊंगा"],
        "mr": ["नफा", "फायदा"],
        "bn": ["মুনাফা", "লাভ"],
        "ta": ["லாபம்"],
        "te": ["లాభం"],
        "gu": ["નફો", "ફાયદો"],
        "kn": ["ಲಾಭ"],
        "ml": ["ലാഭം"],
        "pa": ["ਲਾਭ", "ਮੁਨਾਫ਼ਾ"],
        "bho": ["मुनाफा", "फायदा"],
    },
    BUYER_SEARCH: {
        "en": ["buyer", "who will buy", "find buyer", "who wants", "buyers"],
        "hi": ["खरीदार", "ग्राहक"],
        "mr": ["खरेदीदार"],
        "bn": ["ক্রেতা"],
        "ta": ["வாங்குபவர்"],
        "te": ["కొనుగోలుదారు"],
        "gu": ["ખરીદનાર"],
        "kn": ["ಖರೀದಿದಾರ"],
        "ml": ["വാങ്ങുന്നയാൾ"],
        "pa": ["ਖਰੀਦਦਾਰ"],
        "bho": ["खरीददार"],
    },
    # Genuinely open-ended agricultural questions CropRetain has no data
    # source for (crop advice, "what should I grow this season", general
    # farming questions unrelated to selling). Checked last -- only
    # matched when the text clearly isn't a selling/market question.
    GENERAL_AGRICULTURE_QUERY: {
        "en": ["what crop should i grow", "which crop is best to grow", "how to improve", "fertilizer", "pesticide", "when to plant", "which season"],
        "hi": ["कौन सी फसल उगाऊं", "कौन सी फसल लगाऊं", "खाद", "उर्वरक", "कीटनाशक", "कब बोऊं"],
        "mr": ["कोणते पीक घ्यावे", "खत", "कधी लावावे"],
    },
}


def detect_intent(text: str, language: str) -> str:
    """
    Keyword match against every supported intent's phrase list. This is a
    real, testable, deterministic classifier -- not a stub -- but it is
    still a substring match, so honesty about its limits matters more than
    coverage: if nothing matches, we do NOT guess. Silently defaulting an
    unmatched question to MARKET_RECOMMENDATION was a real correctness bug
    (a plant-disease question or an off-topic remark would previously come
    back as a market recommendation) -- fixed by returning
    NEEDS_CLARIFICATION instead, which the router turns into an honest
    clarifying question rather than an invented answer.
    """
    lowered = text.lower()
    # check each intent's keywords for this language first, then fall back to
    # English keywords (many farmers mix English agri-terms into local speech)
    for intent, by_lang in INTENT_KEYWORDS.items():
        for lang_key in (language, "en"):
            for kw in by_lang.get(lang_key, []):
                if kw.lower() in lowered:
                    return intent
    return NEEDS_CLARIFICATION
