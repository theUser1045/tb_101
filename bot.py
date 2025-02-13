import requests
import pymongo
import re
import logging
import threading
import time
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackContext, filters
from get_json import get_json_data
import os
lst_data = get_json_data()

links_data = lst_data[0]

token = lst_data[1]

MONGO_URI = token[1]
bot_token = token[0]
youtube_token = token[3]
api_url = token[2]

# Connect to MongoDB
client = pymongo.MongoClient(MONGO_URI)
db = client["telegram_db"]
collection = db["clients_id"]
subscribed_collection = db["subscribed_clients"]
logs_collection = db["logs_data"]  # Collection to store logs


# Setup logging
log_file = "bot_logs.log"
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def log_message(message):
    """Writes a message to both stdout and log file."""
    print(message)
    logging.info(message)


def save_logs_to_db():
    """Reads only new logs from the file and saves them to MongoDB every 5 minutes."""
    last_position = 0  # Track last read position

    while True:
        try:
            # Ensure log file exists before reading
            if not os.path.exists(log_file):
                open(log_file, "w").close()  # Create empty log file
                last_position = 0  # No logs yet, so start from 0

            with open(log_file, "r") as file:
                file.seek(last_position)  # Move to last saved position
                logs = file.readlines()
                last_position = file.tell()  # Update position to the end

            if logs:
                logs_collection.insert_one({"timestamp": time.time(), "logs": logs})

                # Clear the log file after saving
                open(log_file, "w").close()
                last_position = 0  # Reset position after clearing logs

        except Exception as e:
            logging.error(f"Error saving logs to MongoDB: {e}")

        time.sleep(300)  # Sleep for 5 minutes


# Start log saving thread
log_thread = threading.Thread(target=save_logs_to_db, daemon=True)
log_thread.start()

def get_serial_num_obj(serial_num):
    for obj in links_data:
        if int(serial_num) == int(obj['serial_num']):
            return obj
    
    return None


def get_youtube_channel_id(handle):
    """Fetches the YouTube channel ID given a YouTube handle."""
    url = f"https://www.youtube.com/{handle}"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            match = re.search(r'<meta itemprop="identifier" content="(UC[^"]+)">', response.text)
            if match:
                return match.group(1)
    except requests.RequestException as e:
        print(f"Request failed: {e}")
    
    return None

def validate_youtube_channel(youtube_input, youtube_token):
    """Validate YouTube handle or channel ID using regex and API."""
    blocked_handles = {"@TimeForEpics", "TimeForEpics_01", "TimeForEpics_02"}
    blocked_ids = {"UC62Pu3nGGtZ2DxhYI-mGDIQ", "UCykzEdG_I9Km7BeahqCgvqg", "UCVhNrRze38iLpeWO0OMb46A"}

    if youtube_input in blocked_handles or youtube_input in blocked_ids:
        return None, None  # Block these specific handles and IDs

    channel_id, channel_handle = None, None

    if youtube_input.startswith("@"):
        # Convert handle to channel ID
        channel_id = get_youtube_channel_id(youtube_input)
        if channel_id:
            channel_handle = youtube_input
            return channel_id, channel_handle
    elif youtube_input.startswith("UC") and len(youtube_input) > 10:
        # Assume it's a valid YouTube channel ID and validate via API
        channel_url = f"https://www.googleapis.com/youtube/v3/channels?part=id&id={youtube_input}&key={youtube_token}"
        response = requests.get(channel_url, timeout=5)
        data = response.json()
        if "items" in data and len(data["items"]) > 0:
            return youtube_input, None  # Valid channel ID, no handle

    return None, None  # Return None for both if validation fails

