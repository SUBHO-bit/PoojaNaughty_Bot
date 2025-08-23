import logging
import os
import random
from datetime import datetime
from flask import Flask, request # <-- Flask import করা আছে
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
import asyncio

# ==========================
# 1. CONFIGURATION
# ==========================
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', 'default_user')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

if not all([TELEGRAM_BOT_TOKEN, GROQ_API_KEY, WEBHOOK_URL]):
    raise ValueError("Error: Important environment variables are missing!")

INSTAGRAM_LINK = f'https://www.instagram.com/{INSTAGRAM_USERNAME}'
IMAGE_FOLDER = 'Images'

try:
    groq_client = AsyncGroq(api_key=GROQ_API_KEY)
except Exception as e:
    logging.error(f"FATAL: Groq initialization failed. Error: {e}")
    groq_client = None

language_options = {'English': 'en', 'Hindi': 'hi', 'Bengali': 'bn', 'Tamil': 'ta', 'Telugu': 'te', 'Marathi': 'mr'}

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

persistence = PicklePersistence(filepath="bot_data")

# ==========================
# 2. BOT FUNCTIONS (অপরিবর্তিত)
# ==========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... আপনার start ফাংশনের কোড ...
    if context.user_data.get('followed', False): await send_welcome(update, context); return
    welcome_msg = (f"🌟 *Welcome!* 🌟\n\nTo chat, please follow:\n\n1. 👉 Follow [@{INSTAGRAM_USERNAME}]({INSTAGRAM_LINK})\n2. ✅ Tap 'I Followed' below.")
    keyboard = [[InlineKeyboardButton("📸 Open Instagram", url=INSTAGRAM_LINK)], [InlineKeyboardButton("✅ I Followed", callback_data="follow_verify")]]
    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... আপনার handle_callback ফাংশনের কোড ...
    query = update.callback_query; await query.answer()
    if query.data == "follow_verify":
        context.user_data['followed'] = True; context.user_data['verified_at'] = datetime.now().isoformat()
        await query.edit_message_text("✅ *Verification Successful!*\n\nThank you! Choose your language:", parse_mode='Markdown')
        languages = [[key] for key in language_options.keys()]
        await query.message.reply_text("Please select your language:", reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))
        await send_random_image(query.message.chat_id, context)

async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... আপনার send_welcome ফাংশনের কোড ...
    await send_random_image(update.message.chat_id, context); welcome_msg = "Welcome back! 😊 Please choose your language."
    languages = [[key] for key in language_options.keys()]
    await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))

async def generate_reply_with_groq(user_text, user_lang):
    # ... আপনার generate_reply_with_groq ফাংশনের কোড ...
    if not groq_client: return "Sorry, connection problem! Please try again! 😊"
    try:
        chat_completion = await groq_client.chat.completions.create(messages=[{"role": "system", "content": f"You are Pooja, a friendly, romantic, and flirty AI girlfriend. Use emojis. Keep responses very short (1-2 sentences). Reply in {user_lang}."}, {"role": "user", "content": user_text}], model="llama3-70b-8192", temperature=0.8, max_tokens=100)
        return chat_completion.choices[0].message.content.strip()
    except Exception as e: logger.error(f"Groq API error: {e}"); return "That's an interesting thought! Let's talk about something else. 😉"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... আপনার handle_message ফাংশনের কোড ...
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
    # ... আপনার send_random_image ফাংশনের কোড ...
    if not os.path.exists(IMAGE_FOLDER): return
    try:
        images = [img for img in os.listdir(IMAGE_FOLDER) if img.lower().endswith(('.png', '.jpg', '.jpeg'))]
        if images:
            with open(os.path.join(IMAGE_FOLDER, random.choice(images)), 'rb') as photo: await context.bot.send_photo(chat_id, photo)
    except Exception as e: logger.error(f"Error sending image: {e}")


# ==========================
# 3. BOT STARTUP (হোস্টিং এর জন্য)
# ==========================
application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

# --- এই লাইনটি খুবই গুরুত্বপূর্ণ ---
app = Flask(__name__)
# --------------------------------

@app.route("/")
def index(): return "Hello! Bot is running."

@app.route(f'/{TELEGRAM_BOT_TOKEN}', methods=['POST'])
async def webhook():
    update = Update.de_json(await request.get_json(force=True), application.bot)
    await application.process_update(update); return 'ok'

async def setup():
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(TEXT, handle_message))
    application.add_handler(CallbackQueryHandler(handle_callback))
    await application.bot.set_webhook(url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")

if __name__ != '__main__':
    asyncio.run(setup())
