"""
Native-language response templates for the CropRetain assistant.

The assistant's answers are always generated from *structured data*
(crop, quantity, market, net profit, price, distance, transport) produced
by the existing recommendation engine -- never from machine-translating
free English text. That's what makes native-language answers here
trustworthy: we're filling in a hand-written, human-reviewed sentence
template per language, not guessing at a translation.

Only languages in i18n.languages.FULLY_SUPPORTED have templates. Any other
language falls back to English (see nlu.py), and the frontend clearly
labels that fallback rather than pretending it's native.
"""

MARKET_RECOMMENDATION = {
    "en": "For {quantity} kg of {crop} from {location}, {market} currently gives the best estimated net return of \u20b9{net_profit} (price \u20b9{price}/kg, {distance} km away, transport \u20b9{transport}).",
    "hi": "{location} से {quantity} किलो {crop} के लिए, {market} में अभी सबसे अच्छा अनुमानित शुद्ध लाभ ₹{net_profit} है (भाव ₹{price}/किलो, दूरी {distance} किमी, परिवहन ₹{transport})।",
    "mr": "{location} येथून {quantity} किलो {crop} साठी, {market} येथे सध्या सर्वोत्तम अंदाजित निव्वळ नफा ₹{net_profit} आहे (भाव ₹{price}/किलो, अंतर {distance} किमी, वाहतूक ₹{transport}).",
    "bn": "{location} থেকে {quantity} কেজি {crop}-এর জন্য, {market}-এ এখন সর্বোত্তম আনুমানিক নিট মুনাফা ₹{net_profit} (দাম ₹{price}/কেজি, দূরত্ব {distance} কিমি, পরিবহন ₹{transport})।",
    "ta": "{location} இலிருந்து {quantity} கிலோ {crop}-க்கு, {market} இல் தற்போது சிறந்த மதிப்பிடப்பட்ட நிகர லாபம் ₹{net_profit} (விலை ₹{price}/கிலோ, தூரம் {distance} கிமீ, போக்குவரத்து ₹{transport}).",
    "te": "{location} నుండి {quantity} కిలోల {crop} కోసం, {market} లో ప్రస్తుతం ఉత్తమ అంచనా నికర లాభం ₹{net_profit} (ధర ₹{price}/కిలో, దూరం {distance} కిమీ, రవాణా ₹{transport}).",
    "gu": "{location} થી {quantity} કિલો {crop} માટે, {market} માં હાલમાં શ્રેષ્ઠ અંદાજિત ચોખ્ખો નફો ₹{net_profit} છે (ભાવ ₹{price}/કિલો, અંતર {distance} કિમી, પરિવહન ₹{transport}).",
    "kn": "{location} ನಿಂದ {quantity} ಕೆಜಿ {crop} ಗೆ, {market} ನಲ್ಲಿ ಈಗ ಉತ್ತಮ ಅಂದಾಜು ನಿವ್ವಳ ಲಾಭ ₹{net_profit} (ಬೆಲೆ ₹{price}/ಕೆಜಿ, ದೂರ {distance} ಕಿಮೀ, ಸಾಗಣೆ ₹{transport}).",
    "ml": "{location} യിൽ നിന്ന് {quantity} കിലോ {crop}-ന്, {market} ൽ ഇപ്പോൾ ഏറ്റവും മികച്ച കണക്കാക്കിയ അറ്റാദായം ₹{net_profit} (വില ₹{price}/കിലോ, ദൂരം {distance} കിമീ, ഗതാഗതം ₹{transport}).",
    "pa": "{location} ਤੋਂ {quantity} ਕਿਲੋ {crop} ਲਈ, {market} ਵਿੱਚ ਹੁਣ ਸਭ ਤੋਂ ਵਧੀਆ ਅਨੁਮਾਨਿਤ ਸ਼ੁੱਧ ਲਾਭ ₹{net_profit} ਹੈ (ਭਾਅ ₹{price}/ਕਿਲੋ, ਦੂਰੀ {distance} ਕਿਮੀ, ਢੋਆ-ਢੁਆਈ ₹{transport}).",
    "or": "{location} ରୁ {quantity} କିଲୋ {crop} ପାଇଁ, {market} ରେ ବର୍ତ୍ତମାନ ସର୍ବୋତ୍ତମ ଆକଳିତ ନିଟ୍ ଲାଭ ₹{net_profit} (ମୂଲ୍ୟ ₹{price}/କିଲୋ, ଦୂରତା {distance} କିମି, ପରିବହନ ₹{transport}).",
    "as": "{location} ৰ পৰা {quantity} কিলো {crop} ৰ বাবে, {market} ত এতিয়া সৰ্বোত্তম আনুমানিক নীট মুনাফা ₹{net_profit} (দাম ₹{price}/কিলো, দূৰত্ব {distance} কিমি, পৰিবহন ₹{transport})।",
    "ur": "{location} سے {quantity} کلو {crop} کے لیے، {market} میں اس وقت بہترین تخمینی خالص منافع ₹{net_profit} ہے (قیمت ₹{price}/کلو، فاصلہ {distance} کلومیٹر، نقل و حمل ₹{transport})۔",
    "bho": "{location} से {quantity} किलो {crop} खातिर, {market} में अभी सबसे बढ़िया अनुमानित शुद्ध मुनाफा ₹{net_profit} बा (भाव ₹{price}/किलो, दूरी {distance} किमी, ढुलाई ₹{transport}).",
    "mai": "{location} स' {quantity} किलो {crop} लेल, {market} मे अखन सभसँ नीक अनुमानित शुद्ध लाभ ₹{net_profit} अछि (भाव ₹{price}/किलो, दूरी {distance} किमी, परिवहन ₹{transport}).",
}