async def start(update: Update, context: CallbackContext):
    """Handles the /start command and checks user subscription status."""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username or update.message.from_user.first_name

    user_in_clients = collection.find_one({"user_id": user_id})
    user_in_subscribed = subscribed_collection.find_one({"user_id": user_id})

    if user_in_clients:
        if user_in_subscribed:
            await update.message.reply_text(
                "✅ Welcome back! Please send a serial number to get the PDF link.\n\n"
                "📢 *Don't know the Rdf Serial Number?* Check our Telegram channel: [TimeForEpics](https://t.me/TimeForEpics)",
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        else:
            collection.delete_one({"user_id": user_id})  # Remove if not subscribed
            await update.message.reply_text(
                "📢 Welcome! To use this bot, please subscribe to our YouTube channel: "
                "[TimeForEpics](https://www.youtube.com/@TimeForEpics_01?sub_confirmation=1)\n\n"
                "✅ After subscribing, send your YouTube **channel ID** or **handle** here.\n\n "
                "📌 **Example Formats:** \n\n"
                "👉 Sample Handle: `@YourChannelHandle`\n\n"
                "👉 Sample Channel ID: `UC123abcXYZ456`"
            
            )
    else:
        await update.message.reply_text(
            "📢 Welcome! To use this bot, please subscribe to our YouTube channel: "
                "[TimeForEpics](https://www.youtube.com/@TimeForEpics_01?sub_confirmation=1)\n\n"
                "✅ After subscribing, send your YouTube **channel ID** or **handle** here.\n\n "
                "📌 **Example Formats:** \n\n"
                "👉 Sample Handle: `@YourChannelHandle`\n\n"
                "👉 Sample Channel ID: `UC123abcXYZ456`"
            
        )

async def register(update: Update, context: CallbackContext):
    """Handles user input and distinguishes between YouTube handles and serial numbers."""
    user_id = update.message.from_user.id
    user_name = update.message.from_user.username or update.message.from_user.first_name
    user_input = update.message.text.strip()

    # Check if input is a serial number (numeric)
    if user_input.isdigit():
        await process_serial_number(update, user_input)
        return

    # Otherwise, assume YouTube input
    print(f"🔍 Validating YouTube input: {user_input} for user {user_id} ({user_name})")
    channel_id, channel_handle = validate_youtube_channel(user_input, youtube_token)

    if channel_id or channel_handle:
        print(f"✅ YouTube channel valid. Registering user {user_id} ({user_name}) with Channel ID: {channel_id}, Handle: {channel_handle}")
        collection.insert_one({"user_id": user_id, "user_name": user_name})
        subscribed_collection.insert_one({
            "user_id": user_id, 
            "user_name": user_name, 
            "channel_id": channel_id, 
            "channel_handle": channel_handle
        })
        await update.message.reply_text("✅ Registration successful! Now send /start.")
    else:
        print(f"❌ Invalid YouTube input provided by user {user_id} ({user_name})")
        await update.message.reply_text("❌ Invalid YouTube handle or channel ID. Please try again.")


async def process_serial_number(update: Update, serial_number: str):
    """Fetches the PDF link using the serial number from local JSON data."""

    # Validate serial_number: Check if it's a number
    if not serial_number.isdigit():
        print(f"❌ Invalid Serial Number: {serial_number} (Not a number)")  # Debug
        await update.message.reply_text("❌ Error: Invalid serial number. Please enter a valid number.")
        return

    # Get serial number object from JSON
    serial_obj = get_serial_num_obj(serial_number)
    if not serial_obj:
        print(f"❌ No Data Found for Serial Number: {serial_number}")  # Debug
        await update.message.reply_text("❌ Error: No data found for the provided serial number.")
        return

    print(f"✅ Found Data for Serial Number: {serial_number}")  # Debug

    # Construct the response message
    message = (
        f"✅  *File Name:* {serial_obj['file_name']}\n\n"
        f"🔗 *Download Link:* [Click Here]({serial_obj['link']})\n\n"
        f"📌 *Serial Number:* {serial_obj['serial_num']}"
    )

    # Send the response message
    await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)




# Set up the bot
app = Application.builder().token(bot_token).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, register))

print("🤖 Bot is running...")
app.run_polling()