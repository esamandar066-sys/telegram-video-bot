import os
import asyncio
import yt_dlp
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

BOT_TOKEN = "8227185560:AAFNIHiiSE1bnJXKA5vrysmYlaMB52DRapw"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🎬 **Video Upload Bot**\n\n"
        "📹 Video fayl yoki Instagram linkini yuboring:\n"
        "• Video fayl (MP4, AVI, MOV)\n"
        "• Instagram: instagram.com/reel/...\n\n"
        "⚡️ 1 minutgacha video -> YouTube Shorts",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message()
async def handle_message(message: types.Message):
    await message.answer("⏳ Video qabul qilindi! Qayta ishlanmoqda...")

async def main():
    print("🤖 Bot ishga tushdi!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
