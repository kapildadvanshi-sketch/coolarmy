import os
import time
import shutil
import subprocess
import tempfile

from PIL import Image, ImageEnhance

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
)

from dotenv import load_dotenv
import yt_dlp


# =========================
# LOAD BOT TOKEN
# =========================

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN nahi mila. .env file mein BOT_TOKEN=YOUR_TOKEN add karo."
    )


# =========================
# START COMMAND
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "👋 Welcome to Media Processing Bot!\n\n"
        "📸 Photo:\n"
        "Send a photo and I will process it.\n\n"
        "🎥 Video:\n"
        "Send a publicly accessible Instagram/TikTok video link.\n\n"
        "⚠️ Some links may not work if the platform requires "
        "login or blocks automated access.\n\n"
        "💬 Send /help for instructions."
    )

    await update.message.reply_text(text)


# =========================
# HELP COMMAND
# =========================

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    text = (
        "📖 How to use:\n\n"
        "1️⃣ Send a photo directly.\n"
        "2️⃣ Send a public Instagram/TikTok video URL.\n\n"
        "The bot will download/process the media and send it back."
    )

    await update.message.reply_text(text)


# =========================
# IMAGE PROCESSING
# =========================

def modify_image(input_path, output_path):

    img = Image.open(input_path).convert("RGB")

    width, height = img.size

    # Small crop
    if width > 20 and height > 20:
        crop_box = (
            int(width * 0.02),
            int(height * 0.02),
            int(width * 0.98),
            int(height * 0.98),
        )

        img = img.crop(crop_box)

    # Slight visual adjustment
    img = ImageEnhance.Color(img).enhance(1.10)
    img = ImageEnhance.Brightness(img).enhance(1.04)
    img = ImageEnhance.Contrast(img).enhance(1.03)

    img.save(
        output_path,
        "JPEG",
        quality=95,
        optimize=True
    )


# =========================
# VIDEO PROCESSING
# =========================

def process_video(input_path, output_path):

    vf_filters = (
        "scale=iw-4:ih-4,"
        "crop=iw-4:ih-4,"
        "eq=brightness=0.02:"
        "contrast=1.03:"
        "saturation=1.05:"
        "gamma=0.99"
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        input_path,

        "-vf",
        vf_filters,

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "21",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-movflags",
        "+faststart",

        output_path,
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            "FFmpeg error:\n"
            + result.stderr[-1500:]
        )


# =========================
# DOWNLOAD VIDEO
# =========================

