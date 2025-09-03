# video_generator.py
import os
import tempfile
import shutil
from datetime import datetime
import yaml
import numpy as np
from gtts import gTTS
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip,
    ImageClip,
    CompositeVideoClip,
    AudioFileClip,
    CompositeAudioClip,
    ColorClip,
)
from content_source import get_today_content
from email_utils import send_email_with_attachment

BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
OUTPUT_DIR = BASE_DIR / "output"
CONFIG_PATH = BASE_DIR / "templates" / "config.yaml"

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

def hex_to_rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def make_text_image(text, font_path, font_size, max_width, fill="#FFFFFF", stroke_fill="#000000"):
    # Create a PIL image with transparent background that wraps the text
    font = ImageFont.truetype(str(font_path), font_size)
    # naive word-wrap
    words = text.split()
    lines = []
    cur = ""
    for w in words:
        test = (cur + " " + w).strip()
        size = font.getsize(test)[0]
        if size <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    # calculate image size (approx)
    line_height = font.getsize("Ay")[1] + 6
    img_h = line_height * len(lines) + 10
    img_w = max_width
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = 5
    for line in lines:
        w, h = draw.textsize(line, font=font)
        x = (img_w - w) // 2
        # shadow/stroke
        draw.text((x - 1, y - 1), line, font=font, fill=stroke_fill)
        draw.text((x + 1, y + 1), line, font=font, fill=stroke_fill)
        draw.text((x, y), line, font=font, fill=fill)
        y += line_height
    return img

def ken_burns_clip(clip, target_h, zoom=1.06):
    # Resize to cover target_h then animate a gentle zoom
    clip = clip.resize(height=target_h)
    if clip.w < cfg["width"]:
        clip = clip.resize(width=cfg["width"])
    # crop center
    clip = clip.crop(x_center=clip.w/2, y_center=clip.h/2, width=cfg["width"], height=cfg["height"])
    # zoom effect: use resize with a lambda
    return clip.fx(lambda c: c.resize(lambda t: 1 + (zoom - 1) * (t / c.duration)))

def make_progress_bar(cfg, duration):
    W, H = cfg["width"], cfg["height"]
    bar_h = 18
    bg_color = hex_to_rgb(cfg["progress_bg"])
    fg_color = hex_to_rgb(cfg["progress_fg"])

    # Background strip
    bg = ColorClip(size=(W, bar_h), color=bg_color).set_duration(duration).set_position(("center", H - bar_h - 40))

    # make a dynamic fg clip using VideoClip.make_frame
    from moviepy.video.VideoClip import VideoClip

    def make_frame(t):
        arr = np.zeros((bar_h, W, 3), dtype=np.uint8)
        filled = int((t / duration) * W)
        if filled > 0:
            arr[:, :filled, 0] = fg_color[0]
            arr[:, :filled, 1] = fg_color[1]
            arr[:, :filled, 2] = fg_color[2]
        return arr

    fg = VideoClip(make_frame=make_frame, duration=duration).set_position(("left", H - bar_h - 40))
    return CompositeVideoClip([bg, fg], size=(cfg["width"], cfg["height"])).set_duration(duration)

