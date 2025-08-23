# === প্রয়োজনীয় লাইব্রেরিগুলো আনা হচ্ছে ===
import logging
import os
import random
from datetime import datetime

# এই প্যাকেজগুলো ইনস্টল করতে হবে
# pip install python-telegram-bot[ext] python-dotenv groq gtts
from dotenv import load_dotenv
from gtts import gTTS
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    PicklePersistence,
)
from telegram.ext.filters import TEXT
from groq import AsyncGroq

# === ধাপ ১: কনফিগারেশন ===

# .env ফাইল থেকে গোপন তথ্য লোড করার জন্য
load_dotenv()

# .env ফাইল থেকে আপনার টোকেন এবং অন্যান্য তথ্য এখানে লোড করা হচ্ছে
# নিশ্চিত করুন আপনার .env ফাইলে এই লাইনগুলো আছে:
# TELEGRAM_BOT_TOKEN="আপনার টেলিগ্রাম বট টোকেন"
# GROQ_API_KEY="আপনার Groq API কী"
# INSTAGRAM_USERNAME="আপনার ইনস্টাগ্রাম ইউজারনেম"
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME')

# যদি টোকেন খুঁজে না পাওয়া যায়, তাহলে প্রোগ্রাম বন্ধ হয়ে যাবে
if not TELEGRAM_BOT_TOKEN or not GROQ_API_KEY or not INSTAGRAM_USERNAME:
    print("ত্রুটি: .env ফাইলে TELEGRAM_BOT_TOKEN, GROQ_API_KEY, বা INSTAGRAM_USERNAME পাওয়া যায়নি।")
    exit()

# অন্যান্য প্রয়োজনীয় ভেরিয়েবল
INSTAGRAM_LINK = f'https://www.instagram.com/{INSTAGRAM_USERNAME}'
IMAGE_FOLDER = 'Images'  # ছবি রাখার জন্য ফোল্ডারের নাম

# Groq ক্লায়েন্ট (AI মডেল) চালু করা হচ্ছে
try:
    groq_client = AsyncGroq(api_key=GROQ_API_KEY)
except Exception:
    print("ত্রুটি: Groq API কী সম্ভবত ভুল।")
    groq_client = None

# ভাষার অপশন
language_options = {
    'English': 'en', 'Hindi': 'hi', 'Bengali': 'bn',
    'Tamil': 'ta', 'Telugu': 'te', 'Marathi': 'mr'
}

# লগিং সেটআপ (টার্মিনালে কী ঘটছে তা দেখার জন্য)
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# ব্যবহারকারীর তথ্য মনে রাখার জন্য (যেমন কে ফলো করেছে)। এটি bot_data নামে একটি ফাইল তৈরি করবে।
persistence = PicklePersistence(filepath="bot_data")


# === ধাপ ২: বটের মূল ফাংশনগুলো (এখানে কোনো পরিবর্তন নেই) ===

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('followed', False):
        await send_welcome(update, context)
        return
    welcome_msg = (
        "🌟 *Welcome to Our Exclusive Chat Experience!* 🌟\n\n"
        "To unlock chatting with me, please follow these steps:\n\n"
        f"1. 👉 Follow our Instagram [@{INSTAGRAM_USERNAME}]({INSTAGRAM_LINK})\n"
        "2. ✅ Come back here and tap 'I Followed' below\n"
        "3. 🎁 Get instant access to chat with me!"
    )
    keyboard = [[InlineKeyboardButton("📸 Open Instagram", url=INSTAGRAM_LINK)], [InlineKeyboardButton("✅ I Followed", callback_data="follow_verify")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=reply_markup, disable_web_page_preview=True)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "follow_verify":
        context.user_data['followed'] = True
        context.user_data['verified_at'] = datetime.now().isoformat()
        await query.edit_message_text("✅ *Verification Successful!*\n\nThank you for following! You can now chat with me. 😊\n" "Choose your preferred language to get started:", parse_mode='Markdown')
        languages = [[key] for key in language_options.keys()]
        markup = ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True)
        await query.message.reply_text("Please select your language:", reply_markup=markup)
        await send_random_image(query.message.chat_id, context)

async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random_image(update.message.chat_id, context)
    welcome_msg = "Welcome back! 😊 Please choose your language to continue."
    languages = [[key] for key in language_options.keys()]
    markup = ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True)
    await update.message.reply_text(welcome_msg, reply_markup=markup)

async def generate_reply_with_groq(user_text, user_lang):
    if not groq_client:
        return "Sorry, AI connection problem! Please try again! 😊"
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": f"You are Pooja, a friendly, romantic, and flirty AI girlfriend. Use emojis. Keep responses very short (1-2 sentences). Reply in {user_lang}."},
                {"role": "user", "content": user_text}
            ],
            model="llama3-70b-8192", temperature=0.8, max_tokens=100,
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "That's an interesting thought! Let's talk about something else. 😉"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text: return
    user_message = update.message.text
    if not context.user_data.get('followed', False):
        await start(update, context)
        return
    if user_message in language_options:
        context.user_data['language'] = language_options[user_message]
        context.user_data['message_count'] = 0
        await update.message.reply_text(f"Great! I'll chat with you in {user_message} 🥰")
        return
    user_lang = context.user_data.get('language', 'en')
    reply = await generate_reply_with_groq(user_message, user_lang)
    await update.message.reply_text(reply)
    message_count = context.user_data.get('message_count', 0) + 1
    context.user_data['message_count'] = message_count
    if message_count > 0 and message_count % 20 == 0:
        await update.message.reply_text("Wow, we've been chatting so much! 😉 Here's a little something for you...")
        await send_random_image(update.message.chat_id, context)

async def send_random_image(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(IMAGE_FOLDER): return
    try:
        images = [img for img in os.listdir(IMAGE_FOLDER) if img.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if images:
            img_path = os.path.join(IMAGE_FOLDER, random.choice(images))
            with open(img_path, 'rb') as photo:
                await context.bot.send_photo(chat_id, photo)
    except Exception as e:
        logger.error(f"Error sending image: {e}")


# === ধাপ ৩: বট চালু করার কোড ===
def main():
    # বট অ্যাপ্লিকেশন তৈরি করা হচ্ছে
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

    # কোন কমান্ডে কোন ফাংশন কাজ করবে তা ঠিক করা হচ্ছে
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(TEXT, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # বট চালু করা হচ্ছে (এটি চলতে থাকবে যতক্ষণ আপনি টার্মিনাল বন্ধ না করবেন)
    logger.info("বট চালু হচ্ছে...")
    application.run_polling()
    logger.info("বট বন্ধ হয়েছে।")

# এই লাইনটি নিশ্চিত করে যে main() ফাংশনটি তখনই চলবে যখন আপনি সরাসরি এই ফাইলটি চালাবেন
if __name__ == '__main__':
    main()