def download_video(url, download_directory):

    output_template = os.path.join(
        download_directory,
        "input.%(ext)s"
    )

    ydl_opts = {

        "outtmpl": output_template,

        # Don't treat a single video as playlist
        "noplaylist": True,

        # Prefer normal MP4-compatible video/audio
        "format": (
            "bestvideo*[ext=mp4]+bestaudio[ext=m4a]/"
            "best[ext=mp4]/best"
        ),

        "merge_output_format": "mp4",

        "socket_timeout": 60,

        "retries": 3,

        "fragment_retries": 3,

        "extractor_retries": 3,

        "quiet": True,

        "no_warnings": True,

        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:

        info = ydl.extract_info(
            url,
            download=True
        )

        downloaded_file = ydl.prepare_filename(info)

        # If yt-dlp merged into mp4
        possible_mp4 = os.path.splitext(
            downloaded_file
        )[0] + ".mp4"

        if os.path.exists(possible_mp4):
            return possible_mp4

        if os.path.exists(downloaded_file):
            return downloaded_file

        # Find whatever file was actually created
        files = os.listdir(download_directory)

        media_files = [
            f for f in files
            if f.lower().endswith(
                (".mp4", ".mkv", ".webm", ".mov", ".m4v")
            )
        ]

        if media_files:
            return os.path.join(
                download_directory,
                media_files[0]
            )

        raise FileNotFoundError(
            "Video download hua, lekin output file nahi mili."
        )


# =========================
# HANDLE TEXT / LINKS
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text

    if not text:
        return

    text = text.strip()

    # =========================
    # URL CHECK
    # =========================

    if not text.startswith(
        ("http://", "https://")
    ):

        await update.message.reply_text(
            "🤖 Invalid input.\n\n"
            "Please send a public Instagram/TikTok "
            "video link or send a photo."
        )

        return

    # =========================
    # URL CHECK
    # =========================

    allowed_domains = (
        "instagram.com",
        "www.instagram.com",
        "tiktok.com",
        "www.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    )

    if not any(
        domain in text.lower()
        for domain in allowed_domains
    ):

        await update.message.reply_text(
            "❌ Please send an Instagram or TikTok URL."
        )

        return

    status_message = await update.message.reply_text(
        "🔄 Link detected...\n"
        "⏳ Downloading video..."
    )

    work_directory = tempfile.mkdtemp(
        prefix="media_bot_"
    )

    try:

        # =========================
        # DOWNLOAD
        # =========================

        input_video = download_video(
            text,
            work_directory
        )

        if not os.path.exists(input_video):

            raise FileNotFoundError(
                "Downloaded video file nahi mili."
            )

        await status_message.edit_text(
            "✅ Video downloaded!\n"
            "⚙️ Processing video..."
        )

        # =========================
        # PROCESS
        # =========================

        output_video = os.path.join(
            work_directory,
            "processed.mp4"
        )

        process_video(
            input_video,
            output_video
        )

        if not os.path.exists(output_video):

            raise FileNotFoundError(
                "Processed video create nahi hui."
            )

        # =========================
        # FILE SIZE CHECK
        # =========================

        file_size = os.path.getsize(
            output_video
        )

        if file_size == 0:

            raise RuntimeError(
                "Processed video empty hai."
            )

        await status_message.edit_text(
            "📤 Uploading video to Telegram..."
        )

        # =========================
        # SEND VIDEO
        # =========================

        with open(
            output_video,
            "rb"
        ) as video_file:

            await update.message.reply_video(
                video=video_file,
                caption="✅ Video processed successfully!",
                supports_streaming=True
            )

        await status_message.delete()

    except Exception as e:

        error_message = str(e)

        print(
            "\n========== ERROR ==========\n"
            + error_message +
            "\n===========================\n"
        )

        # Keep Telegram error readable
        if len(error_message) > 1200:
            error_message = error_message[-1200:]

        await status_message.edit_text(
            "❌ Video process nahi ho paya.\n\n"
            f"Error:\n{error_message}\n\n"
            "💡 Agar Instagram/TikTok link login "
            "ya restricted access maangta hai, "
            "yt-dlp us link ko download nahi kar sakta."
        )

    finally:

        # =========================
        # CLEAN TEMP FILES
        # =========================

        try:
            shutil.rmtree(
                work_directory,
                ignore_errors=True
            )
        except Exception:
            pass


# =========================
# HANDLE PHOTO
# =========================

async def handle_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    work_directory = tempfile.mkdtemp(
        prefix="photo_bot_"
    )

    input_path = os.path.join(
        work_directory,
        "input.jpg"
    )

    output_path = os.path.join(
        work_directory,
        "output.jpg"
    )

    try:

        photo = update.message.photo[-1]

        telegram_file = await photo.get_file()

        await telegram_file.download_to_drive(
            input_path
        )

        modify_image(
            input_path,
            output_path
        )

        with open(
            output_path,
            "rb"
        ) as image_file:

            await update.message.reply_photo(
                photo=image_file,
                caption="✅ Image processed successfully!"
            )

    except Exception as e:

        print(
            "Photo error:",
            e
        )

        await update.message.reply_text(
            f"❌ Photo process failed:\n{e}"
        )

    finally:

        shutil.rmtree(
            work_directory,
            ignore_errors=True
        )


# =========================
# MAIN
# =========================

def main():

    print("Starting bot...")

    application = (
        ApplicationBuilder()
        .token(TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    application.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    # Photos
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_photo
        )
    )

    # Text / URLs
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("Bot is running...")

    application.run_polling()


# =========================
# RUN
# =========================

if __name__ == "__main__":
    main()
