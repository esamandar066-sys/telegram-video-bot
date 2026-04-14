#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import asyncio
import re
import time
import json
import subprocess
import logging
import pickle
from datetime import datetime

# Aiogram 3.x importlar
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

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

# YouTube OAuth sozlamalari
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

# ============================================================
# YOUTUBE AUTHENTICATION
# ============================================================
def find_client_secrets_file():
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
    
    if os.path.exists(token_file):
        with open(token_file, 'rb') as token:
            credentials = pickle.load(token)
    
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleRequest())
        else:
            secrets_file = find_client_secrets_file()
            if not secrets_file:
                raise Exception("client_secrets.json topilmadi! Google Cloud Console dan yuklab oling.")
            
            flow = InstalledAppFlow.from_client_secrets_file(secrets_file, scopes=scopes)
            credentials = flow.run_local_server(port=0)
        
        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)
        print("✅ YouTube token saqlandi")
    
    return credentials

def get_youtube_service():
    credentials = get_youtube_credentials()
    return build('youtube', 'v3', credentials=credentials)

# ============================================================
# VIDEO FUNKSIYALARI
# ============================================================
def get_video_duration(video_path: str) -> float:
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                return float(stream.get('duration', 0))
        return 0
    except:
        return 0

def download_video(url: str):
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
        raise Exception(f"Videoni yuklab bo'lmadi: {str(e)}")

async def download_telegram_video(file_id: str, output_path: str):
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, output_path)
    return output_path

def upload_to_youtube(video_path: str, title: str, privacy: str = "public"):
    youtube = get_youtube_service()
    
    duration = get_video_duration(video_path)
    is_short = duration <= 60
    
    clean_title = title[:95].replace('/', '_').replace('\\', '_')
    
    if is_short:
        final_title = f"{clean_title} #shorts"
        tags = ['shorts', 'viral', 'trending']
        category_id = '24'
    else:
        final_title = clean_title
        tags = ['video', 'trending']
        category_id = '22'
    
    body = {
        'snippet': {
            'title': final_title,
            'description': f"📹 {clean_title}\n\n#youtube #video",
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
        return video_url, is_short, duration
        
    except HttpError as e:
        error_content = str(e)
        if "uploadLimitExceeded" in error_content:
            raise Exception("YouTube kunlik yuklash limitiga yetdingiz! (Kuniga ~6 ta video)")
        elif "quotaExceeded" in error_content:
            raise Exception("YouTube API limiti tugadi! Ertaga qayta uruning.")
        else:
            raise Exception(f"YouTube xatosi: {error_content[:200]}")

# ============================================================
# TELEGRAM BOT HANDLERLAR
# ============================================================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Video Yuklash", callback_data="upload_video")],
        [InlineKeyboardButton(text="🔗 Linkdan Yuklash", callback_data="upload_link")],
    ])
    
    await message.answer(
        "🎬 **Video Upload Bot**\n\n"
        "📹 **Video yuklash:**\n"
        "• Video faylni yuboring\n"
        "• Instagram linkini yuboring\n"
        "• YouTube linkini yuboring\n\n"
        "⚡️ Video 1 minutgacha bo'lsa -> **YouTube Shorts**\n"
        "📌 Barcha videolar PUBLIC qilib yuklanadi",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "🆘 **Yordam**\n\n"
        "**Qo'llab-quvvatlanadigan manbalar:**\n"
        "• Instagram Reels/Posts\n"
        "• YouTube videolar\n"
        "• Telegram video fayllar\n\n"
        "**Buyruqlar:**\n"
        "/start - Boshlash\n"
        "/help - Yordam",
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
        "🔗 **Link yuboring**\n\n"
        "Qo'llab-quvvatlanadigan linklar:\n"
        "• Instagram: `instagram.com/reel/...`\n"
        "• YouTube: `youtu.be/...`\n\n"
        "🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Video Yuklash", callback_data="upload_video")],
        [InlineKeyboardButton(text="🔗 Linkdan Yuklash", callback_data="upload_link")],
    ])
    await callback.message.edit_text(
        "🎬 **Video Upload Bot**\n\nAsosiy menyu",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()

# ============================================================
# VIDEO QABUL QILISH
# ============================================================
@dp.message(lambda message: message.video is not None)
async def handle_video_file(message: types.Message):
    status_msg = await message.answer("🔄 Yuklab olinmoqda...")
    
    try:
        file_id = message.video.file_id
        file_name = message.video.file_name or "video.mp4"
        
        temp_path = os.path.join(TEMP_FOLDER, f"{int(time.time())}_{file_name}")
        await download_telegram_video(file_id, temp_path)
        
        await status_msg.edit_text("📤 YouTube'ga yuklanmoqda... (1-2 daqiqa)")
        
        video_url, is_short, duration = upload_to_youtube(temp_path, file_name, "public")
        
        await status_msg.edit_text(
            f"✅ **Video muvaffaqiyatli yuklandi!**\n\n"
            f"📹 Nomi: {file_name[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📌 Format: {'YouTube Shorts' if is_short else 'Oddiy video'}\n"
            f"🔗 Link: {video_url}",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)}")

@dp.message(lambda message: "instagram.com" in message.text or "youtu.be" in message.text)
async def handle_link(message: types.Message):
    url = message.text.strip()
    status_msg = await message.answer("🔄 Linkdan yuklab olinmoqda...")
    
    try:
        video_path, video_title, _ = download_video(url)
        
        await status_msg.edit_text("📤 YouTube'ga yuklanmoqda... (1-2 daqiqa)")
        
        video_url, is_short, duration = upload_to_youtube(video_path, video_title, "public")
        
        await status_msg.edit_text(
            f"✅ **Video muvaffaqiyatli yuklandi!**\n\n"
            f"📹 Nomi: {video_title[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📌 Format: {'YouTube Shorts' if is_short else 'Oddiy video'}\n"
            f"🔗 Link: {video_url}",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True
        )
        
        if os.path.exists(video_path):
            os.remove(video_path)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)}")

# ============================================================
# BOTNI ISHGA TUSHIRISH
# ============================================================
async def main():
    print("=" * 50)
    print("🤖 YOUTUBE UPLOAD BOT")
    print("=" * 50)
    print(f"✅ Bot ishga tushdi!")
    print(f"📁 Yuklash papkasi: {DOWNLOAD_FOLDER}")
    
    secrets_file = find_client_secrets_file()
    if secrets_file:
        print(f"✅ YouTube OAuth: {secrets_file} topildi")
    else:
        print(f"⚠️ YouTube OAuth: client_secrets.json topilmadi!")
    
    print("=" * 50)
    print("Botni Telegram'da oching va /start yuboring")
    print("=" * 50)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Bot to'xtatildi")
    except Exception as e:
        print(f"❌ Xatolik: {e}")
