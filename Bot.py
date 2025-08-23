import logging
import os
import random
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv
from gtts import gTTS
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    PicklePersistence,
    filters,
)
from groq import AsyncGroq
import asyncio

# === CONFIGURATION ===
load_dotenv()
# (বাকি সব ভেরিয়েবল আগের মতোই থাকবে)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', 'default_user')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

if not all([TELEGRAM_BOT_TOKEN, GROQ_API_KEY, WEBHOOK_URL]):
    raise ValueError("Error: Environment variables are missing!")

INSTAGRAM_LINK = f'https://www.instagram.com/{INSTAGRAM_USERNAME}'
IMAGE_FOLDER = 'Images'
groq_client = AsyncGroq(api_key=GROQ_API_KEY)
language_options = {'English': 'en', 'Hindi': 'hi', 'Bengali': 'bn', 'Tamil': 'ta', 'Telugu': 'te', 'Marathi': 'mr'}
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
persistence = PicklePersistence(filepath="bot_data")

# === BOT APPLICATION SETUP ===
application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

# === BOT FUNCTIONS (অপরিবর্তিত) ===
# (আপনার start, handle_callback, send_welcome, generate_reply_with_groq, handle_message, send_random_image ফাংশনগুলো এখানে অপরিবর্তিত থাকবে)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('followed', False): await send_welcome(update, context); return
    welcome_msg = (f"🌟 *Welcome!* 🌟\n\nTo chat, please follow:\n\n1. 👉 Follow [@{INSTAGRAM_USERNAME}]({INSTAGRAM_LINK})\n2. ✅ Tap 'I Followed' below.")
    keyboard = [[InlineKeyboardButton("📸 Open Instagram", url=INSTAGRAM_LINK)], [InlineKeyboardButton("✅ I Followed", callback_data="follow_verify")]]
    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "follow_verify":
        context.user_data['followed'] = True; context.user_data['verified_at'] = datetime.now().isoformat()
        await query.edit_message_text("✅ *Verification Successful!*\n\nThank you! Choose your language:", parse_mode='Markdown')
        languages = [[key] for key in language_options.keys()]
        await query.message.reply_text("Please select your language:", reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))
        await send_random_image(query.message.chat_id, context)
async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random_image(update.message.chat_id, context); welcome_msg = "Welcome back! 😊 Please choose your language."
    languages = [[key] for key in language_options.keys()]
    await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))
async def generate_reply_with_groq(user_text, user_lang):
    if not groq_client: return "Sorry, connection problem! Please try again! 😊"
    try:
        chat_completion = await groq_client.chat.completions.create(messages=[{"role": "system", "content": f"You are Pooja, a friendly, romantic, and flirty AI girlfriend. Use emojis. Keep responses very short (1-2 sentences). Reply in {user_lang}."}, {"role": "user", "content": user_text}], model="llama3-70b-8192", temperature=0.8, max_tokens=100)
        return chat_completion.choices[0].message.content.strip()
    except Exception as e: logger.error(f"Groq API error: {e}"); return "That's an interesting thought! Let's talk about something else. 😉"
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message and update.message.text): return
    user_message = update.message.text
    if not context.user_data.get('followed', False): await start(update, context); return
    if user_message in language_options:
        context.user_data['language'] = language_options[user_message]; context.user_data['message_count'] = 0
        await update.message.reply_text(f"Great! I'll chat with you in {user_message} 🥰"); return
    user_lang = context.user_data.get('language', 'en'); reply = await generate_reply_with_groq(user_message, user_lang); await update.message.reply_text(reply)
    message_count = context.user_data.get('message_count', 0) + 1; context.user_data['message_count'] = message_count
    if message_count > 0 and message_count % 20 == 0: await update.message.reply_text("Wow, we've been chatting so much! 😉 Here's a little something for you..."); await send_random_image(update.message.chat_id, context)
async def send_random_image(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(IMAGE_FOLDER): return
    try:
        images = [img for img in os.listdir(IMAGE_FOLDER) if img.lower().endswith(('.png', '.jpg', 'jpeg'))]
        if images:
            with open(os.path.join(IMAGE_FOLDER, random.choice(images)), 'rb') as photo: await context.bot.send_photo(chat_id, photo)
    except Exception as e: logger.error(f"Error sending image: {e}")

# === Add handlers to the application ===
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
application.add_handler(CallbackQueryHandler(handle_callback))

# === FLASK APP (for webhook) ===
app = Flask(__name__)

@app.route("/")
def index():
    return "Hello! Bot is running."

# --- এই ফাংশনটি এখন সিঙ্ক্রোনাস ---
@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
def webhook():
    """সিঙ্ক্রোনাস Webhook যা অ্যাসিঙ্ক্রোনাস টাস্ক চালায়"""
    update = Update.de_json(request.get_json(force=True), application.bot)
    # অ্যাসিঙ্ক্রোনাস টাস্ক চালানোর জন্য asyncio.run ব্যবহার করা হচ্ছে
    asyncio.run(application.process_update(update))
    return 'ok', 200

# === Main setup to run bot and set webhook ===
async def main_async():
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}", allowed_updates=Update.ALL_TYPES)

if __name__ != '__main__':
    # Gunicorn যখন অ্যাপটি চালু করে, তখন এই অংশটি চলে
    asyncio.run(main_async())