CLARIFY_CROP = {
    "en": "I couldn't identify the crop. Which crop are you selling? (e.g. Tomato, Wheat, Soybean)",
    "hi": "मुझे फसल समझ नहीं आई। आप कौन सी फसल बेच रहे हैं? (जैसे टमाटर, गेहूं, सोयाबीन)",
    "mr": "मला पीक समजले नाही. तुम्ही कोणते पीक विकत आहात? (उदा. टोमॅटो, गहू, सोयाबीन)",
    "bn": "আমি ফসলটি বুঝতে পারিনি। আপনি কোন ফসল বিক্রি করছেন? (যেমন টমেটো, গম, সয়াবিন)",
    "ta": "பயிரை என்னால் அடையாளம் காண முடியவில்லை. நீங்கள் எந்தப் பயிரை விற்கிறீர்கள்? (எ.கா. தக்காளி, கோதுமை, சோயாபீன்)",
    "te": "పంటను గుర్తించలేకపోయాను. మీరు ఏ పంటను అమ్ముతున్నారు? (ఉదా. టమాటా, గోధుమ, సోయాబీన్)",
    "gu": "મને પાક સમજાયો નહીં. તમે કયો પાક વેચી રહ્યા છો? (દા.ત. ટામેટા, ઘઉં, સોયાબીન)",
    "kn": "ಬೆಳೆ ಗುರುತಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ನೀವು ಯಾವ ಬೆಳೆ ಮಾರಾಟ ಮಾಡುತ್ತಿದ್ದೀರಿ? (ಉದಾ. ಟೊಮೇಟೊ, ಗೋಧಿ, ಸೋಯಾಬೀನ್)",
    "ml": "വിള തിരിച്ചറിയാൻ കഴിഞ്ഞില്ല. നിങ്ങൾ ഏത് വിളയാണ് വിൽക്കുന്നത്? (ഉദാ: തക്കാളി, ഗോതമ്പ്, സോയാബീൻ)",
    "pa": "ਮੈਨੂੰ ਫ਼ਸਲ ਸਮਝ ਨਹੀਂ ਆਈ। ਤੁਸੀਂ ਕਿਹੜੀ ਫ਼ਸਲ ਵੇਚ ਰਹੇ ਹੋ? (ਜਿਵੇਂ ਟਮਾਟਰ, ਕਣਕ, ਸੋਇਆਬੀਨ)",
    "or": "ମୁଁ ଫସଲ ବୁଝିପାରିଲି ନାହିଁ। ଆପଣ କେଉଁ ଫସଲ ବିକ୍ରି କରୁଛନ୍ତି? (ଯଥା ଟମାଟୋ, ଗହମ, ସୋୟାବିନ)",
    "as": "মই শস্যটো বুজি নাপালোঁ। আপুনি কি শস্য বিক্ৰী কৰি আছে? (যেনে টমেটো, গম, সয়াবিন)",
    "ur": "مجھے فصل سمجھ نہیں آئی۔ آپ کون سی فصل بیچ رہے ہیں؟ (مثلاً ٹماٹر، گندم، سویابین)",
    "bho": "हमरा फसल समझ ना आइल। रउआ कवन फसल बेच रहल बानी? (जइसे टमाटर, गेहूं, सोयाबीन)",
    "mai": "हमरा फसल बुझल नहि गेल। अहाँ कोन फसल बेचि रहल छी? (जेना टमाटर, गहूम, सोयाबीन)",
}

