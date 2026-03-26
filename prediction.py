import random
import asyncio
import requests
import datetime
import os
from telegram import Bot
from PIL import Image, ImageDraw, ImageFont
from google import genai

# =========================
# 🔐 ENV
# =========================
TOKEN = os.getenv("TOKEN")
CHANNELS = os.getenv("CHANNELS")  # @ch1,@ch2
CRIC_API_KEY = os.getenv("CRIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# =========================
# 📡 MULTI CHANNEL
# =========================
def get_channels():
    return [c.strip() for c in CHANNELS.split(",") if c.strip()]

async def send_all_message(text, parse_mode=None):
    for ch in get_channels():
        try:
            await bot.send_message(ch, text, parse_mode=parse_mode)
        except Exception as e:
            print(f"❌ {ch} msg error:", e)

async def send_all_photo(path):
    for ch in get_channels():
        try:
            with open(path, "rb") as p:
                await bot.send_photo(ch, p)
        except Exception as e:
            print(f"❌ {ch} photo error:", e)

async def send_all_poll(t1, t2):
    for ch in get_channels():
        try:
            await bot.send_poll(
                ch,
                f"{t1} vs {t2} - Who wins?",
                [t1, t2],
                is_anonymous=False
            )
        except Exception as e:
            print(f"❌ {ch} poll error:", e)

# =========================
# ⚙️ CONFIG
# =========================
POST_INTERVAL = 1800
START_BEFORE = 4
LIVE_URGENCY_INTERVAL = 1200

# =========================
# 🧠 MEMORY
# =========================
prediction_cache = {}
last_post_time = {}
match_started = {}
last_urgency = {}

# =========================
# 🌍 FILTER
# =========================
INTERNATIONAL = [
    "india","australia","england","pakistan",
    "new zealand","south africa","sri lanka",
    "bangladesh","west indies"
]

def is_valid(t1, t2):
    t1, t2 = t1.lower(), t2.lower()
    if "india" in t1 or "india" in t2:
        return True
    if any(x in t1 for x in INTERNATIONAL) and any(x in t2 for x in INTERNATIONAL):
        return True
    return False

# =========================
# 🌍 MATCHES
# =========================
def get_matches():
    try:
        url = f"https://api.cricapi.com/v1/cricScore?apikey={CRIC_API_KEY}"
        data = requests.get(url).json()

        today = str(datetime.date.today())
        res = []

        for m in data.get("data", []):
            dt = m.get("dateTimeGMT")
            t1 = m.get("t1")
            t2 = m.get("t2")

            if not (dt and t1 and t2):
                continue
            if today not in dt:
                continue
            if not is_valid(t1, t2):
                continue

            try:
                mt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")
            except:
                continue

            res.append({"t1": t1, "t2": t2, "time": mt})

        return res
    except:
        return []

# =========================
# 🧠 AI
# =========================
def predict(t1, t2):
    key = f"{t1}_{t2}"

    if key in prediction_cache:
        return prediction_cache[key]

    winner = random.choice([t1, t2])
    toss = random.choice([t1, t2])

    try:
        r = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"{t1} vs {t2}. Predict winner shortly."
        )
        reason = r.text.strip()
    except:
        reason = f"{winner} looks stronger."

    data = {"winner": winner, "toss": toss, "reason": reason}
    prediction_cache[key] = data
    return data

# =========================
# 🎨 TOSS THEMES
# =========================
def toss_post(t1, t2, toss):
    themes = [
        f"🔵 AI TOSS SIGNAL\n🏏 {t1} vs {t2}\n⚡ Toss: {toss}",
        f"🔴 FINAL TOSS\n🏏 {t1} vs {t2}\n🚨 {toss}",
        f"🟡 PREMIUM\n🏏 {t1} vs {t2}\n💎 {toss}",
        f"🟢 SAFE PICK\n🏏 {t1} vs {t2}\n✅ {toss}",
        f"🟣 VIP SIGNAL\n🏏 {t1} vs {t2}\n🎯 {toss}"
    ]
    return random.choice(themes)

# =========================
# 🎭 MATCH POST
# =========================
def match_post(t1, t2, p):
    return f"🔥 {t1} vs {t2}\nWinner: {p['winner']}\n{p['reason']}"

# =========================
# 🎨 POSTER v2
# =========================
def poster(t1, t2, w):
    img = Image.new("RGB", (900, 900))
    d = ImageDraw.Draw(img)

    for y in range(900):
        d.line([(0,y),(900,y)], fill=(20+y//5,20,40+y//3))

    d.text((200,300),f"{t1} vs {t2}",fill="white")
    d.rectangle([150,650,750,780], fill=(0,0,0))
    d.text((200,690),f"WINNER: {w}",fill=(255,215,0))

    path = f"{t1}_{t2}.png"
    img.save(path)
    return path

# =========================
# 🚨 URGENCY
# =========================
def urgency(t1, t2):
    return random.choice([
        f"🚨 LIVE {t1} vs {t2}",
        f"🔥 GAME ON {t1} vs {t2}",
        f"⚡ FINAL CALL {t1} vs {t2}"
    ])

# =========================
# 🚀 MAIN LOOP
# =========================
async def run_bot():
    while True:
        try:
            now = datetime.datetime.utcnow()
            matches = get_matches()

            for m in matches:
                t1, t2 = m["t1"], m["t2"]
                mt = m["time"]
                key = f"{t1}_{t2}"

                start = mt - datetime.timedelta(hours=START_BEFORE)

                # PRE MATCH
                if start <= now <= mt:
                    last = last_post_time.get(key)
                    if not last or (now-last).total_seconds() > POST_INTERVAL:

                        p = predict(t1, t2)

                        await send_all_message(toss_post(t1, t2, p["toss"]))
                        await send_all_message(match_post(t1, t2, p))

                        img = poster(t1, t2, p["winner"])
                        await send_all_photo(img)

                        last_post_time[key] = now

                # MATCH START
                if now >= mt:

                    if key not in match_started:
                        await send_all_poll(t1, t2)
                        await send_all_message(urgency(t1, t2))
                        match_started[key] = True

                    last_u = last_urgency.get(key)
                    if not last_u or (now-last_u).total_seconds() > LIVE_URGENCY_INTERVAL:
                        await send_all_message(urgency(t1, t2))
                        last_urgency[key] = now

            await asyncio.sleep(60)

        except Exception as e:
            print("❌ Error:", e)
            await asyncio.sleep(60)

# =========================
# ▶️ START
# =========================
if __name__ == "__main__":
    asyncio.run(run_bot())
