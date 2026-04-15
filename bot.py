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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.storage.memory import MemoryStorage

# Google API (YouTube yuklash uchun)
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

# Telegram Bot Token
BOT_TOKEN = "8227185560:AAFNIHiiSE1bnJXKA5vrysmYlaMB52DRapw"

# YouTube OAuth fayli
CLIENT_SECRETS_FILE = "client_secrets.json"

# Papkalar
DOWNLOAD_FOLDER = "downloads"
OUTPUT_FOLDER = "output"

for folder in [DOWNLOAD_FOLDER, OUTPUT_FOLDER]:
    if not os.path.exists(folder):
        os.makedirs(folder)

# Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Bot
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Yuklash limiti
DAILY_UPLOAD_LIMIT = 10
upload_counter = 0
last_reset_date = datetime.now().date()

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
            credentials = flow.run_local_server(port=0, open_browser=False)
        
        with open(token_file, 'wb') as token:
            pickle.dump(credentials, token)
    
    return credentials

def get_youtube_service():
    credentials = get_youtube_credentials()
    return build('youtube', 'v3', credentials=credentials)

# ============================================================
# VIDEO YUKLAB OLISH (YUQORI FORMATDA)
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

def get_video_resolution(video_path: str) -> str:
    """Video rezolyutsiyasini olish"""
    try:
        cmd = ['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_streams', video_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'video':
                width = stream.get('width', 0)
                height = stream.get('height', 0)
                return f"{width}x{height}"
        return "Noma'lum"
    except:
        return "Noma'lum"

def get_video_size(file_path: str) -> str:
    """Fayl hajmini chiroyli ko'rsatish"""
    size = os.path.getsize(file_path)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"

def download_instagram_video(url: str):
    """Instagram videoni eng yuqori sifatda yuklab olish"""
    try:
        # Eng yuqori sifat uchun sozlamalar
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'outtmpl': f'{DOWNLOAD_FOLDER}/instagram_%(title)s_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'extract_flat': False,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = re.sub(r'[\\/*?:"<>|]', "", info.get('title', 'instagram_video'))
            video_id = info.get('id', 'unknown')
            
            # Yuklangan faylni topish
            for file in os.listdir(DOWNLOAD_FOLDER):
                if file.endswith('.mp4') and (video_id in file or video_title[:30] in file):
                    video_path = os.path.join(DOWNLOAD_FOLDER, file)
                    break
            else:
                video_path = f"{DOWNLOAD_FOLDER}/instagram_{video_title}_{video_id}.mp4"
            
            # Video ma'lumotlari
            duration = info.get('duration', 0)
            resolution = info.get('resolution', 'Noma\'lum')
            
            return video_path, video_title, video_id, duration, resolution
            
    except Exception as e:
        logger.error(f"Instagram yuklash xatosi: {e}")
        raise Exception(f"Instagram videoni yuklab bo'lmadi: {str(e)}")

def download_youtube_video(url: str, quality: str = "best"):
    """
    YouTube videoni yuqori sifatda yuklab olish
    quality: 'best', '1080p', '720p', '480p'
    """
    try:
        # Sifatga qarab format tanlash
        if quality == "1080p":
            format_spec = 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]'
        elif quality == "720p":
            format_spec = 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]'
        elif quality == "480p":
            format_spec = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]'
        else:
            format_spec = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        
        ydl_opts = {
            'format': format_spec,
            'merge_output_format': 'mp4',
            'outtmpl': f'{DOWNLOAD_FOLDER}/youtube_%(title)s_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = re.sub(r'[\\/*?:"<>|]', "", info.get('title', 'youtube_video'))
            video_id = info.get('id', 'unknown')
            duration = info.get('duration', 0)
            
            # Yuklangan faylni topish
            for file in os.listdir(DOWNLOAD_FOLDER):
                if file.endswith('.mp4') and (video_id in file or video_title[:30] in file):
                    video_path = os.path.join(DOWNLOAD_FOLDER, file)
                    break
            else:
                video_path = f"{DOWNLOAD_FOLDER}/youtube_{video_title}_{video_id}.mp4"
            
            # Rezolyutsiya olish
            resolution = info.get('resolution', 'Noma\'lum')
            if resolution == 'Noma\'lum':
                # Formatdan olish
                for f in info.get('formats', []):
                    if f.get('height'):
                        resolution = f"{f.get('width', 0)}x{f.get('height', 0)}"
                        break
            
            return video_path, video_title, video_id, duration, resolution
            
    except Exception as e:
        logger.error(f"YouTube yuklash xatosi: {e}")
        raise Exception(f"YouTube videoni yuklab bo'lmadi: {str(e)}")

def download_tiktok_video(url: str):
    """TikTok videoni yuqori sifatda yuklab olish"""
    try:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'outtmpl': f'{DOWNLOAD_FOLDER}/tiktok_%(title)s_%(id)s.%(ext)s',
            'quiet': True,
            'no_warnings': True,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_title = re.sub(r'[\\/*?:"<>|]', "", info.get('title', 'tiktok_video'))
            video_id = info.get('id', 'unknown')
            duration = info.get('duration', 0)
            
            for file in os.listdir(DOWNLOAD_FOLDER):
                if file.endswith('.mp4') and (video_id in file or video_title[:30] in file):
                    video_path = os.path.join(DOWNLOAD_FOLDER, file)
                    break
            else:
                video_path = f"{DOWNLOAD_FOLDER}/tiktok_{video_title}_{video_id}.mp4"
            
            return video_path, video_title, video_id, duration, "Noma'lum"
            
    except Exception as e:
        logger.error(f"TikTok yuklash xatosi: {e}")
        raise Exception(f"TikTok videoni yuklab bo'lmadi: {str(e)}")

async def download_telegram_video(file_id: str, output_path: str):
    """Telegram'dan video faylni yuklab olish"""
    file = await bot.get_file(file_id)
    await bot.download_file(file.file_path, output_path)
    return output_path

# ============================================================
# YOUTUBEGA YUKLASH
# ============================================================
def upload_to_youtube(video_path: str, title: str, duration: float, privacy: str = "public"):
    """Videoni YouTube'ga yuklash"""
    youtube = get_youtube_service()
    
    is_short = duration <= 60
    clean_title = title[:95].replace('/', '_').replace('\\', '_')
    
    if is_short:
        final_title = f"{clean_title} #shorts"
        tags = ['shorts', 'viral', 'trending']
        category_id = '24'
        description = f"📱 {clean_title}\n\n🎬 Yuklandi: Instagram/YouTube\n⏱️ Davomiyligi: {int(duration)} sekund\n\n#shorts #viral #trending"
    else:
        final_title = clean_title
        tags = ['video', 'trending']
        category_id = '22'
        description = f"📱 {clean_title}\n\n📥 Yuklandi: Instagram/YouTube\n⏱️ Davomiyligi: {int(duration // 60)} minut {int(duration % 60)} sekund\n\n#video #trending"
    
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
        return video_url, is_short
        
    except HttpError as e:
        if "uploadLimitExceeded" in str(e):
            raise Exception("YouTube kunlik yuklash limitiga yetdingiz! (Kuniga ~6 ta video)")
        elif "quotaExceeded" in str(e):
            raise Exception("YouTube API limiti tugadi! Ertaga qayta uruning.")
        else:
            raise Exception(f"YouTube xatosi: {str(e)[:200]}")

# ============================================================
# KUNLIK LIMIT
# ============================================================
def check_daily_limit():
    global upload_counter, last_reset_date
    
    today = datetime.now().date()
    if today != last_reset_date:
        upload_counter = 0
        last_reset_date = today
    
    return upload_counter < DAILY_UPLOAD_LIMIT

def increment_upload_counter():
    global upload_counter
    upload_counter += 1

# ============================================================
# TELEGRAM BOT HANDLERLAR
# ============================================================
@dp.message(Command("start"))
async def start_command(message: types.Message):
    remaining = DAILY_UPLOAD_LIMIT - upload_counter
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Instagram Video", callback_data="download_instagram")],
        [InlineKeyboardButton(text="▶️ YouTube Video", callback_data="download_youtube")],
        [InlineKeyboardButton(text="🎵 TikTok Video", callback_data="download_tiktok")],
        [InlineKeyboardButton(text="📊 Holat", callback_data="status")],
    ])
    
    await message.answer(
        f"🎬 **Yuqori sifatli video yuklab olish boti**\n\n"
        f"📹 **Qo'llab-quvvatlanadigan platformalar:**\n"
        f"• Instagram Reels/Posts (maksimal sifat)\n"
        f"• YouTube videolar (1080p, 720p, 480p)\n"
        f"• TikTok videolar\n"
        f"• Telegram video fayllar\n\n"
        f"**Xususiyatlar:**\n"
        f"• Eng yuqori sifatda yuklab olish\n"
        f"• Audio bilan birga saqlash\n"
        f"• YouTube'ga yuklash imkoniyati\n\n"
        f"📊 Kunlik qolgan: **{remaining}** ta\n\n"
        f"🔽 Platformani tanlang yoki to'g'ridan-to'g'ri link yuboring!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )

@dp.callback_query(lambda c: c.data == "download_instagram")
async def download_instagram_prompt(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "📸 **Instagram linkini yuboring**\n\n"
        "Masalan:\n"
        "• `https://www.instagram.com/reel/...`\n"
        "• `https://www.instagram.com/p/...`\n\n"
        "✅ Eng yuqori sifatda yuklab olinadi!\n\n"
        "🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "download_youtube")
async def download_youtube_prompt(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 Eng yuqori sifat", callback_data="youtube_best")],
        [InlineKeyboardButton(text="📺 1080p (Full HD)", callback_data="youtube_1080p")],
        [InlineKeyboardButton(text="📱 720p (HD)", callback_data="youtube_720p")],
        [InlineKeyboardButton(text="📱 480p", callback_data="youtube_480p")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(
        "▶️ **YouTube video sifatini tanlang**\n\n"
        "Qaysi sifatda yuklab olishni xohlaysiz?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("youtube_"))
async def youtube_quality_selected(callback: types.CallbackQuery):
    quality = callback.data.replace("youtube_", "")
    quality_names = {"best": "Eng yuqori", "1080p": "1080p Full HD", "720p": "720p HD", "480p": "480p"}
    
    # Sifatni vaqtincha saqlash (oddiy usul)
    import sys
    setattr(sys.modules['__main__'], 'selected_quality', quality)
    
    await callback.message.edit_text(
        f"🎬 **YouTube video linkini yuboring**\n\n"
        f"Tanlangan sifat: **{quality_names.get(quality, quality)}**\n\n"
        f"Masalan: `https://youtu.be/...` yoki `https://www.youtube.com/watch?v=...`\n\n"
        f"🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "download_tiktok")
async def download_tiktok_prompt(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🎵 **TikTok linkini yuboring**\n\n"
        "Masalan:\n"
        "• `https://www.tiktok.com/@username/video/...`\n"
        "• `https://vm.tiktok.com/...`\n\n"
        "✅ Eng yuqori sifatda yuklab olinadi!\n\n"
        "🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "status")
async def status_callback(callback: types.CallbackQuery):
    remaining = DAILY_UPLOAD_LIMIT - upload_counter
    
    # Disk bo'sh joyi
    import shutil
    disk_usage = shutil.disk_usage('/')
    free_space = f"{disk_usage.free / (1024**3):.1f} GB"
    
    await callback.message.edit_text(
        f"📊 **Bot Holati**\n\n"
        f"✅ Bot ishlayapti\n"
        f"📤 Bugungi yuklash: {upload_counter}/{DAILY_UPLOAD_LIMIT}\n"
        f"⏳ Qolgan: {remaining} ta\n"
        f"💾 Bo'sh joy: {free_space}\n\n"
        f"📁 Yuklangan fayllar: {len(os.listdir(DOWNLOAD_FOLDER))} ta\n\n"
        f"🔙 /start - Asosiy menyu",
        parse_mode=ParseMode.MARKDOWN
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery):
    remaining = DAILY_UPLOAD_LIMIT - upload_counter
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📹 Instagram Video", callback_data="download_instagram")],
        [InlineKeyboardButton(text="▶️ YouTube Video", callback_data="download_youtube")],
        [InlineKeyboardButton(text="🎵 TikTok Video", callback_data="download_tiktok")],
        [InlineKeyboardButton(text="📊 Holat", callback_data="status")],
    ])
    await callback.message.edit_text(
        f"🎬 **Yuqori sifatli video yuklab olish boti**\n\n"
        f"📊 Kunlik qolgan: {remaining} ta\n\n"
        f"🔽 Platformani tanlang yoki to'g'ridan-to'g'ri link yuboring!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )
    await callback.answer()

# ============================================================
# VIDEO QABUL QILISH VA YUKLAB OLISH
# ============================================================
@dp.message(lambda message: message.video is not None)
async def handle_telegram_video(message: types.Message):
    if not check_daily_limit():
        await message.answer(f"❌ Kunlik limit tugadi! Ertaga qayta uruning.")
        return
    
    status_msg = await message.answer("🔄 Telegram fayli yuklab olinmoqda...")
    
    try:
        file_id = message.video.file_id
        file_name = message.video.file_name or "telegram_video.mp4"
        
        temp_path = os.path.join(DOWNLOAD_FOLDER, f"telegram_{int(time.time())}_{file_name}")
        await download_telegram_video(file_id, temp_path)
        
        duration = get_video_duration(temp_path)
        resolution = get_video_resolution(temp_path)
        file_size = get_video_size(temp_path)
        
        increment_upload_counter()
        
        # Yuklab olingan video ma'lumotlarini yuborish
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 YouTube'ga yuklash", callback_data=f"upload_to_youtube|{temp_path}|{file_name}|{duration}")],
            [InlineKeyboardButton(text="📥 Videoni yuklab olish", callback_data=f"download_video|{temp_path}")],
        ])
        
        await status_msg.edit_text(
            f"✅ **Video muvaffaqiyatli yuklab olindi!**\n\n"
            f"📹 Nomi: {file_name[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📐 Rezolyutsiya: {resolution}\n"
            f"💾 Hajmi: {file_size}\n\n"
            f"Quyidagi tugmalar orqali videoni YouTube'ga yuklashingiz yoki yuklab olishingiz mumkin:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

@dp.message(lambda message: "instagram.com" in message.text.lower())
async def handle_instagram_link(message: types.Message):
    if not check_daily_limit():
        await message.answer(f"❌ Kunlik limit tugadi! Ertaga qayta uruning.")
        return
    
    url = message.text.strip()
    status_msg = await message.answer("🔄 Instagram'dan yuklab olinmoqda (eng yuqori sifat)... ⏳")
    
    try:
        video_path, video_title, video_id, duration, resolution = download_instagram_video(url)
        file_size = get_video_size(video_path)
        
        increment_upload_counter()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 YouTube'ga yuklash", callback_data=f"upload_to_youtube|{video_path}|{video_title}|{duration}")],
            [InlineKeyboardButton(text="📥 Videoni yuklab olish", callback_data=f"download_video|{video_path}")],
        ])
        
        await status_msg.edit_text(
            f"✅ **Instagram video muvaffaqiyatli yuklab olindi!**\n\n"
            f"📹 Nomi: {video_title[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📐 Rezolyutsiya: {resolution}\n"
            f"💾 Hajmi: {file_size}\n\n"
            f"Quyidagi tugmalar orqali videoni YouTube'ga yuklashingiz yoki yuklab olishingiz mumkin:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

@dp.message(lambda message: "youtu.be" in message.text.lower() or "youtube.com" in message.text.lower())
async def handle_youtube_link(message: types.Message):
    if not check_daily_limit():
        await message.answer(f"❌ Kunlik limit tugadi! Ertaga qayta uruning.")
        return
    
    url = message.text.strip()
    
    # Tanlangan sifatni olish
    import sys
    quality = getattr(sys.modules['__main__'], 'selected_quality', 'best')
    
    quality_names = {"best": "Eng yuqori", "1080p": "1080p Full HD", "720p": "720p HD", "480p": "480p"}
    
    status_msg = await message.answer(f"🔄 YouTube'dan yuklab olinmoqda ({quality_names.get(quality, quality)})... ⏳")
    
    try:
        video_path, video_title, video_id, duration, resolution = download_youtube_video(url, quality)
        file_size = get_video_size(video_path)
        
        increment_upload_counter()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 YouTube'ga yuklash", callback_data=f"upload_to_youtube|{video_path}|{video_title}|{duration}")],
            [InlineKeyboardButton(text="📥 Videoni yuklab olish", callback_data=f"download_video|{video_path}")],
        ])
        
        await status_msg.edit_text(
            f"✅ **YouTube video muvaffaqiyatli yuklab olindi!**\n\n"
            f"📹 Nomi: {video_title[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"📐 Rezolyutsiya: {resolution}\n"
            f"💾 Hajmi: {file_size}\n\n"
            f"Quyidagi tugmalar orqali videoni YouTube'ga yuklashingiz yoki yuklab olishingiz mumkin:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

@dp.message(lambda message: "tiktok.com" in message.text.lower())
async def handle_tiktok_link(message: types.Message):
    if not check_daily_limit():
        await message.answer(f"❌ Kunlik limit tugadi! Ertaga qayta uruning.")
        return
    
    url = message.text.strip()
    status_msg = await message.answer("🔄 TikTok'dan yuklab olinmoqda (eng yuqori sifat)... ⏳")
    
    try:
        video_path, video_title, video_id, duration, resolution = download_tiktok_video(url)
        file_size = get_video_size(video_path)
        
        increment_upload_counter()
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 YouTube'ga yuklash", callback_data=f"upload_to_youtube|{video_path}|{video_title}|{duration}")],
            [InlineKeyboardButton(text="📥 Videoni yuklab olish", callback_data=f"download_video|{video_path}")],
        ])
        
        await status_msg.edit_text(
            f"✅ **TikTok video muvaffaqiyatli yuklab olindi!**\n\n"
            f"📹 Nomi: {video_title[:50]}\n"
            f"⏱️ Davomiyligi: {int(duration)} sekund\n"
            f"💾 Hajmi: {file_size}\n\n"
            f"Quyidagi tugmalar orqali videoni YouTube'ga yuklashingiz yoki yuklab olishingiz mumkin:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Xatolik: {str(e)[:200]}")

# ============================================================
# YOUTUBEGA YUKLASH VA YUKLAB OLISH CALLBACKLARI
# ============================================================
@dp.callback_query(lambda c: c.data.startswith("upload_to_youtube|"))
async def upload_to_youtube_callback(callback: types.CallbackQuery):
    data = callback.data.split("|")
    if len(data) >= 4:
        video_path = data[1]
        video_title = data[2]
        duration = float(data[3])
        
        await callback.message.edit_text("📤 YouTube'ga yuklanmoqda... (1-3 daqiqa)")
        
        try:
            video_url, is_short = upload_to_youtube(video_path, video_title, duration, "public")
            
            await callback.message.edit_text(
                f"✅ **Video YouTube'ga muvaffaqiyatli yuklandi!**\n\n"
                f"📹 Nomi: {video_title[:50]}\n"
                f"📌 Format: {'YouTube Shorts' if is_short else 'Oddiy video'}\n"
                f"🔗 Link: {video_url}\n\n"
                f"🎉 Botdan foydalanganingiz uchun rahmat!",
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True
            )
            
        except Exception as e:
            await callback.message.edit_text(f"❌ YouTube'ga yuklash xatosi: {str(e)[:200]}")
    
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("download_video|"))
async def download_video_callback(callback: types.CallbackQuery):
    data = callback.data.split("|")
    if len(data) >= 2:
        video_path = data[1]
        
        if os.path.exists(video_path):
            # Faylni Telegram orqali yuborish
            with open(video_path, 'rb') as f:
                await callback.message.answer_document(
                    types.BufferedInputFile(f.read(), filename=os.path.basename(video_path)),
                    caption="📥 Siz so'ragan video fayl"
                )
        else:
            await callback.message.answer("❌ Fayl topilmadi!")
    
    await callback.answer()

# ============================================================
# ODDIY LINKLAR (platforma aniqlanmasa)
# ============================================================
@dp.message()
async def handle_unknown_link(message: types.Message):
    url = message.text.strip()
    
    # Link ekanligini tekshirish
    if not (url.startswith('http://') or url.startswith('https://')):
        await message.answer(
            "❌ Iltimos, haqiqiy video linkini yuboring!\n\n"
            "Qo'llab-quvvatlanadigan platformalar:\n"
            "• Instagram: instagram.com/reel/...\n"
            "• YouTube: youtu.be/...\n"
            "• TikTok: tiktok.com/@...\n\n"
            "🔽 Platformani tanlash uchun /start",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    await message.answer(
        "❌ Platforma aniqlanmadi!\n\n"
        "Qo'llab-quvvatlanadigan platformalar:\n"
        "• Instagram (instagram.com)\n"
        "• YouTube (youtu.be, youtube.com)\n"
        "• TikTok (tiktok.com)\n\n"
        "🔽 Platformani tanlash uchun /start",
        parse_mode=ParseMode.MARKDOWN
    )

# ============================================================
# BOTNI ISHGA TUSHIRISH
# ============================================================
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    print("✅ Webhook o'chirildi!")

async def main():
    print("=" * 50)
    print("🤖 YUQORI SIFATLI VIDEO YUKLAB OLISH BOTI")
    print("=" * 50)
    print(f"✅ Bot ishga tushdi!")
    print(f"📊 Kunlik limit: {DAILY_UPLOAD_LIMIT} ta video")
    print(f"📁 Yuklash papkasi: {DOWNLOAD_FOLDER}")
    print("=" * 50)
    print("Qo'llab-quvvatlanadigan platformalar:")
    print("  • Instagram (eng yuqori sifat)")
    print("  • YouTube (1080p, 720p, 480p)")
    print("  • TikTok")
    print("  • Telegram video fayllar")
    print("=" * 50)
    
    await on_startup()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ Bot to'xtatildi")
    except Exception as e:
        print(f"❌ Xatolik: {e}")