PRICE_FORECAST_RESPONSE = {
    "en": "{crop} in {market}: current price \u20b9{current}/kg. Estimated in {days} day(s): \u20b9{low}-\u20b9{high}/kg (trend: {trend}).{demo_note} This is CropRetain's deterministic trend forecast, not AI/ML.",
    "hi": "{market} में {crop}: वर्तमान भाव ₹{current}/किलो। {days} दिन में अनुमानित: ₹{low}-₹{high}/किलो (रुझान: {trend})।{demo_note} यह क्रॉपरिटेन का निश्चयात्मक ट्रेंड पूर्वानुमान है, AI/ML नहीं।",
}

PRICE_FORECAST_UNAVAILABLE_RESPONSE = {
    "en": "Not enough historical price data for {crop} in {market} to build a forecast yet.",
    "hi": "{market} में {crop} के लिए अभी पर्याप्त ऐतिहासिक भाव डेटा नहीं है, इसलिए पूर्वानुमान संभव नहीं।",
}

CLARIFY_TWO_MARKETS = {
    "en": "I can compare markets for you -- please name two markets, e.g. \"compare {example_a} and {example_b}\".",
    "hi": "मैं बाज़ारों की तुलना कर सकता हूं -- कृपया दो बाज़ारों के नाम बताएं, जैसे \"{example_a} और {example_b} की तुलना करें\"।",
}

CLARIFY_LOCATION = {
    "en": "Which district or market are you selling from?",
    "hi": "आप किस जिले या मंडी से बेच रहे हैं?",
    "mr": "तुम्ही कोणत्या जिल्ह्यातून किंवा बाजारातून विकत आहात?",
    "bn": "আপনি কোন জেলা বা বাজার থেকে বিক্রি করছেন?",
    "ta": "நீங்கள் எந்த மாவட்டம் அல்லது சந்தையிலிருந்து விற்கிறீர்கள்?",
    "te": "మీరు ఏ జిల్లా లేదా మార్కెట్ నుండి అమ్ముతున్నారు?",
    "gu": "તમે કયા જિલ્લા અથવા બજારમાંથી વેચી રહ્યા છો?",
    "kn": "ನೀವು ಯಾವ ಜಿಲ್ಲೆ ಅಥವಾ ಮಾರುಕಟ್ಟೆಯಿಂದ ಮಾರಾಟ ಮಾಡುತ್ತಿದ್ದೀರಿ?",
    "ml": "നിങ്ങൾ ഏത് ജില്ലയിൽ നിന്നോ ചന്തയിൽ നിന്നോ ആണ് വിൽക്കുന്നത്?",
    "pa": "ਤੁਸੀਂ ਕਿਹੜੇ ਜ਼ਿਲ੍ਹੇ ਜਾਂ ਮੰਡੀ ਤੋਂ ਵੇਚ ਰਹੇ ਹੋ?",
    "or": "ଆପଣ କେଉଁ ଜିଲ୍ଲା କିମ୍ବା ବଜାରରୁ ବିକ୍ରି କରୁଛନ୍ତି?",
    "as": "আপুনি কোন জিলা বা বজাৰৰ পৰা বিক্ৰী কৰি আছে?",
    "ur": "آپ کس ضلع یا منڈی سے فروخت کر رہے ہیں؟",
    "bho": "रउआ कवन जिला भा मंडी से बेच रहल बानी?",
    "mai": "अहाँ कोन जिला या मंडी सँ बेचि रहल छी?",
}

# Shown when the selected language has no NLU/template support yet (honest fallback).
UNSUPPORTED_LANGUAGE_NOTE = {
    "en": "Full AI understanding for this language isn't available yet -- answering in English. You can also type in English or Hindi for best results.",
}


# Honest "no data source" responses -- used for intents CropRetain cannot
# genuinely answer (per the explicit instruction: never hallucinate).
NO_DATA_RESPONSE = {
    "en": "I don't have enough reliable data to answer that yet. I can help with where/when to sell {crop_hint}, price forecasts, transport cost, and profit calculations -- try asking one of those instead.",
    "hi": "मेरे पास अभी इसका भरोसेमंद जवाब देने के लिए पर्याप्त जानकारी नहीं है। मैं {crop_hint}कहाँ/कब बेचें, भाव पूर्वानुमान, परिवहन लागत और मुनाफ़ा गणना में मदद कर सकता हूं -- इनमें से कोई पूछें।",
    "mr": "याचे विश्वासार्ह उत्तर देण्यासाठी माझ्याकडे सध्या पुरेशी माहिती नाही. मी {crop_hint}कुठे/केव्हा विकावे, भाव अंदाज, वाहतूक खर्च आणि नफा गणना यात मदत करू शकतो.",
}

