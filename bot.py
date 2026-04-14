#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
import time
import json
import subprocess
import logging
import pickle
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# Google API
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# Yuklab olish
import yt_dlp

# ============================================================
# KONFIGURATSIYA
# ============================================================

# Telegram Bot Token (BotFather dan oling)
BOT_TOKEN = "8227185560:AAFNIHiiSE1bnJXKA5vrysmYlaMB52DRapw"

# YouTube OAuth fayli (Google Cloud Console dan yuklab olingan)
CLIENT_SECRETS_FILE = "client_secrets.json"

# Papkalar
DOWNLOAD_FOLDER = "downloads"
TEMP_FOLDER = "temp"

for folder in [DOWNLOAD_FOLDER, TEMP_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Yuklash limiti (kuniga)
DAILY_UPLOAD_LIMIT = 10
upload_counter = 0
last_reset_date = datetime.now().date()

# ============================================================
# YOUTUBE AUTHENTICATION
# ============================================================
def find_client_secrets_file():
    """client_secrets.json faylini topish"""
    if os.path.exists('client_secrets.json'):
        return 'client_secrets.json'
    import glob
    json_files = glob.glob('client_secret*.json')
    if json_files:
        return json_files[0]
    return None

def get_youtube_credentials():
    """YouTube API uchun autentifikatsiya"""
    credentials = None
    token_file = 'youtube_token.pickle'
    scopes = ['https://www.googleapis.com/auth/youtube.upload']
    
    # Eski tokenni yuklash
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            credentials = pickle.load(token)
        logger.info("YouTube token yuklandi")
    
    # Token eskirgan yoki mavjud emas
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
            logger.info("YouTube token yangilandi")
        else:
            secrets_file = find_client_secrets_file()
            if not secrets_file:
                raise Exception("client_secrets.json topilmadi! Google Cloud Console dan yuklab oling.")
            
            flow = InstalledAppFlow.from_client_secrets_file(secrets_file, scopes=scopes)
            credentials = flow.run_local_server(port=0)
            logger.info("Yangi YouTube token olindi")
        
        # Tokenni saqlash
        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)
        logger.info("YouTube token saqlandi")
    
    return credentials

def get_youtube_service():
    """YouTube API servisini olish"""
    credentials = get_youtube_credentials()
    return build('youtube', 'v3', credentials=credentials)

# ============================================================
# VIDEO FUNKSIYALARI
# ============================================================
def get_video_duration(video_path: str) -> float:
    """Video davomiyligini sekundlarda olish"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                return float(stream.get('duration', 0))
        return 0
    except Exception as e:
        logger.error(f"Duration olish xatosi: {e}")
        return 0

def download_instagram_video(url: str):
    """Instagram videoni yuklab olish"""
    try:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'video')
            video_id = info.get('id', 'unknown')
            video_filename = f"{DOWNLOAD_FOLDER}/{video_title}_{video_id}.mp4"
            
            if not os.path.exists(video_filename):
                for file in os.listdir(DOWNLOAD_FOLDER):
                    if file.endswith('.mp4') and video_id in file:
                        video_filename = os.path.join(DOWNLOAD_FOLDER, file)
                        break
            
            return video_filename, video_title, video_id
    except Exception as e:
        logger.error(f"Instagram yuklash xatosi: {e}")
        raise Exception(f"Instagram videoni yuklab bo'lmadi: {str(e)}")

def download_youtube_video(url: str):
    """YouTube videoni yuklab olish"""
    try:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'outtmpl': f'{DOWNLOAD_FOLDER}/%(title)s_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = info.get('title', 'video')
            video_id = info.get('id', 'unknown')
            video_filename = f"{DOWNLOAD_FOLDER}/{video_title}_{video_id}.mp4"
            
            if not os.path.exists(video_filename):
                for file in os.listdir(DOWNLOAD_FOLDER):
                    if file.endswith('.mp4') and video_id in file:
                        video_filename = os.path.join(DOWNLOAD_FOLDER, file)
                        break
            
            return video_filename, video_title, video_id
    except Exception as e:
        logger.error(f"YouTube yuklash xatosi: {e}")
        raise Exception(f"YouTube videoni yuklab bo'lmadi: {str(e)}")

async def download_telegram_video(file_id: str, output_path: str):
    """Telegram'dan video faylni yuklab olish"""
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, output_path)
    logger.info(f"Telegram fayli yuklab olindi: {output_path}")
    return output_path

