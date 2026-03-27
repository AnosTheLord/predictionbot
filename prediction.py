import random
import asyncio
import requests
import datetime
import os
import json
import time
from telegram import Bot
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# =========================
# 🔐 ENV
# =========================
TOKEN = os.getenv("TOKEN")
CHANNELS = os.getenv("CHANNELS")
CRIC_API_KEY = os.getenv("CRIC_API_KEY")

bot = Bot(token=TOKEN)

# =========================
# ⚙️ CONFIG
# =========================
POST_INTERVAL = 600
LIVE_POLL_INTERVAL = 900
TOSS_INTERVAL = 1200
START_BEFORE = 4

# =========================
# 🕒 IST
# =========================
from datetime import timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))

# =========================
# 💾 DATABASE
# =========================
DB_FILE = "db.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {}
    try:
        with open(DB_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_db(data):
    with open(DB_FILE, "w") as f:
        json.dump(data, f, indent=2)

db = load_db()

# =========================
# 📡 CHANNELS
# =========================
def get_channels():
    return [c.strip() for c in CHANNELS.split(",") if c.strip()]

async def send_all_message(text):
    for ch in get_channels():
        try:
            await bot.send_message(ch, text)
        except Exception as e:
            print("Msg error:", e)

async def send_all_photo(path):
    for ch in get_channels():
        try:
            with open(path, "rb") as p:
                await bot.send_photo(ch, p)
        except Exception as e:
            print("Photo error:", e)

async def send_all_poll(q, options):
    for ch in get_channels():
        try:
            await bot.send_poll(ch, q, options, is_anonymous=False)
        except Exception as e:
            print("Poll error:", e)

# =========================
# 🏏 TEAM NORMALIZATION
# =========================
ALIASES = {
    "RCB": "Royal Challengers Bengaluru",
    "MI": "Mumbai Indians",
    "CSK": "Chennai Super Kings",
    "KKR": "Kolkata Knight Riders",
    "SRH": "Sunrisers Hyderabad",
    "DC": "Delhi Capitals",
    "RR": "Rajasthan Royals",
    "GT": "Gujarat Titans",
    "LSG": "Lucknow Super Giants",
    "PBKS": "Punjab Kings"
}

def norm(t):
    return ALIASES.get(t, t)

# =========================
# 🌍 MATCHES
# =========================
def get_today_matches():
    try:
        url = f"https://api.cricapi.com/v1/cricScore?apikey={CRIC_API_KEY}"
        data = requests.get(url).json()

        today = str(datetime.date.today())
        res = []

        for m in data.get("data", []):
            dt = m.get("dateTimeGMT")
            t1 = norm(m.get("t1"))
            t2 = norm(m.get("t2"))

            if not (dt and t1 and t2):
                continue
            if today not in dt:
                continue
            if "IPL" not in m.get("series",""):
                continue

            mt = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")

            res.append({"t1": t1, "t2": t2, "time": mt})

        return res

    except Exception as e:
        print("Fetch error:", e)
        return []

# =========================
# 🧠 PREDICTION (DB LOCK)
# =========================
def predict(t1, t2):
    key = f"{t1}_{t2}"

    if key in db:
        return db[key]

    winner = random.choice([t1, t2])
    toss = random.choice([t1, t2])

    data = {
        "winner": winner,
        "toss": toss
    }

    db[key] = data
    save_db(db)

    return data

# =========================
# 🎯 TOSS MESSAGE
# =========================
def toss_msg(t1, t2, toss):
    return random.choice([
        f"🔵 AI TOSS SIGNAL\n🏏 {t1} vs {t2}\n⚡ Toss: {toss}",
        f"🔴 FINAL TOSS\n🏏 {t1} vs {t2}\n🚨 {toss}",
        f"🟣 VIP TOSS\n🏏 {t1} vs {t2}\n🎯 {toss}"
    ])

# =========================
# 🎨 POSTER
# =========================
def create_poster(t1, t2, title):
    img = Image.new("RGB", (800, 800), (15, 15, 30))
    d = ImageDraw.Draw(img)

    d.text((120, 250), f"{t1} vs {t2}", fill="white")
    d.text((120, 400), title, fill="yellow")

    path = f"poster_{int(time.time())}.png"
    img.save(path)
    return path

# =========================
# 🧠 MEMORY
# =========================
announced = db.get("announced", {})
live_sent = db.get("live_sent", {})
last_post = {}
last_poll = {}
last_toss = {}

# =========================
# 🚀 MAIN LOOP
# =========================
async def run_bot():
    global db

    while True:
        try:
            now = datetime.datetime.now(IST)
            matches = get_today_matches()

            for m in matches:
                t1, t2 = m["t1"], m["t2"]
                mt = m["time"] + timedelta(hours=5, minutes=30)
                key = f"{t1}_{t2}"

                start = mt - timedelta(hours=START_BEFORE)

                # =========================
                # 🎯 TOSS LOOP
                # =========================
                if start <= now <= mt:

                    last = last_toss.get(key)

                    if not last or (now-last).total_seconds()>TOSS_INTERVAL:

                        p = predict(t1, t2)

                        await send_all_message(toss_msg(t1, t2, p["toss"]))
                        await send_all_photo(create_poster(t1, t2, "Toss Prediction"))

                        last_toss[key] = now

                # =========================
                # 📊 MATCH POSTS
                # =========================
                if start <= now <= mt:

                    last = last_post.get(key)

                    if not last or (now-last).total_seconds()>POST_INTERVAL:

                        p = predict(t1, t2)

                        await send_all_message(f"🔥 {t1} vs {t2}\nWinner: {p['winner']}")
                        await send_all_photo(create_poster(t1, t2, p["winner"]))

                        last_post[key] = now

                # =========================
                # 🟢 LIVE
                # =========================
                if now >= mt:

                    if key not in live_sent:
                        await send_all_message(f"🔥 MATCH LIVE\n{t1} vs {t2}")
                        live_sent[key] = True
                        db["live_sent"] = live_sent
                        save_db(db)

                    last = last_poll.get(key)

                    if not last or (now-last).total_seconds()>LIVE_POLL_INTERVAL:
                        await send_all_poll(f"{t1} vs {t2}", [t1, t2])
                        last_poll[key] = now

            await asyncio.sleep(60)

        except Exception as e:
            print("Error:", e)
            await asyncio.sleep(60)

# =========================
# ▶️ START
# =========================
if __name__ == "__main__":
    asyncio.run(run_bot())