DISEASE_HELP_RESPONSE = {
    "en": "I'm CropRetain's market assistant, not a plant-disease diagnostic tool -- I don't have reliable data to diagnose crop health issues like this. For {crop_hint}leaf/pest problems, please consult your local Krishi Vigyan Kendra (KVK) or agricultural extension officer. I can help with selling, pricing, and market decisions once your crop is ready.",
    "hi": "मैं क्रॉपरिटेन का बाज़ार सहायक हूं, पौध-रोग निदान उपकरण नहीं -- इस तरह की फसल स्वास्थ्य समस्या का निदान करने के लिए मेरे पास भरोसेमंद जानकारी नहीं है। {crop_hint}पत्ती/कीट समस्या के लिए कृपया अपने नज़दीकी कृषि विज्ञान केंद्र (KVK) या कृषि विस्तार अधिकारी से संपर्क करें। फसल तैयार होने पर बिक्री, भाव और बाज़ार के फैसलों में मैं मदद कर सकता हूं।",
    "mr": "मी क्रॉपरिटेनचा बाजार सहाय्यक आहे, वनस्पती-रोग निदान साधन नाही -- अशा पीक आरोग्य समस्येचे निदान करण्यासाठी माझ्याकडे विश्वासार्ह माहिती नाही. {crop_hint}पान/कीड समस्येसाठी कृपया तुमच्या जवळच्या कृषी विज्ञान केंद्राशी (KVK) संपर्क साधा. पीक तयार झाल्यावर विक्री व बाजार निर्णयांत मी मदत करू शकतो.",
}

TRANSPORT_RESPONSE = {
    "en": "Estimated transport cost for {quantity} kg of {crop} from {location} to {market} ({distance} km): \u20b9{transport_cost} (based on CropRetain's standard per-km/per-tonne demo rate, not a live logistics quote).",
    "hi": "{location} से {market} ({distance} किमी) तक {quantity} किलो {crop} के परिवहन की अनुमानित लागत: ₹{transport_cost} (क्रॉपरिटेन की मानक प्रति-किमी/प्रति-टन डेमो दर पर आधारित, लाइव लॉजिस्टिक्स कोटेशन नहीं)।",
    "mr": "{location} ते {market} ({distance} किमी) पर्यंत {quantity} किलो {crop} च्या वाहतुकीचा अंदाजित खर्च: ₹{transport_cost} (क्रॉपरिटेनच्या प्रति-किमी/प्रति-टन डेमो दरावर आधारित, थेट लॉजिस्टिक्स कोट नाही).",
}

FARMPOOL_RESPONSE = {
    "en": "For {quantity} kg of {crop} from {location}, a shared transport plan to {market} could cut your cost to \u20b9{shared_cost} instead of \u20b9{individual_cost}. That saves about \u20b9{savings} ({savings_pct}%) and includes {partner_count} simulated nearby farmer(s) in the pool.",
    "hi": "{location} से {quantity} किलो {crop} के लिए, {market} तक साझा परिवहन योजना आपकी लागत को ₹{individual_cost} के बजाय ₹{shared_cost} तक कम कर सकती है। इससे लगभग ₹{savings} ({savings_pct}%) की बचत होगी और इसमें {partner_count} नकली/सिमुलेटेड आसपास के किसान शामिल हैं।",
}

PROFIT_RESPONSE = {
    "en": "Selling {quantity} kg of {crop} from {location} at {market} gives an estimated net profit of \u20b9{net_profit} (price \u20b9{price}/kg minus an estimated \u20b9{transport} transport). This covers price and transport only -- for a full breakdown including labour, packaging and storage costs, use the Profit Calculator.",
    "hi": "{location} से {quantity} किलो {crop} को {market} में बेचने पर अनुमानित शुद्ध लाभ ₹{net_profit} है (भाव ₹{price}/किलो घटाकर अनुमानित परिवहन ₹{transport})। यह केवल भाव और परिवहन को शामिल करता है -- मजदूरी, पैकेजिंग और भंडारण लागत सहित पूरी गणना के लिए प्रॉफिट कैलकुलेटर का उपयोग करें।",
}

