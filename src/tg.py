from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackContext

from nalunch import NalunchAccount


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
                balances = {}

                for acc in self.accounts:
                    balances[acc.creds.name] = acc.get_balance()

                message = "\n".join([f"{key}: {value}₽" for key, value in balances.items()])
                await update.message.reply_text(message)
            except Exception as e:
                print("error: ", e)
                await update.message.reply_text(f"Exception: {e}")

        return wrapper

    def run(self):
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("nalunch_balances", self.create_balances_handler()))
        app.run_polling()
