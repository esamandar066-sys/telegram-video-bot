import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

BOT_TOKEN = "8227185560:AAFNIHiiSE1bnJXKA5vrysmYlaMB52DRapw"
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer(
        "🎬 **Video Upload Bot ishga tushdi!**\n\n"
        "📹 Video fayl yoki Instagram linkini yuboring",
        parse_mode=ParseMode.MARKDOWN
    )

@dp.message()
async def handle_message(message: types.Message):
    if message.video:
        await message.answer(f"✅ Video qabul qilindi!")
    elif message.text and "instagram.com" in message.text:
        await message.answer("📸 Instagram linki qabul qilindi!")
    else:
        await message.answer("📹 Iltimos, video fayl yoki Instagram linkini yuboring!")

async def main():
    # Webhook'ni o'chirish (MUHIM!)
    await bot.delete_webhook(drop_pending_updates=True)
    print("🤖 Bot ishga tushdi! Webhook o'chirildi.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
