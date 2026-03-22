import random
import asyncio
import requests
import datetime
import os
from telegram import Bot
from PIL import Image, ImageDraw, ImageFont
from google import genai   # ✅ NEW GEMINI SDK

# 🔐 ENV VARIABLES
TOKEN = os.getenv("TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")
CRIC_API_KEY = os.getenv("CRIC_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = Bot(token=TOKEN)

# 🔑 Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# 🔒 Prediction cache
prediction_cache = {}

# 🌍 INTERNATIONAL TEAMS
INTERNATIONAL_TEAMS = [
    "india", "australia", "england", "pakistan",
    "new zealand", "south africa", "sri lanka",
    "bangladesh", "west indies", "afghanistan",
    "ireland", "zimbabwe", "netherlands"
]

# 🔄 TEAM NAME NORMALIZATION
ALIASES = {
    "ind": "india",
    "aus": "australia",
    "eng": "england",
    "pak": "pakistan",
    "nz": "new zealand",
    "sa": "south africa",
    "sl": "sri lanka",
    "wi": "west indies"
}

def normalize(name):
    name = name.lower()
    for k, v in ALIASES.items():
        if k in name:
            return v
    return name

# 🎯 FILTER LOGIC
def is_valid_match(team1, team2):
    t1 = normalize(team1)
    t2 = normalize(team2)

    # 🇮🇳 Always allow India matches
    if "india" in t1 or "india" in t2:
        return True

    # 🌍 Both international → allow
    if any(t in t1 for t in INTERNATIONAL_TEAMS) and any(t in t2 for t in INTERNATIONAL_TEAMS):
        return True

    return False

# 🌍 GET MATCHES
def get_today_matches():
    try:
        url = f"https://api.cricapi.com/v1/cricScore?apikey={CRIC_API_KEY}"
        data = requests.get(url).json()

        matches = data.get("data", [])
        today = str(datetime.date.today())

        filtered = []

        for m in matches:
            dt = m.get("dateTimeGMT", "")
            status = m.get("status", "Upcoming")
            t1 = m.get("t1")
            t2 = m.get("t2")

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

            filtered.append({
                "team1": t1,
                "team2": t2,
                "status": status,
                "time": match_time
            })

        # ⏰ SORT (Upcoming → Live)
        filtered.sort(key=lambda x: (
            0 if "Upcoming" in x["status"] else 1,
            x["time"]
        ))

        return filtered

    except Exception as e:
        print("❌ Fetch Error:", e)
        return []

# 🧠 GEMINI AI PREDICTION
def gemini_prediction(team1, team2):
    key = f"{team1}_vs_{team2}"

    if key in prediction_cache:
        return prediction_cache[key]

    winner = team1 if random.random() > 0.55 else team2
    toss = random.choice([team1, team2])
    confidence = random.randint(78, 92)

    style = random.choice([
        "confident expert tone",
        "bold aggressive tone",
        "analytical tone"
    ])

    prompt = f"""
You are a professional cricket analyst.

Match: {team1} vs {team2}

Predict that {winner} will win.

Write in a {style}.
Give a short reasoning (2 lines max).
Do not mention AI.
"""

    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt
        )
        reason = response.text.strip()
    except Exception as e:
        print("Gemini error:", e)
        reason = f"{winner} looks stronger based on squad balance and recent form."

    prediction = {
        "winner": winner,
        "toss": toss,
        "confidence": confidence,
        "reason": reason
    }

    prediction_cache[key] = prediction
    return prediction

# 🎨 POSTER
def create_poster(team1, team2, winner):
    img = Image.new("RGB", (900, 900), (15, 15, 30))
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("arial.ttf", 60)
        team_font = ImageFont.truetype("arial.ttf", 50)
        winner_font = ImageFont.truetype("arial.ttf", 55)
    except:
        title_font = ImageFont.load_default()
        team_font = ImageFont.load_default()
        winner_font = ImageFont.load_default()

    draw.text((150, 80), "MATCH PREDICTION", fill=(255, 215, 0), font=title_font)
    draw.text((200, 300), team1, fill="white", font=team_font)
    draw.text((350, 380), "VS", fill="cyan", font=team_font)
    draw.text((200, 460), team2, fill="white", font=team_font)
    draw.text((200, 650), f"WINNER: {winner}", fill="yellow", font=winner_font)

    path = f"{team1}_vs_{team2}.png"
    img.save(path)
    return path

# ✍️ MESSAGE
def format_msg(team1, team2, status, pred):
    return f"""
🔥 *MATCH PREDICTION* 🔥

🏏 *{team1} vs {team2}*

📡 Status: {status}

🤖 AI Insight:
{pred['reason']}

📊 Confidence: {pred['confidence']}%

👉 Toss: {pred['toss']}
👉 Winner: {pred['winner']}

💬 YES KARO 👍
"""

# 🧲 ENGAGEMENT
def engagement_post():
    return random.choice([
        "🔥 Big match coming... experts confused 🤯",
        "💥 Insider update dropping soon...",
        "⚠️ This match is risky...",
        "👀 Smart users already know..."
    ])

# 🚀 MAIN LOOP
async def run_bot():
    while True:
        try:
            matches = get_today_matches()

            if not matches:
                print("⛔ No matches today")
                await asyncio.sleep(3600)
                continue

            for m in matches:
                t1, t2 = m["team1"], m["team2"]

                pred = gemini_prediction(t1, t2)
                msg = format_msg(t1, t2, m["status"], pred)

                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=msg,
                    parse_mode="Markdown"
                )

                poster = create_poster(t1, t2, pred["winner"])
                with open(poster, "rb") as photo:
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=photo)

                print(f"✅ Posted {t1} vs {t2}")

                await asyncio.sleep(1800)

            # engagement
            await bot.send_message(chat_id=CHANNEL_ID, text=engagement_post())
            await asyncio.sleep(2700)

        except Exception as e:
            print("❌ Error:", e)
            await asyncio.sleep(60)

# ▶️ START
if __name__ == "__main__":
    asyncio.run(run_bot())
