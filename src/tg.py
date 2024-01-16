import asyncio
from datetime import datetime, timedelta
import io
import uuid
from typing import Callable
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Update
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
import zxingcpp


from nalunch import NalunchAccount, VendingItemToBuy
from config import KnownVendingDevice


qreader = QReader()


class VendingProductsCache:
    account: NalunchAccount
    cache: dict
    cache_time: dict
    lock: asyncio.Lock

    def __init__(self, account_to_use: NalunchAccount):
        self.account = account_to_use
        self.cache = {}
        self.cache_time = {}
        self.lock = asyncio.Lock()

    def load_device_products(self, device_id: str):
        items_list = self.account.get_vending_products(device_id)
        self.cache[device_id] = {}
        for item in items_list:
            self.cache[device_id][item["id"]] = item
        self.cache_time[device_id] = datetime.now()

    async def get_vending_products(self, device_id: str):
        async with self.lock:
            if device_id not in self.cache_time or (datetime.now() - self.cache_time[device_id] > timedelta(hours=1)):
                self.load_device_products(device_id)

            return self.cache[device_id]


class MediaGroupProcessor:
    id: str
    wait_time: timedelta
    media: list
    time_cutoff: datetime
    callback: Callable
    started: bool
    lock: asyncio.Lock

    def __init__(self, id: str, wait_time: timedelta = timedelta(milliseconds=500)):
        self.id = id
        self.media = []
        self.started = False
        self.lock = asyncio.Lock()
        self.wait_time = wait_time

    async def start(self):
        while True:
            await asyncio.sleep(0.1)
            async with self.lock:
                if self.time_cutoff <= datetime.now():
                    if self.callback:
                        await self.callback(self.id, self.media)
                    return

    async def add(self, media, callback):
        async with self.lock:
            self.time_cutoff = datetime.now() + self.wait_time
            self.media.append(media)
            self.callback = callback
            if not self.started:
                self.started = True
                asyncio.create_task(self.start())


