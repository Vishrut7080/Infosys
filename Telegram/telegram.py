from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters
import threading

def start_telegram_bot(token, process_command):

    app = ApplicationBuilder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("Telegram Assistant Connected.")

    async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_text = update.message.text.lower().strip()

        try:
            response = process_command(user_text)
        except Exception as e:
            response = f"[System]: Error - {str(e)}"

        await update.message.reply_text(response)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Telegram Bot Running...")
    app.run_polling()


def start_telegram_in_thread(token, process_command):
    thread = threading.Thread(
        target=start_telegram_bot,
        args=(token, process_command),
        daemon=True
    )
    thread.start()
    return thread