BUYER_SEARCH_FOUND_RESPONSE = {
    "en": "I found {count} active buyer demand(s) for {crop}: {buyer_list}. Open Buyer Demands to see full details and connect.",
    "hi": "{crop} के लिए मुझे {count} सक्रिय खरीदार मांग मिली: {buyer_list}। पूरी जानकारी और संपर्क के लिए बायर डिमांड्स खोलें।",
}

BUYER_SEARCH_NONE_RESPONSE = {
    "en": "I couldn't find any active buyer demand for {crop} right now. Check Marketplace or Buyer Demands for updates, or post your lot so buyers can find you.",
    "hi": "अभी {crop} के लिए कोई सक्रिय खरीदार मांग नहीं मिली। अपडेट के लिए मार्केटप्लेस या बायर डिमांड्स देखें, या अपनी उपज पोस्ट करें ताकि खरीदार आपको ढूंढ सकें।",
}

MARKET_COMPARISON_RESPONSE = {
    "en": "For {quantity} kg of {crop}: {market_a} -- price \u20b9{price_a}/kg, {distance_a} km away, transport \u20b9{transport_a}, estimated net \u20b9{net_a}. {market_b} -- price \u20b9{price_b}/kg, {distance_b} km away, transport \u20b9{transport_b}, estimated net \u20b9{net_b}. {better_market} gives the better estimated net return.",
    "hi": "{quantity} किलो {crop} के लिए: {market_a} -- भाव ₹{price_a}/किलो, दूरी {distance_a} किमी, परिवहन ₹{transport_a}, अनुमानित शुद्ध ₹{net_a}। {market_b} -- भाव ₹{price_b}/किलो, दूरी {distance_b} किमी, परिवहन ₹{transport_b}, अनुमानित शुद्ध ₹{net_b}। {better_market} में बेहतर अनुमानित शुद्ध लाभ मिलता है।",
}

WEATHER_LIVE_DEMO_RESPONSE = {
    "en": "{status_label} weather for {location}: {condition}, {temp_max}\u00b0C / {temp_min}\u00b0C, {rain_prob}% rain chance, {humidity}% humidity. Source: {source}.",
    "hi": "{location} का {status_label} मौसम: {condition}, {temp_max}°C / {temp_min}°C, बारिश की संभावना {rain_prob}%, नमी {humidity}%। स्रोत: {source}।",
}

WEATHER_UNAVAILABLE_RESPONSE = {
    "en": "Weather data isn't available for {location} right now.",
    "hi": "अभी {location} के लिए मौसम जानकारी उपलब्ध नहीं है।",
}

# Shown when detect_intent() cannot confidently classify the question --
# never silently answered as a market recommendation (or anything else).
CLARIFY_INTENT_RESPONSE = {
    "en": "I can help with: market recommendations (where to sell), current or forecast prices, market comparisons, transport cost, profit, buyer demand, or weather. Could you rephrase your question to mention one of these?",
    "hi": "मैं इनमें मदद कर सकता हूं: बाज़ार सिफारिश (कहाँ बेचें), वर्तमान या अनुमानित भाव, बाज़ार तुलना, परिवहन लागत, मुनाफ़ा, खरीदार मांग, या मौसम। कृपया अपना सवाल इनमें से किसी एक के बारे में दोबारा पूछें।",
}

QUALITY_POINTER_RESPONSE = {
    "en": "To get a quality grade for your {crop_hint}crop, go to AgriMarket -> Post your harvest -> upload a photo for a real image-based assessment (brightness/color/texture analysis of your actual photo -- clearly marked as a demo assessment, not a certified lab grading).",
    "hi": "अपनी {crop_hint}फसल की गुणवत्ता ग्रेड पाने के लिए, एग्रीमार्केट -> अपनी फसल पोस्ट करें -> पर जाकर एक असली फोटो-आधारित मूल्यांकन के लिए तस्वीर अपलोड करें (आपकी असली फोटो का brightness/रंग/बनावट विश्लेषण -- स्पष्ट रूप से डेमो मूल्यांकन के रूप में चिह्नित, प्रमाणित लैब ग्रेडिंग नहीं)।",
    "mr": "तुमच्या {crop_hint}पिकाची गुणवत्ता ग्रेड मिळवण्यासाठी, अ‍ॅग्रीमार्केट -> तुमचे पीक पोस्ट करा -> वर जाऊन खऱ्या फोटो-आधारित मूल्यांकनासाठी फोटो अपलोड करा (तुमच्या खऱ्या फोटोचे brightness/रंग/पोत विश्लेषण -- डेमो मूल्यांकन म्हणून स्पष्टपणे चिन्हांकित, प्रमाणित लॅब ग्रेडिंग नाही).",
}