class NalunchTelegramBot:
    token: str
    accounts: list[NalunchAccount]
    known_vending_devices: list[KnownVendingDevice]
    chat_ids: set[int]

    vending_products: VendingProductsCache
    media_groups: dict[str, MediaGroupProcessor]
    lock: asyncio.Lock

    def __init__(
        self,
        token: str,
        chat_ids: set[int],
        accounts: list[NalunchAccount],
        known_vending_devices: list[KnownVendingDevice],
    ):
        self.token = token
        self.accounts = accounts
        self.chat_ids = chat_ids
        self.known_vending_devices = known_vending_devices
        self.media_groups = {}
        self.vending_products = VendingProductsCache(accounts[0])
        self.lock = asyncio.Lock()

    def acc_by_name(self, name: str):
        selected_account = next(
            (acc for acc in self.accounts if acc.creds.name == name),
            None,
        )
        if selected_account is None:
            raise Exception("No such account")
        return selected_account

    def vending_by_id(self, id: str):
        selected_vending = next(
            (device for device in self.known_vending_devices if str(device.id) == id),
            None,
        )
        if selected_vending is None:
            raise Exception("No such known vending device id")
        return selected_vending

    def balances_handler(self):
        async def wrapper(update: Update, context: CallbackContext):
            if context._chat_id not in self.chat_ids:
                await update.message.reply_text(f"Unknown chat id: {context._chat_id}!")
                return

            try:
                msg = await update.message.reply_text("Loading balances...")
                balances = {}

                for acc in self.accounts:
                    balances[acc.creds.name] = acc.get_balance()

                message = "\n".join(
                    [f"<b>{key}</b>: <b>{value}₽</b>" for key, value in balances.items()]
                )

                await msg.edit_text(message, parse_mode="HTML")
            except Exception as e:
                print("error: ", e)
                await msg.edit_text(f"Exception: {e}")

        return wrapper

    async def make_account_chooser(self, update: Update, context: CallbackContext):
        keyboard = [
            [InlineKeyboardButton(acc.creds.name, callback_data=acc.creds.name)]
            for acc in self.accounts
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Choose account to pay from:", reply_markup=reply_markup
        )
        context.user_data["awaiting_account_choose"] = True

    def pay_qr_handler(self):
        async def wrapper(update: Update, context: CallbackContext):
            context.user_data.clear()
            context.user_data["pay_qr_handler"] = True
            await self.make_account_chooser(update, context)

        return wrapper

    def pay_vending_handler(self):
        async def wrapper(update: Update, context: CallbackContext):
            context.user_data.clear()
            context.user_data["pay_vending_handler"] = True
            await self.make_account_chooser(update, context)

        return wrapper

    def callback_query_handler(self):
        async def wrapper(update: Update, context: CallbackContext):
            query = update.callback_query
            await query.answer()

            if context.user_data.get("awaiting_account_choose", False):
                context.user_data["awaiting_account_choose"] = False
                context.user_data["selected_account"] = query.data

                text = f"Selected account: <b>{query.data}</b>\n"
                reply_markup = None
                if context.user_data.get("pay_qr_handler", False):
                    text += "Reply with a QR code photo for paying."
                    context.user_data["awaiting_qr_bill"] = True
                elif context.user_data.get("pay_vending_handler", False):
                    text += "Choose vending device:"
                    keyboard = [
                        [
                            InlineKeyboardButton(
                                vending.name, callback_data=str(vending.id)
                            )
                        ]
                        for vending in self.known_vending_devices
                    ]
                    keyboard.append(
                        [InlineKeyboardButton("Other (scan QR code)", callback_data="0")]
                    )
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    context.user_data["awaiting_vending_choose"] = True

                await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")
            elif context.user_data.get("awaiting_vending_choose", False):
                selected_account = context.user_data["selected_account"]
                selected_device_id = query.data

                text = f"Selected account: <b>{selected_account}</b>\n"

                if query.data == "0":
                    text += "Reply with vending device QR code."
                    context.user_data["awaiting_vending_qr"] = True
                else:
                    context.user_data["selected_device_id"] = selected_device_id
                    selected_vending = self.vending_by_id(selected_device_id)
                    text += f"Selected vending device: <b>{selected_vending.name}</b>\nReply with barcodes photos for paying."
                    context.user_data["awaiting_vending_barcodes"] = True
                    context.user_data["parsed_barcodes"] = []
                await query.edit_message_text(text=text, parse_mode="HTML")
                context.user_data["awaiting_vending_choose"] = False
            elif context.user_data.get("awaiting_vending_pay_confirmation", False):
                context.user_data["awaiting_vending_pay_confirmation"] = False
                if query.data == "yes":
                    await query.edit_message_text("Performing payment...")
                    try:
                        selected_account = self.acc_by_name(
                            context.user_data["selected_account"]
                        )
                        items_to_buy = [VendingItemToBuy(id=id, count=count) for id, count in context.user_data["items_to_buy"].items()]
                        device_id = context.user_data["selected_device_id"]
                        price = selected_account.pay_vending(device_id, items_to_buy)
                        await query.edit_message_text(f"Vending payment successful! Spent <b>{price}₽</b>.", parse_mode="HTML")
                    except Exception as e:
                        print("error: ", e)
                        await query.edit_message_text(f"Exception: {e}")
                elif query.data == "no":
                    await query.edit_message_text("Payment was cancelled.")
                else:
                    context.user_data["awaiting_vending_barcodes"] = True
                    await query.edit_message_text("Append one or more photos of barcodes.")
            else:
                await query.edit_message_text(text="Unknown operation")

        return wrapper

    async def parse_qr_code(self, photo):
        image_file = await photo.get_file()
        image_stream = io.BytesIO()

        await image_file.download_to_memory(image_stream)
        image_stream.seek(0)

        image = cv2.imdecode(np.frombuffer(image_stream.read(), np.uint8), 1)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

        decoded_text = qreader.detect_and_decode(image=image)
        return decoded_text[0]

    def photo_handler(self):
        async def wrapper(update: Update, context: CallbackContext):
            if context.user_data.get("awaiting_qr_bill", False):
                msg = await update.message.reply_text("Reading QR code...")
                path = await self.parse_qr_code(update.message.photo[-1])

                await msg.edit_text("Performing payment...")

                try:
                    selected_account = self.acc_by_name(
                        context.user_data["selected_account"]
                    )
                    price = selected_account.pay(path)
                    await msg.edit_text(f"Payment successful! Spent <b>{price}₽</b>.", parse_mode="HTML")
                    context.user_data["awaiting_qr_bill"] = False
                except Exception as e:
                    print("error: ", e)
                    await msg.edit_text(f"Exception: {e}")
            elif context.user_data.get("awaiting_vending_qr", False):
                msg = await update.message.reply_text("Reading QR code...")

                device_id = await self.parse_qr_code(update.message.photo[-1])

                context.user_data["selected_device_id"] = device_id

                await msg.edit_text("Getting vending device info...")

                try:
                    selected_account = self.acc_by_name(
                        context.user_data["selected_account"]
                    )
                    vending_name = selected_account.get_vending_name(device_id)
                    await msg.edit_text(
                        f"Selected account: <b>{context.user_data['selected_account']}</b>\n"
                        f"Selected vending: <b>{vending_name}</b>\n"
                        "Reply with barcodes photos for paying."
                    )
                    context.user_data["awaiting_vending_qr"] = False
                    context.user_data["awaiting_vending_barcodes"] = True
                except Exception as e:
                    print("error: ", e)
                    await msg.edit_text(f"Exception: {e}", parse_mode='HTML')
            elif context.user_data.get("awaiting_vending_barcodes", False):
                media_group_id = update.message.media_group_id or uuid.uuid4()
                async with self.lock:
                    if media_group_id not in self.media_groups:
                        self.media_groups[media_group_id] = MediaGroupProcessor(media_group_id)

                await self.media_groups[media_group_id].add(update.message.photo[-1], self.media_group_callback(update, context))

        return wrapper

    def media_group_callback(self, update: Update, context: CallbackContext):
        async def wrapper(media_group_id: str, photos):
            try:
                del self.media_groups[media_group_id]
                msg = await update.message.reply_text(f"Trying to parse barcodes from {len(photos)} photos...")
                parsed_barcodes = []
                not_parsed = []

                for photo in photos:
                    image_file = await photo.get_file()
                    image_stream = io.BytesIO()

                    await image_file.download_to_memory(image_stream)
                    image_stream.seek(0)

                    image = cv2.imdecode(np.frombuffer(image_stream.read(), np.uint8), 1)
                    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

                    results = zxingcpp.read_barcodes(image)
                    if len(results) == 0:
                        not_parsed.append(photo)
                        continue

                    parsed_barcodes.append(results[0].text)

                context.user_data["parsed_barcodes"] += parsed_barcodes

                if len(not_parsed) > 0:
                    media_group = [InputMediaPhoto(photo) for photo in not_parsed]
                    await msg.edit_text("Unable to parse these barcodes, send new photos of them again (only them).")
                    await update.message.reply_media_group(media=media_group)
                else:
                    context.user_data["awaiting_vending_barcodes"] = False
                    await msg.edit_text("All photos have been parsed! Collecting confirmation info...")

                    vending_items = await self.vending_products.get_vending_products(context.user_data["selected_device_id"])
                    items_counts = {}
                    for item_id in context.user_data["parsed_barcodes"]:
                        if item_id not in vending_items:
                            await msg.edit_text(f"Hmm, there is no item with id {item_id} in vending device product list, probably an error occurred while parsing, restart all buying process please..")
                            return
                        if item_id not in items_counts:
                            items_counts[item_id] = 1
                        else:
                            items_counts[item_id] += 1
                    
                    sum = 0
                    msg_text = f"Account <b>{context.user_data['selected_account']}</b> is about to buy:\n\n"
                    for item_id, count in items_counts.items():
                        msg_text += f'{count}x "{vending_items[item_id]["name"]}" - <b>{int(vending_items[item_id]["price"]*count)}₽</b>\n'
                        sum += int(vending_items[item_id]["price"]*count)
                    msg_text += f"\nTotal price: <b>{sum}₽</b>\n\nDo you confirm?"

                    reply_markup = InlineKeyboardMarkup([
                        [InlineKeyboardButton("Yes", callback_data="yes")],
                        [InlineKeyboardButton("Cancel payment", callback_data="no")],
                        [InlineKeyboardButton("Add more items", callback_data="add")],
                    ])
                    context.user_data["awaiting_vending_pay_confirmation"] = True
                    context.user_data["items_to_buy"] = items_counts
                    await msg.edit_text(msg_text, reply_markup=reply_markup, parse_mode="HTML")

            except Exception as e:
                print(e)
                await update.message.reply_text("An exception while media group processing: " + str(e))

        return wrapper

    def run(self):
        app = ApplicationBuilder().token(self.token).build()
        app.add_handler(CommandHandler("nalunch_balances", self.balances_handler()))
        app.add_handler(CommandHandler("nalunch_pay_vending", self.pay_vending_handler()))
        app.add_handler(CommandHandler("nalunch_pay_qr", self.pay_qr_handler()))
        app.add_handler(CallbackQueryHandler(self.callback_query_handler()))
        app.add_handler(MessageHandler(filters.PHOTO, self.photo_handler()))
        app.run_polling()
