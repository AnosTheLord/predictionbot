import random
import asyncio
import requests
import datetime
import os
from telegram import Bot
from PIL import Image, ImageDraw
from google import genai

# =========================
# 🔐 ENV VARIABLES
# =========================
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CRIC_API_KEY = os.getenv("CRIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# =========================
# ⚙️ CONFIG
# =========================
POST_INTERVAL = 1800          # 30 min
START_BEFORE = 4              # 4 hours before match
LIVE_URGENCY_INTERVAL = 1200  # 20 min

CONFIDENCE_MIN = 78
CONFIDENCE_MAX = 92

ENABLE_POSTER = True

# =========================
# 🧠 MEMORY
# =========================
prediction_cache = {}
last_post_time = {}
match_started_tracker = {}
last_urgency_time = {}

# =========================
# 🌍 TEAM FILTER
# =========================
INTERNATIONAL_TEAMS = [
    "india", "australia", "england", "pakistan",
    "new zealand", "south africa", "sri lanka",
    "bangladesh", "west indies"
]

def is_valid_match(t1, t2):
    t1 = t1.lower()
    t2 = t2.lower()

    if "india" in t1 or "india" in t2:
        return True

    if any(t in t1 for t in INTERNATIONAL_TEAMS) and any(t in t2 for t in INTERNATIONAL_TEAMS):
        return True

    return False

# =========================
# 🌍 GET MATCHES
# =========================
def get_today_matches():
    try:
        url = f"https://api.cricapi.com/v1/cricScore?apikey={CRIC_API_KEY}"
        data = requests.get(url).json()

        matches = data.get("data", [])
        today = str(datetime.date.today())

        result = []

        for m in matches:
            dt = m.get("dateTimeGMT")
            t1 = m.get("t1")
            t2 = m.get("t2")
            status = m.get("status", "Upcoming")

            if not (dt and t1 and t2):
                continue

            if today not in dt:
                continue

            if not is_valid_match(t1, t2):
                continue

            try:
                match_time = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
            except:
                continue

            result.append({
                "team1": t1,
                "team2": t2,
                "time": match_time,
                "status": status
            })

        return result

    except Exception as e:
        print("❌ Fetch Error:", e)
        return []

# =========================
# 🧠 AI PREDICTION
# =========================
def get_prediction(t1, t2):
    key = f"{t1}_{t2}"

    if key in prediction_cache:
        return prediction_cache[key]

    winner = random.choice([t1, t2])
    toss = random.choice([t1, t2])
    confidence = random.randint(CONFIDENCE_MIN, CONFIDENCE_MAX)

    prompt = f"""
Match: {t1} vs {t2}
Predict {winner} will win.
Give short reasoning (1-2 lines).
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        reason = response.text.strip()
    except Exception as e:
        print("Gemini Error:", e)
        reason = f"{winner} looks stronger based on recent form."

    prediction = {
        "winner": winner,
        "toss": toss,
        "confidence": confidence,
        "reason": reason
    }

    prediction_cache[key] = prediction
    return prediction

# =========================
# 🎭 MULTI FORMAT POSTS
# =========================
def generate_post(t1, t2, pred):
    formats = [

        f"""🔥 MATCH ALERT 🔥
🏏 {t1} vs {t2}

👉 Winner: {pred['winner']}
📊 Confidence: {pred['confidence']}%
""",

        f"""⚡ BIG GAME COMING ⚡

{t1} 🆚 {t2}

👀 {pred['reason']}

🔥 Pick: {pred['winner']}
""",

        f"""📊 EXPERT ANALYSIS

{t1} vs {t2}

💬 {pred['reason']}

🎯 Prediction: {pred['winner']}
""",

        f"""💣 HIGH VOLTAGE MATCH

🏏 {t1} vs {t2}

👉 Toss: {pred['toss']}
👉 Winner: {pred['winner']}
"""
    ]

    return random.choice(formats)

# =========================
# 🎨 POSTER
# =========================
def create_poster(t1, t2, winner):
    img = Image.new("RGB", (800, 800), (15, 15, 30))
    draw = ImageDraw.Draw(img)

    draw.text((120, 250), f"{t1} vs {t2}", fill="white")
    draw.text((120, 400), f"Winner: {winner}", fill="yellow")

    path = f"{t1}_{t2}.png"
    img.save(path)
    return path

# =========================
# 📊 POLL
# =========================
async def send_match_poll(t1, t2):
    await bot.send_poll(
        chat_id=CHANNEL_ID,
        question=f"🏏 {t1} vs {t2}\nWho will win?",
        options=[t1, t2],
        is_anonymous=False
    )

# =========================
# 🚨 URGENCY POSTS
# =========================
def urgency_post(t1, t2):
    msgs = [
        f"🚨 MATCH STARTED 🚨\n\n🏏 {t1} vs {t2}\n⚠️ Last chance!",
        f"🔥 LIVE NOW 🔥\n\n{t1} vs {t2}\n👀 Smart users ready...",
        f"⚡ GAME ON ⚡\n\n{t1} vs {t2}\n💣 Big moves incoming!",
        f"🚨 FINAL CALL 🚨\n\n{t1} vs {t2}\n📊 Don’t miss!"
    ]
    return random.choice(msgs)

# =========================
# 🚀 MAIN LOOP
# =========================
async def run_bot():
    while True:
        try:
            now = datetime.datetime.utcnow()
            matches = get_today_matches()

            if not matches:
                print("⛔ No matches today")
                await asyncio.sleep(3600)
                continue

            for m in matches:
                t1 = m["team1"]
                t2 = m["team2"]
                match_time = m["time"]

                key = f"{t1}_{t2}"
                start_time = match_time - datetime.timedelta(hours=START_BEFORE)

                # =========================
                # 🟡 PRE-MATCH POSTS
                # =========================
                if start_time <= now <= match_time:

                    last_time = last_post_time.get(key)

                    if not last_time or (now - last_time).total_seconds() > POST_INTERVAL:

                        pred = get_prediction(t1, t2)
                        msg = generate_post(t1, t2, pred)

                        await bot.send_message(chat_id=CHANNEL_ID, text=msg)

                        if ENABLE_POSTER:
                            poster = create_poster(t1, t2, pred["winner"])
                            with open(poster, "rb") as p:
                                await bot.send_photo(chat_id=CHANNEL_ID, photo=p)

                        last_post_time[key] = now
                        print(f"✅ Pre-match post: {t1} vs {t2}")

                # =========================
                # 🟢 MATCH START ACTION
                # =========================
                if now >= match_time:

                    if key not in match_started_tracker:

                        await send_match_poll(t1, t2)

                        await bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=urgency_post(t1, t2)
                        )

                        match_started_tracker[key] = True
                        print(f"🚀 Match started: {t1} vs {t2}")

                    # 🔁 LIVE URGENCY LOOP
                    last_u = last_urgency_time.get(key)

                    if not last_u or (now - last_u).total_seconds() > LIVE_URGENCY_INTERVAL:

                        await bot.send_message(
                            chat_id=CHANNEL_ID,
                            text=urgency_post(t1, t2)
                        )

                        last_urgency_time[key] = now
                        print(f"⚡ Live urgency: {t1} vs {t2}")

            await asyncio.sleep(60)

        except Exception as e:
            print("❌ Error:", e)
            await asyncio.sleep(60)

# =========================
# ▶️ START
# =========================
if __name__ == "__main__":
    asyncio.run(run_bot())