def upload_to_youtube(video_path: str, title: str, privacy: str = "public"):
    """Videoni YouTube'ga yuklash"""
    youtube = get_youtube_service()
    
    # Video davomiyligini olish
    duration = get_video_duration(video_path)
    is_short = duration <= 60
    
    # Sarlavha tayyorlash
    clean_title = title[:95].replace('/', '_').replace('\\', '_')
    
    if is_short:
        final_title = f"{clean_title} #shorts"
        tags = ['shorts', 'viral', 'trending', 'instagram']
        category_id = '24'  # Entertainment
        description = f"📱 {clean_title}\n\n🎬 Instagram'dan yuklandi\n⏱️ Davomiyligi: {int(duration)} sekund\n\n#shorts #instagram #reels #viral"
    else:
        final_title = clean_title
        tags = ['video', 'trending', 'instagram']
        category_id = '22'  # People & Blogs
        description = f"📱 {clean_title}\n\n📥 Instagram'dan yuklandi\n⏱️ Davomiyligi: {int(duration // 60)} minut {int(duration % 60)} sekund\n\n#instagram #reels #video"
    
    body = {
        'snippet': {
            'title': final_title,
            'description': description[:5000],
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': privacy
        }
    }
    
    media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True, mimetype='video/mp4')
    
    try:
        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )
        response = request.execute()
        video_url = f"https://youtu.be/{response['id']}"
        logger.info(f"Video YouTube'ga yuklandi: {video_url}")
        return video_url, is_short, duration
        
    except HttpError as e:
        error_content = str(e)
        if "uploadLimitExceeded" in error_content:
            raise Exception("YouTube kunlik yuklash limitiga yetdingiz! (Kuniga ~6 ta video)")
        elif "quotaExceeded" in error_content:
            raise Exception("YouTube API limiti tugadi! Ertaga qayta uruning.")
        else:
            raise Exception(f"YouTube xatosi: {error_content[:200]}")

def check_daily_limit():
    """Kunlik yuklash limitini tekshirish"""
    global upload_counter, last_reset_date
    
    today = datetime.now().date()
    if today != last_reset_date:
        upload_counter = 0
        last_reset_date = today
        logger.info("Kunlik limit qayta tiklandi")
    
    return upload_counter < DAILY_UPLOAD_LIMIT

def increment_upload_counter():
    global upload_counter
    upload_counter += 1
    logger.info(f"Bugungi yuklash: {upload_counter}/{DAILY_UPLOAD_LIMIT}")

