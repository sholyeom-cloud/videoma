# content_source.py
import os
import json
import openai
from datetime import datetime

# Set your API key via the env variable OPENAI_API_KEY (added to GitHub Secrets)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Edit/extend this list with the anime/manga you want covered
ANIME_TITLES = [
    "One Piece",
    "Naruto",
    "Attack on Titan",
    "Fullmetal Alchemist: Brotherhood",
    "Demon Slayer",
    "Jujutsu Kaisen",
    "Death Note",
    "Bleach",
    "My Hero Academia",
    "Chainsaw Man",
    "Spy x Family",
    "Mob Psycho 100",
    "Hunter x Hunter",
    "Haikyuu!!",
    "Tokyo Revengers",
]

def _call_openai_for(title: str):
    system = (
        "You are a friendly short-video writer. Produce a very short JSON object only — nothing else."
        " The JSON must have keys: subtitle (<=8 words), narration (1-2 sentences, no spoilers), hashtags (array of up to 4 hashtags)."
        " Tone: energetic and concise. Avoid spoilers. Do not include extraneous explanation."
    )

    user = (
        f"Create content for this anime/manga title:\n\nTitle: {title}\n\n"
        "Return JSON only, for example:\n"
        '{\"subtitle\":\"Hook here\",\"narration\":\"Two-sentence pitch...\",\"hashtags\":[\"#anime\",\"#shonen\"]}'
    )

    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        content = resp["choices"][0]["message"]["content"].strip()
        # Some models may wrap JSON in backticks or text; try to extract JSON substring
        first = content.find("{")
        last = content.rfind("}")
        if first != -1 and last != -1:
            json_str = content[first:last+1]
        else:
            json_str = content
        data = json.loads(json_str)
        return data
    except Exception as e:
        # fallback safe defaults
        print("OpenAI call failed:", e)
        return {
            "subtitle": "Discover this series",
            "narration": f"{title} — a must-watch. Quick description unavailable.",
            "hashtags": ["#anime"],
        }

def get_today_content():
    # Deterministic selection by UTC day so re-runs on the same date produce the same title
    idx = int(datetime.utcnow().strftime("%Y%j")) % len(ANIME_TITLES)
    title = ANIME_TITLES[idx]
    ai_result = _call_openai_for(title)
    return {
        "title": title,
        "subtitle": ai_result.get("subtitle", ""),
        "body": ai_result.get("narration", ""),
        "hashtags": ai_result.get("hashtags", []),
    }

if __name__ == "__main__":
    print(get_today_content())
