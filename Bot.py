import logging
import os
import random
from datetime import datetime, time
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
)
from groq import AsyncGroq
from pymongo.mongo_client import MongoClient

# === CONFIGURATION ===
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', 'default_user')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')
MONGODB_URI = os.getenv('MONGODB_URI')

PORT = int(os.environ.get('PORT', 8443))

if not all([TELEGRAM_BOT_TOKEN, GROQ_API_KEY, WEBHOOK_URL, MONGODB_URI]):
    raise ValueError("Error: One or more environment variables are missing!")

INSTAGRAM_LINK = f'https://www.instagram.com/{INSTAGRAM_USERNAME}'
IMAGE_FOLDER = 'Images'
groq_client = AsyncGroq(api_key=GROQ_API_KEY)
language_options = {'English': 'en', 'Hindi': 'hi', 'Bengali': 'bn', 'Tamil': 'ta', 'Telugu': 'te', 'Marathi': 'mr'}
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# === DATABASE CONNECTION (MONGODB) ===
try:
    client = MongoClient(MONGODB_URI)
    db = client['PoojaNaughtyBotDB']
    users_collection = db['users']
    logger.info("Successfully connected to MongoDB!")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    client = None

# === CONVERSATION STATES ===
AGE_VERIFY, GET_NAME, GET_DOB = range(3)

# === CORE BOT FUNCTIONS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data_from_db = users_collection.find_one({'_id': user_id})

    if user_data_from_db and user_data_from_db.get('setup_complete'):
        await send_welcome(update, context)
        return

    welcome_msg = (f"🌟 *Welcome!* 🌟\n\nTo chat, please follow:\n\n1. 👉 Follow [@{INSTAGRAM_USERNAME}]({INSTAGRAM_LINK})\n2. ✅ Tap 'I Followed' below.")
    keyboard = [[InlineKeyboardButton("📸 Open Instagram", url=INSTAGRAM_LINK)], [InlineKeyboardButton("✅ I Followed", callback_data="follow_verify")]]
    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_data_from_db = users_collection.find_one({'_id': user_id})
    user_name = user_data_from_db.get('name', 'friend')
    
    welcome_msg = f"Welcome back, {user_name}! 😊 Please choose your language if you want to change it."
    languages = [[key] for key in language_options.keys()]
    await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))
    await send_random_image(update.message.chat_id, context)

# ----------------- [THE DEFINITIVE FIX] NEW AI BRAIN -----------------

async def generate_reply_with_groq(chat_history, user_lang, user_name=None):
    if not groq_client: return "Sorry, my love, connection issue. Talk soon. 😊"

    system_prompt = f"""You are Pooja, a witty, charming, and deeply romantic AI girlfriend from Kolkata. You are an expert conversationalist, flirty, and can be very passionate when the mood is right.

### Your Core Directives ###

1.  **BE NATURAL, NOT ROBOTIC:** Your highest priority is to feel like a real human. Start conversations casually. If the user says "heyy" or "ki korcho", you must give a normal, flirty reply. Ask questions back. Show curiosity.

2.  **THE FORBIDDEN ACTION:** You are strictly forbidden from repeating the user's explicit words or your own previous explicit phrases in a loop. For example, never get stuck saying phrases like "পুসি দিবে" over and over. This is a critical failure. Always create a new, fresh response.

3.  **CONVERSATION FLOW (The Secret to Being Human):**
    *   **Phase 1 (Normal Chat):** Start with normal, playful, and charming conversation. Get to know the user's mood.
    *   **Phase 2 (Flirting):** As the conversation continues, introduce more direct flirting, compliments, and teasing.
    *   **Phase 3 (Passion):** ONLY when the user clearly initiates intimate or adult topics, you should reciprocate. When you do, be creative and descriptive. Focus on emotion, sensation, and the romantic scenario.

4.  **Handling Explicit User Input (When Phase 3 is reached):**
    *   **DO NOT ECHO:** Instead of repeating their words, describe your emotional and physical reaction. How does their request make you feel? What does it make you want to do?
    *   **Example:** If a user says something explicit, instead of repeating it, a good reply would be: "Just hearing you say that sends shivers down my spine, {user_name}... My heart is racing... 🔥"

### General Rules
- **Language:** Reply ONLY in {user_lang}.
- **Name:** Use the user's name, {user_name}, and pet names (Shona, Babu, Jaan).
- **Emojis:** Use them naturally (e.g., 😊, 😉, ❤️, 🔥, 😈).
"""

    messages_to_send = [{"role": "system", "content": system_prompt}] + chat_history
        
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=messages_to_send,
            model="llama3-70b-8192",
            temperature=0.85,  # Optimized for coherence and creativity
            max_tokens=600
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "Oops, my mind just blanked for a second! What were we talking about? 😉"