def build_video():
    global cfg
    cfg = load_config()
    OUTPUT_DIR.mkdir(exist_ok=True)
    data = get_today_content()

    W, H = cfg["width"], cfg["height"]
    fps = cfg["fps"]
    duration = cfg["duration_seconds"]

    # background
    bg_mp4 = ASSETS_DIR / "background.mp4"
    bg_jpg = ASSETS_DIR / "background.jpg"
    if bg_mp4.exists():
        bg = VideoFileClip(str(bg_mp4)).without_audio()
        if bg.duration < duration:
            bg = bg.loop().subclip(0, duration)
        else:
            bg = bg.subclip(0, duration)
    elif bg_jpg.exists():
        bg = ImageClip(str(bg_jpg)).set_duration(duration)
    else:
        bg = ColorClip(size=(W, H), color=(10, 10, 10)).set_duration(duration)

    # fit & ken burns: simple resize/crop + slight zoom
    bg = bg.resize(height=H)
    if bg.w < W:
        bg = bg.resize(width=W)
    # center crop
    if hasattr(bg, "crop"):
        bg = bg.crop(x_center=bg.w / 2, y_center=bg.h / 2, width=W, height=H)
    # gentle zoom (if moviepy supports)
    # fallback: no explicit fx if not supported
    try:
        bg = bg.fx(lambda c: c.resize(lambda t: 1 + 0.03 * (t / duration)))
    except Exception:
        pass

    # Create text images and transform to ImageClips
    fonts_dir = ASSETS_DIR / "fonts"
    bold_font = fonts_dir / cfg["font_bold"].split("/")[-1]
    reg_font = fonts_dir / cfg["font_regular"].split("/")[-1]
    # fallbacks to system default if the files don't exist
    if not bold_font.exists():
        bold_font = cfg["font_bold"]
    if not reg_font.exists():
        reg_font = cfg["font_regular"]

    title_img = make_text_image(
        data["title"],
        font_path=bold_font,
        font_size=cfg["title"]["fontsize"],
        max_width=int(W * 0.9),
        fill=cfg["text_color"],
        stroke_fill=cfg["shadow_color"],
    )
    subtitle_img = make_text_image(
        data.get("subtitle", ""),
        font_path=reg_font,
        font_size=cfg["subtitle"]["fontsize"],
        max_width=int(W * 0.9),
        fill=cfg["text_color"],
        stroke_fill=cfg["shadow_color"],
    )

    title_clip = ImageClip(np.array(title_img)).set_duration(duration)
    subtitle_clip = ImageClip(np.array(subtitle_img)).set_duration(duration)

    # Positions (relative)
    title_pos = (int((W - title_img.width) * cfg["title"]["x"]), int(H * cfg["title"]["y"]))
    subtitle_pos = (int((W - subtitle_img.width) * cfg["subtitle"]["x"]), int(H * cfg["subtitle"]["y"]))

    title_clip = title_clip.set_position(title_pos)
    subtitle_clip = subtitle_clip.set_position(subtitle_pos)

    # progress bar
    progress = make_progress_bar(cfg, duration)

    # compose
    composite = CompositeVideoClip([bg, title_clip, subtitle_clip, progress], size=(W, H)).set_duration(duration)

    # Audio: TTS + background music (if any)
    audio_clips = []
    tts_tmp = None
    if cfg.get("use_tts", True):
        tts_text = data.get("body") or f"{data['title']}. {data.get('subtitle','')}"
        try:
            tts = gTTS(text=tts_text, lang=cfg.get("voice_lang", "en"))
            tf = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
            tts.save(tf.name)
            tts_tmp = tf.name
            tts_audio = AudioFileClip(tts_tmp)
            audio_clips.append(tts_audio)
        except Exception as e:
            print("TTS failed:", e)

    music_path = ASSETS_DIR / "music.mp3"
    if music_path.exists():
        try:
            music = AudioFileClip(str(music_path)).volumex(cfg.get("music_volume", 0.12))
            if music.duration < duration:
                # loop music
                loops = int(duration // music.duration) + 1
                full = music
                for _ in range(loops - 1):
                    full = full.append(music, crossfade=0)
                music = full.subclip(0, duration)
            else:
                music = music.subclip(0, duration)
            audio_clips.append(music)
        except Exception as e:
            print("Music load failed:", e)

    if audio_clips:
        composite = composite.set_audio(CompositeAudioClip(audio_clips))

    # export
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    out_path = OUTPUT_DIR / f"daily_{date_str}.mp4"
    composite.write_videofile(str(out_path), fps=fps, codec="libx264", audio_codec="aac", preset="medium", threads=4)

    # cleanup
    if tts_tmp and os.path.exists(tts_tmp):
        try:
            os.remove(tts_tmp)
        except Exception:
            pass

    return str(out_path)

def maybe_email(filepath):
    user = os.getenv("GMAIL_USER")
    pwd = os.getenv("GMAIL_APP_PASS")
    to = os.getenv("EMAIL_TO") or user
    subject_prefix = load_config().get("email_subject_prefix", "Daily Anime Video")
    subject = f"{subject_prefix} — {Path(filepath).name}"
    if not user or not pwd:
        print("[warn] GMAIL_USER / GMAIL_APP_PASS not set — skipping email")
        return
    print(f"Emailing {filepath} to {to} ...")
    send_email_with_attachment(user, pwd, to, subject, filepath)

if __name__ == "__main__":
    path = build_video()
    maybe_email(path)
    print("Done:", path)
