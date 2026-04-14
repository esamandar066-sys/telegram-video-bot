import asyncio, os, pickle, json
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import yt_dlp

BOT_TOKEN = "8227185560:AAFNIHiiSE1bnJXKA5vrysmYlaMB52DRapw"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# YouTube token fayli
TOKEN_FILE = "token.pickle"
CLIENT_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def get_youtube_service():
    """YouTube servisini olish (browsersiz)"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # Browsersiz autentifikatsiya
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_FILE, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=False)
            print(f"🔗 Autentifikatsiya uchun linkni oching: {flow.authorization_url()[0]}")
        
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
    
    return build("youtube", "v3", credentials=creds)

@dp.message(Command("start"))
async def start(msg: types.Message):
    await msg.answer("🎬 Bot ishga tushdi!\n\n📹 Instagram linkini yuboring")

@dp.message()
async def handle(msg: types.Message):
    url = msg.text.strip()
    if "instagram.com" not in url:
        await msg.answer("📸 Iltimos, Instagram linkini yuboring")
        return
    
    status = await msg.answer("⏳ Yuklab olinmoqda...")
    
    try:
        # Yuklab olish
        ydl_opts = {'format': 'best', 'outtmpl': 'video.mp4', 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get('title', 'video')[:80]
        
        # YouTube'ga yuklash
        await status.edit_text("📤 YouTube'ga yuklanmoqda...")
        youtube = get_youtube_service()
        
        duration = 15  # oddiy duration
        is_short = duration <= 60
        
        body = {
            'snippet': {
                'title': f"{title} {'#shorts' if is_short else ''}",
                'description': f"Instagram'dan yuklandi\n\n#instagram #reels",
                'categoryId': '22'
            },
            'status': {'privacyStatus': 'public'}
        }
        
        media = MediaFileUpload('video.mp4', chunksize=1024*1024, resumable=True)
        request = youtube.videos().insert(part=','.join(body.keys()), body=body, media_body=media)
        response = request.execute()
        
        video_url = f"https://youtu.be/{response['id']}"
        await status.edit_text(f"✅ Yuklandi!\n🔗 {video_url}")
        
        # Tozalash
        if os.path.exists('video.mp4'):
            os.remove('video.mp4')
            
    except Exception as e:
        await status.edit_text(f"❌ Xatolik: {str(e)[:100]}")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