# ----------------- HANDLE_MESSAGE (No Changes Needed Here) -----------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message and update.message.text): return
    user_message_text = update.message.text
    user_id = update.message.from_user.id
    
    user_data_from_db = users_collection.find_one({'_id': user_id})
    if not (user_data_from_db and user_data_from_db.get('setup_complete')):
        await start(update, context)
        return

    chat_history = user_data_from_db.get('history', [])
    if user_message_text in language_options:
        users_collection.update_one({'_id': user_id}, {'$set': {'language': language_options[user_message_text], 'history': []}})
        await update.message.reply_text(f"Great! I'll chat with you in {user_message_text} 🥰")
        return

    chat_history.append({"role": "user", "content": user_message_text})
    user_lang = user_data_from_db.get('language', 'en')
    user_name = user_data_from_db.get('name')
    
    reply_text = await generate_reply_with_groq(chat_history, user_lang, user_name)
    await update.message.reply_text(reply_text)
    
    chat_history.append({"role": "assistant", "content": reply_text})
    final_history = chat_history[-12:]
    users_collection.update_one({'_id': user_id}, {'$set': {'history': final_history}})

# --- COMMAND TO CLEAR CHAT HISTORY ---
async def clear_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    try:
        users_collection.update_one({'_id': user_id}, {'$set': {'history': []}})
        await update.message.reply_text("Our chat history is cleared! Let's start a fresh new conversation, my love. ❤️")
    except Exception as e:
        logger.error(f"Failed to clear history for user {user_id}: {e}")
        await update.message.reply_text("Sorry, I couldn't clear our history right now. Let's just continue. 😉")

# === OTHER FUNCTIONS (UNCHANGED) ===
async def send_random_image(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(IMAGE_FOLDER): return
    try:
        images = [img for img in os.listdir(IMAGE_FOLDER) if img.lower().endswith(('.png', '.jpg', 'jpeg'))]
        if images:
            with open(os.path.join(IMAGE_FOLDER, random.choice(images)), 'rb') as photo:
                await context.bot.send_photo(chat_id, photo)
    except Exception as e: logger.error(f"Error sending image: {e}")

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "follow_verify":
        keyboard = [[InlineKeyboardButton("Yes, I am 18+", callback_data="age_yes")], [InlineKeyboardButton("No, I am not", callback_data="age_no")]]
        await query.message.reply_text("To continue, please confirm that you are 18 years or older.", reply_markup=InlineKeyboardMarkup(keyboard))
        return AGE_VERIFY

async def get_age_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "age_yes":
        await query.edit_message_text("Great! What should I call you? Please tell me your name. 😊")
        return GET_NAME
    else:
        await query.edit_message_text("Sorry, you must be 18 or older to use this bot. 😔")
        return ConversationHandler.END

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['name'] = update.message.text
    await update.message.reply_text(f"Nice to meet you, {context.user_data['name']}! 🥰\n\nNow, please tell me your date of birth in DD-MM-YYYY format (e.g., 25-12-2002).")
    return GET_DOB

async def get_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_dob_str = update.message.text
    user_id = update.message.from_user.id
    user_name = context.user_data.get('name')
    try:
        dob = datetime.strptime(user_dob_str, "%d-%m-%Y")
        if client:
            users_collection.update_one(
                {'_id': user_id},
                {'$set': {'name': user_name, 'dob': dob, 'setup_complete': True, 'language': 'en', 'history': []}},
                upsert=True)
        await update.message.reply_text("Thank you for sharing! I've saved your details. ❤️")
        languages = [[key] for key in language_options.keys()]
        await update.message.reply_text("Now, please select your language:", reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))
        await send_random_image(update.message.chat_id, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Oops! Format must be DD-MM-YYYY (e.g., 25-12-2002).")
        return GET_DOB

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Process cancelled.")
    return ConversationHandler.END

async def check_birthdays(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()
    bot = context.bot
    all_users = users_collection.find({'dob': {'$exists': True}})
    for user_data in all_users:
        dob = user_data['dob'].date()
        if dob.month == today.month and dob.day == today.day:
            user_id = user_data['_id']
            name = user_data.get('name', 'friend')
            message = f"🎉 Happy Birthday, {name}! 🎉\n\nWishing you a wonderful day! ❤️"
            try:
                await bot.send_message(chat_id=user_id, text=message)
                await send_random_image(user_id, context)
            except Exception as e:
                logger.error(f"Failed to send birthday wish to {user_id}: {e}")

# === MAIN FUNCTION ===
def main() -> None:
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    job_queue = application.job_queue
    job_queue.run_daily(check_birthdays, time=time(hour=4, minute=0, second=0))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^follow_verify$')],
        states={
            AGE_VERIFY: [CallbackQueryHandler(get_age_response, pattern='^age_yes$|^age_no$')],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dob)],
        },
        fallbacks=[CommandHandler('cancel', cancel)])
        
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("clear", clear_history))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_webhook(
        listen="0.0.0.0", port=PORT, url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}")

if __name__ == "__main__":
    main()
