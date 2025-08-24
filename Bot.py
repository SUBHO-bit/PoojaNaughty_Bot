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
    PicklePersistence,
    filters,
    ConversationHandler,
)
from groq import AsyncGroq

# === CONFIGURATION ===
load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GROQ_API_KEY = os.getenv('GROQ_API_KEY')
INSTAGRAM_USERNAME = os.getenv('INSTAGRAM_USERNAME', 'default_user')
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

# Render সার্ভার PORT এনভায়রনমেন্ট ভেরিয়েবল সেট করে, যা আমাদের ব্যবহার করতে হবে
PORT = int(os.environ.get('PORT', 8443))

if not all([TELEGRAM_BOT_TOKEN, GROQ_API_KEY, WEBHOOK_URL]):
    raise ValueError("Error: Environment variables are missing!")

INSTAGRAM_LINK = f'https://www.instagram.com/{INSTAGRAM_USERNAME}'
IMAGE_FOLDER = 'Images'
groq_client = AsyncGroq(api_key=GROQ_API_KEY)
language_options = {'English': 'en', 'Hindi': 'hi', 'Bengali': 'bn', 'Tamil': 'ta', 'Telugu': 'te', 'Marathi': 'mr'}
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)
persistence = PicklePersistence(filepath="bot_data")

# === CONVERSATION STATES ===
# ব্যবহারকারীর তথ্য সংগ্রহের জন্য ConversationHandler-এর ধাপগুলো
AGE_VERIFY, GET_NAME, GET_DOB = range(3)

# === CORE BOT FUNCTIONS ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # যদি ব্যবহারকারী আগে থেকেই ভেরিফাইড এবং তথ্য দিয়ে থাকেন, তাহলে সরাসরি চ্যাটে পাঠান
    if context.user_data.get('setup_complete', False):
        await send_welcome(update, context)
        return

    # নতুন ব্যবহারকারীদের জন্য ফলো করতে বলা
    welcome_msg = (f"🌟 *Welcome!* 🌟\n\nTo chat, please follow:\n\n1. 👉 Follow [@{INSTAGRAM_USERNAME}]({INSTAGRAM_LINK})\n2. ✅ Tap 'I Followed' below.")
    keyboard = [[InlineKeyboardButton("📸 Open Instagram", url=INSTAGRAM_LINK)], [InlineKeyboardButton("✅ I Followed", callback_data="follow_verify")]]
    await update.message.reply_text(welcome_msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard), disable_web_page_preview=True)

async def send_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = context.user_data.get('name', 'friend')
    welcome_msg = f"Welcome back, {user_name}! 😊 Please choose your language if you want to change it."
    languages = [[key] for key in language_options.keys()]
    await update.message.reply_text(welcome_msg, reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))
    await send_random_image(update.message.chat_id, context)

async def generate_reply_with_groq(user_text, user_lang, user_name=None):
    if not groq_client: return "Sorry, connection problem! Please try again! 😊"
    
    system_prompt = f"You are Pooja, a friendly, romantic, and flirty AI girlfriend. Use emojis. Keep responses very short (1-2 sentences). Reply in {user_lang}."
    
    if user_name:
        system_prompt += f" The user's name is {user_name}. Occasionally, and only when it feels natural, address the user by their name to make the conversation more personal. Don't use the name in every message."
        
    try:
        chat_completion = await groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text}
            ],
            model="llama3-70b-8192",
            temperature=0.8,
            max_tokens=100
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return "That's an interesting thought! Let's talk about something else. 😉"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not (update.message and update.message.text): return
    user_message = update.message.text

    # যদি ব্যবহারকারীর সেটআপ সম্পূর্ণ না হয়, তাহলে তাকে /start করতে বলা
    if not context.user_data.get('setup_complete', False):
        await start(update, context)
        return

    if user_message in language_options:
        context.user_data['language'] = language_options[user_message]
        context.user_data['message_count'] = 0
        await update.message.reply_text(f"Great! I'll chat with you in {user_message} 🥰")
        return

    user_lang = context.user_data.get('language', 'en')
    user_name = context.user_data.get('name')
    reply = await generate_reply_with_groq(user_message, user_lang, user_name)
    await update.message.reply_text(reply)

    message_count = context.user_data.get('message_count', 0) + 1
    context.user_data['message_count'] = message_count
    if message_count > 0 and message_count % 20 == 0:
        await update.message.reply_text("Wow, we've been chatting so much! 😉 Here's a little something for you...")
        await send_random_image(update.message.chat_id, context)