# ============================================================
# TELEGRAM BOT HANDLERLAR
# ============================================================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    remaining = DAILY_UPLOAD_LIMIT - upload_counter
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Video Yuklash (Fayl)", callback_data="upload_video")],
        [InlineKeyboardButton(text="🔗 Linkdan Yuklash", callback_data="upload_link")],
        [InlineKeyboardButton(text="📊 Holat", callback_data="status")],
    ])
    
    await message.answer(
        f"🎬 **Video Upload Bot**\n\n"
        f"📹 Instagram videolarini YouTube'ga yuklash uchun bot!\n\n"
        f"**Qanday ishlatish:**\n"
        f"• Video faylni yuboring\n"
        f"• Instagram linkini yuboring\n\n"
        f"**Xususiyatlar:**\n"
        f"• ⏱️ 1 minutgacha video → YouTube Shorts\n"
        f"• 🔊 Audio to'liq saqlanadi\n"
        f"• 🌍 Videolar PUBLIC qilib yuklanadi\n\n"
        f"📊 Kunlik qolgan yuklash: **{remaining}** ta",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "🆘 **Yordam**\n\n"
        "**Qo'llab-quvvatlanadigan manbalar:**\n"
        "• Instagram Reels/Posts\n"
        "• Telegram video fayllar (MP4, AVI, MOV)\n\n"
        "**Buyruqlar:**\n"
        "/start - Boshlash\n"
        "/help - Yordam\n\n"
        "**Eslatma:** YouTube kunlik limiti ~6 ta video",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.callback_query(lambda c: c.data == "upload_video")
async def upload_video_prompt(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📹 **Video fayl yuboring**\n\n"
        "MP4, AVI, MOV, MKV formatlari qo'llab-quvvatlanadi.\n\n"
        "🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "upload_link")
async def upload_link_prompt(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🔗 **Instagram linkini yuboring**\n\n"
        "Masalan:\n"
        "• `https://www.instagram.com/reel/...`\n"
        "• `https://www.instagram.com/p/...`\n\n"
        "🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "status")
async def status_callback(callback: types.CallbackQuery):
    remaining = DAILY_UPLOAD_LIMIT - upload_counter
    
    # YouTube token mavjudligini tekshirish
    has_token = os.path.exists('youtube_token.pickle')
    has_secrets = find_client_secrets_file() is not None
    
    await callback.message.edit_text(
        f"📊 **Bot Holati**\n\n"
        f"✅ Bot ishlayapti\n"
        f"📤 Bugungi yuklash: {upload_counter}/{DAILY_UPLOAD_LIMIT}\n"
        f"⏳ Qolgan: {remaining} ta\n"
        f"🔑 YouTube token: {'✅ bor' if has_token else '❌ yo‘q'}\n"
        f"📄 client_secrets.json: {'✅ bor' if has_secrets else '❌ yo‘q'}\n\n"
        f"🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    remaining = DAILY_UPLOAD_LIMIT - upload_counter
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Video Yuklash (Fayl)", callback_data="upload_video")],
        [InlineKeyboardButton(text="🔗 Linkdan Yuklash", callback_data="upload_link")],
        [InlineKeyboardButton(text="📊 Holat", callback_data="status")],
    ])
    await callback.message.edit_text(
        f"🎬 **Video Upload Bot**\n\n"
        f"📊 Kunlik qolgan yuklash: {remaining} ta",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()

# ============================================================
# VIDEO QABUL QILISH
# ============================================================
@dp.message(lambda message: message.video is not None)
async def handle_video_file(message: types.Message):
    # Kunlik limitni tekshirish
    if not check_daily_limit():
        await message.answer(
            f"❌ **Kunlik limit tugadi!**\n\n"
            f"Bugun {DAILY_UPLOAD_LIMIT} ta video yukladingiz.\n"
            f"Ertaga qayta uruning.\n\n"
            f"📅 Limit qayta tiklanadi: yarim tunda",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    status_msg = await message.answer("🔄 Yuklab olinmoqda...")
    
    try:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        
        temp_path = os.path.join(TEMP_FOLDER, f"{int(time.time())}_{file_name}")
        await download_telegram_video(file_id, temp_path)
        
        await status_msg.edit_text("📤 YouTube'ga yuklanmoqda... (1-2 daqiqa)")
        
        video_url, is_short, duration = upload_to_youtube(temp_path, file_name, "public")
        increment_upload_counter()
        
        remaining = DAILY_UPLOAD_LIMIT - upload_counter
        
        await status_msg.edit_text(
            f"✅ **Video muvaffaqiyatli yuklandi!**\n\n"
            f"📹 Nomi: {file_name[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📌 Format: {'🎬 YouTube Shorts' if is_short else '📹 Oddiy video'}\n"
            f"🔗 Link: {video_url}\n\n"
            f"📊 Bugun yana **{remaining}** ta video yuklashingiz mumkin",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        # Faylni o'chirish
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    except HttpError as e:
        if "quotaExceeded" in str(e):
            await status_msg.edit_text(
                f"⚠️ **YouTube API limiti tugadi!**\n\n"
                f"Bugun {upload_counter} ta video yuklandi.\n"
                f"Ertaga qayta uruning.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await status_msg.edit_text(f"❌ YouTube xatosi: {str(e)[:200]}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

@dp.message(lambda message: "instagram.com" in message.text.lower())
async def handle_instagram_link(message: types.Message):
    # Kunlik limitni tekshirish
    if not check_daily_limit():
        await message.answer(
            f"❌ **Kunlik limit tugadi!**\n\n"
            f"Bugun {DAILY_UPLOAD_LIMIT} ta video yukladingiz.\n"
            f"Ertaga qayta uruning.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    url = message.text.strip()
    status_msg = await message.answer("🔄 Instagram'dan yuklab olinmoqda... (bu 1-2 daqiqa vaqt olishi mumkin)")
    
    try:
        video_path, video_title, video_id = download_instagram_video(url)
        
        await status_msg.edit_text("📤 YouTube'ga yuklanmoqda... (1-2 daqiqa)")
        
        video_url, is_short, duration = upload_to_youtube(video_path, video_title, "public")
        increment_upload_counter()
        
        remaining = DAILY_UPLOAD_LIMIT - upload_counter
        
        await status_msg.edit_text(
            f"✅ **Video muvaffaqiyatli yuklandi!**\n\n"
            f"📹 Nomi: {video_title[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📌 Format: {'🎬 YouTube Shorts' if is_short else '📹 Oddiy video'}\n"
            f"🔗 Link: {video_url}\n\n"
            f"📊 Bugun yana **{remaining}** ta video yuklashingiz mumkin",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        # Faylni o'chirish
        if os.path.exists(video_path):
            os.remove(video_path)
            
    except HttpError as e:
        if "quotaExceeded" in str(e):
            await status_msg.edit_text(
                f"⚠️ **YouTube API limiti tugadi!**\n\n"
                f"Bugun {upload_counter} ta video yuklandi.\n"
                f"Ertaga qayta uruning.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await status_msg.edit_text(f"❌ YouTube xatosi: {str(e)[:200]}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

@dp.message(lambda message: "youtu.be" in message.text or "youtube.com" in message.text)
async def handle_youtube_link(message: types.Message):
    # Kunlik limitni tekshirish
    if not check_daily_limit():
        await message.answer(
            f"❌ **Kunlik limit tugadi!**\n\n"
            f"Bugun {DAILY_UPLOAD_LIMIT} ta video yukladingiz.\n"
            f"Ertaga qayta uruning.",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    url = message.text.strip()
    status_msg = await message.answer("🔄 YouTube'dan yuklab olinmoqda...")
    
    try:
        video_path, video_title, video_id = download_youtube_video(url)
        
        await status_msg.edit_text("📤 YouTube'ga yuklanmoqda... (1-2 daqiqa)")
        
        video_url, is_short, duration = upload_to_youtube(video_path, video_title, "public")
        increment_upload_counter()
        
        remaining = DAILY_UPLOAD_LIMIT - upload_counter
        
        await status_msg.edit_text(
            f"✅ **Video muvaffaqiyatli yuklandi!**\n\n"
            f"📹 Nomi: {video_title[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📌 Format: {'🎬 YouTube Shorts' if is_short else '📹 Oddiy video'}\n"
            f"🔗 Link: {video_url}\n\n"
            f"📊 Bugun yana **{remaining}** ta video yuklashingiz mumkin",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        if os.path.exists(video_path):
            os.remove(video_path)
            
    except HttpError as e:
        if "quotaExceeded" in str(e):
            await status_msg.edit_text(
                f"⚠️ **YouTube API limiti tugadi!**\n\n"
                f"Bugun {upload_counter} ta video yuklandi.\n"
                f"Ertaga qayta uruning.",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await status_msg.edit_text(f"❌ YouTube xatosi: {str(e)[:200]}")
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

# ============================================================
# BOTNI ISHGA TUSHIRISH
# ============================================================
async def on_startup():
    """Bot ishga tushganda webhook'ni o'chirish"""
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook o'chirildi!")

async def main():
    print("=" * 50)
    print("🤖 YOUTUBE UPLOAD BOT")
    print("=" * 50)
    print(f"✅ Bot ishga tushdi!")
    print(f"📊 Kunlik limit: {DAILY_UPLOAD_LIMIT} ta video")
    
    # YouTube OAuth faylini tekshirish
    secrets_file = find_client_secrets_file()
    if secrets_file:
        print(f"✅ YouTube OAuth: {secrets_file} topildi")
    else:
        print(f"⚠️ YouTube OAuth: client_secrets.json topilmadi!")
        print(f"   YouTube'ga yuklash uchun Google Cloud Console dan faylni yuklab oling")
    
    print("=" * 50)
    
    # Webhook'ni o'chirish
    await on_startup()
    
    # Botni ishga tushirish
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Bot to'xtatildi")
    except Exception as e:
        print(f"❌ Xatolik: {e}")