# PRICE_LOOKUP: {price_line} is a pre-built fact string (live/demo/no-data)
# assembled in assistant.py from app.routers.market._get_price's own
# honest status field -- this template only wraps it in a native-language
# sentence, it never re-decides live vs demo itself.
PRICE_LOOKUP_RESPONSE = {
    "en": "{crop} in {market}: {price_line}",
    "hi": "{market} में {crop}: {price_line}",
}


def render_no_data(language: str, crop: str = None) -> str:
    tpl = NO_DATA_RESPONSE.get(language, NO_DATA_RESPONSE["en"])
    crop_hint = f"{crop} " if crop else ""
    return tpl.format(crop_hint=crop_hint)


def render_disease_help(language: str, crop: str = None) -> str:
    tpl = DISEASE_HELP_RESPONSE.get(language, DISEASE_HELP_RESPONSE["en"])
    crop_hint = f"{crop} " if crop else "your "
    return tpl.format(crop_hint=crop_hint)


def render_transport(language: str, **kwargs) -> str:
    tpl = TRANSPORT_RESPONSE.get(language, TRANSPORT_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_farmpool(language: str, **kwargs) -> str:
    tpl = FARMPOOL_RESPONSE.get(language, FARMPOOL_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_quality_pointer(language: str, crop: str = None) -> str:
    tpl = QUALITY_POINTER_RESPONSE.get(language, QUALITY_POINTER_RESPONSE["en"])
    crop_hint = f"{crop} " if crop else ""
    return tpl.format(crop_hint=crop_hint)


def render_market_recommendation(language: str, **kwargs) -> str:
    tpl = MARKET_RECOMMENDATION.get(language, MARKET_RECOMMENDATION["en"])
    return tpl.format(**kwargs)


def render_clarify_crop(language: str) -> str:
    return CLARIFY_CROP.get(language, CLARIFY_CROP["en"])


def render_clarify_location(language: str) -> str:
    return CLARIFY_LOCATION.get(language, CLARIFY_LOCATION["en"])


def render_price_lookup(language: str, **kwargs) -> str:
    tpl = PRICE_LOOKUP_RESPONSE.get(language, PRICE_LOOKUP_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_profit(language: str, **kwargs) -> str:
    tpl = PROFIT_RESPONSE.get(language, PROFIT_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_buyer_search_found(language: str, **kwargs) -> str:
    tpl = BUYER_SEARCH_FOUND_RESPONSE.get(language, BUYER_SEARCH_FOUND_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_buyer_search_none(language: str, crop: str) -> str:
    tpl = BUYER_SEARCH_NONE_RESPONSE.get(language, BUYER_SEARCH_NONE_RESPONSE["en"])
    return tpl.format(crop=crop)


def render_market_comparison(language: str, **kwargs) -> str:
    tpl = MARKET_COMPARISON_RESPONSE.get(language, MARKET_COMPARISON_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_weather(language: str, **kwargs) -> str:
    tpl = WEATHER_LIVE_DEMO_RESPONSE.get(language, WEATHER_LIVE_DEMO_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_weather_unavailable(language: str, location: str) -> str:
    tpl = WEATHER_UNAVAILABLE_RESPONSE.get(language, WEATHER_UNAVAILABLE_RESPONSE["en"])
    return tpl.format(location=location)


def render_clarify_intent(language: str) -> str:
    return CLARIFY_INTENT_RESPONSE.get(language, CLARIFY_INTENT_RESPONSE["en"])


def render_clarify_two_markets(language: str, example_a: str, example_b: str) -> str:
    tpl = CLARIFY_TWO_MARKETS.get(language, CLARIFY_TWO_MARKETS["en"])
    return tpl.format(example_a=example_a, example_b=example_b)


def render_price_forecast(language: str, **kwargs) -> str:
    tpl = PRICE_FORECAST_RESPONSE.get(language, PRICE_FORECAST_RESPONSE["en"])
    return tpl.format(**kwargs)


def render_price_forecast_unavailable(language: str, crop: str, market: str) -> str:
    tpl = PRICE_FORECAST_UNAVAILABLE_RESPONSE.get(language, PRICE_FORECAST_UNAVAILABLE_RESPONSE["en"])
    return tpl.format(crop=crop, market=market)
