import io
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
from qreader import QReader
import cv2
import numpy as np

from nalunch import NalunchAccount


qreader = QReader()

class TgBot:
    token: str
    accounts: list[NalunchAccount]
    chat_ids: set[int]

    def __init__(self, token: str, chat_ids: set[int], accounts: list[NalunchAccount]):
        self.token = token
        self.accounts = accounts
        self.chat_ids = chat_ids

    def create_balances_handler(self):
        async def wrapper(update: Update, context: CallbackContext):
            if context._chat_id not in self.chat_ids:
                await update.message.reply_text(f"Unknown chat id: {context._chat_id}!")
                return

            try:
                print("fetching balances...")
                msg = await update.message.reply_text("Loading balances...")
                balances = {}

                for acc in self.accounts:
                    balances[acc.creds.name] = acc.get_balance()

                message = "\n".join(
                    [f"{key}: {value}₽" for key, value in balances.items()]
                )

                await msg.edit_text(message)
            except Exception as e:
                print("error: ", e)
                await msg.edit_text(f"Exception: {e}")

        return wrapper

    def create_pay_handler(self):
        async def start_pay(update: Update, context: CallbackContext):
            keyboard = [
                [InlineKeyboardButton(acc.creds.name, callback_data=acc.creds.name)]
                for acc in self.accounts
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Choose account to pay from:", reply_markup=reply_markup
            )

        async def button_callback(update: Update, context: CallbackContext):
            query = update.callback_query
            await query.answer()
            context.user_data["selected_account"] = query.data
            await query.edit_message_text(
                text=f"Selected account: {query.data}\nReply with a QR code photo for paying."
            )

        async def photo_handler(update: Update, context: CallbackContext):
            selected_account_name = context.user_data['selected_account']
            selected_account = next((acc for acc in self.accounts if acc.creds.name == selected_account_name), None)
            if selected_account is None:
                await update.message.reply_text(f"Unknown account: {selected_account_name}!")
                return

            msg_text = "Reading QR code..."
            msg = await update.message.reply_text(msg_text)

            image_file = await update.message.photo[-1].get_file()
            image_stream = io.BytesIO()

            await image_file.download_to_memory(image_stream)
            image_stream.seek(0)

            image = cv2.imdecode(np.frombuffer(image_stream.read(), np.uint8), 1)
            image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            decoded_text = qreader.detect_and_decode(image=image)
            path = decoded_text[0]

            msg_text += " DONE\nPerforming payment..."
            await msg.edit_text(msg_text)

            try:
                price = selected_account.pay(path)
                await msg.edit_text(f"Payment successful! Spent {price}₽.")
            except Exception as e:
                print("error: ", e)
                await msg.edit_text(f"Exception: {e}")

        return start_pay, button_callback, photo_handler

    def run(self):
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(
            CommandHandler("nalunch_balances", self.create_balances_handler())
        )

        start_pay, button_callback, photo_handler = self.create_pay_handler()
        app.add_handler(CommandHandler("nalunch_pay", start_pay))
        app.add_handler(CallbackQueryHandler(button_callback))
        app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

        app.run_polling()