async def send_random_image(chat_id, context: ContextTypes.DEFAULT_TYPE):
    if not os.path.exists(IMAGE_FOLDER):
        logger.warning(f"Image folder '{IMAGE_FOLDER}' not found.")
        return
    try:
        images = [img for img in os.listdir(IMAGE_FOLDER) if img.lower().endswith(('.png', '.jpg', 'jpeg'))]
        if images:
            with open(os.path.join(IMAGE_FOLDER, random.choice(images)), 'rb') as photo:
                await context.bot.send_photo(chat_id, photo)
        else:
            logger.info(f"No images found in '{IMAGE_FOLDER}'.")
    except Exception as e:
        logger.error(f"Error sending image: {e}")

# === CONVERSATION HANDLER FUNCTIONS for user setup ===
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "follow_verify":
        context.user_data['followed'] = True
        context.user_data['verified_at'] = datetime.now().isoformat()
        await query.edit_message_text("✅ *Verification Successful!*\n\nThank you!", parse_mode='Markdown')
        keyboard = [[InlineKeyboardButton("Yes, I am 18+", callback_data="age_yes")], [InlineKeyboardButton("No, I am not", callback_data="age_no")]]
        await query.message.reply_text("To continue, please confirm that you are 18 years or older.", reply_markup=InlineKeyboardMarkup(keyboard))
        return AGE_VERIFY

async def get_age_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "age_yes":
        context.user_data['is_18_plus'] = True
        await query.edit_message_text("Great! What should I call you? Please tell me your name. 😊")
        return GET_NAME
    else:
        await query.edit_message_text("Sorry, you must be 18 or older to use this bot. 😔")
        return ConversationHandler.END

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.message.text
    context.user_data['name'] = user_name
    await update.message.reply_text(f"Nice to meet you, {user_name}! 🥰\n\nNow, please tell me your date of birth in DD-MM-YYYY format (e.g., 25-12-2002). I'll wish you on your birthday!")
    return GET_DOB

async def get_dob(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_dob_str = update.message.text
    try:
        dob = datetime.strptime(user_dob_str, "%d-%m-%Y").date()
        context.user_data['dob'] = dob
        context.user_data['setup_complete'] = True # সেটআপ সম্পূর্ণ
        
        await update.message.reply_text("Thank you for sharing! I've saved your details. ❤️")
        
        languages = [[key] for key in language_options.keys()]
        await update.message.reply_text("Now, please select your language to start chatting:", reply_markup=ReplyKeyboardMarkup(languages, one_time_keyboard=True, resize_keyboard=True))
        
        await send_random_image(update.message.chat_id, context)
        return ConversationHandler.END
    except ValueError:
        await update.message.reply_text("Oops! That doesn't look like the right format. Please use DD-MM-YYYY format (e.g., 25-12-2002).")
        return GET_DOB

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("The setup process has been cancelled. Type /start to try again.")
    return ConversationHandler.END

# === BIRTHDAY WISH SCHEDULER ===
async def check_birthdays(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()
    bot = context.bot
    all_user_data = context.application.user_data
    
    for user_id, user_data in all_user_data.items():
        if user_data.get('dob') and user_data.get('name'):
            dob = user_data['dob']
            if dob.month == today.month and dob.day == today.day:
                name = user_data['name']
                message = f"🎉 Happy Birthday, {name}! 🎉\n\nWishing you a day full of love and laughter. Have a wonderful day! ❤️"
                try:
                    await bot.send_message(chat_id=user_id, text=message)
                    await send_random_image(user_id, context)
                except Exception as e:
                    logger.error(f"Failed to send birthday wish to {user_id}: {e}")

# === MAIN FUNCTION ===
def main() -> None:
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).persistence(persistence).build()

    # জন্মদিনের Job সেট করা (প্রতিদিন UTC সময় সকাল ৪টায় চলবে)
    job_queue = application.job_queue
    job_queue.run_daily(check_birthdays, time=time(hour=4, minute=0, second=0))

    # ব্যবহারকারীর তথ্য সংগ্রহের জন্য Conversation Handler
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_callback, pattern='^follow_verify$')],
        states={
            AGE_VERIFY: [CallbackQueryHandler(get_age_response, pattern='^age_yes$|^age_no$')],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_dob)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        persistent=True,
        name="user_setup_conversation"
    )

    # হ্যান্ডলারগুলো যোগ করা
    application.add_handler(CommandHandler("start", start))
    application.add_handler(conv_handler)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Run the bot with webhook
    application.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
