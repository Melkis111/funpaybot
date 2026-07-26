import asyncio
import threading
import time
import logging
import json
import requests
from bs4 import BeautifulSoup
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

GOLDEN_KEY = ""
TELEGRAM_TOKEN = ""
ALLOWED_USER_IDS = [ , ]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BASE_URL = "https://funpay.com"
reply_map = {}  # {telegram_msg_id: chat_id}


class FunPayAPI:
    def __init__(self, golden_key: str):
        self.session = requests.Session()
        self.session.cookies.set("golden_key", golden_key, domain="funpay.com")
        self.user_id = None
        self.username = None
        self.csrf_token = None

    def init_account(self):
        resp = self.session.get(BASE_URL, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        username_el = soup.find("div", {"class": "user-link-name"})
        if not username_el:
            raise Exception("Golden key невалиден.")
        self.username = username_el.text
        body = soup.find("body")
        app_data = json.loads(body.get("data-app-data", "{}"))
        self.user_id = app_data.get("userId")
        self.csrf_token = app_data.get("csrf-token")
        logger.info(f"Подключено: {self.username} (ID: {self.user_id})")

    def send_message(self, chat_id: int, text: str):
        request = {
            "action": "chat_message",
            "data": {"node": chat_id, "last_message": -1, "content": f"\u206e{text}"}
        }
        objects = [{
            "type": "chat_node",
            "id": chat_id,
            "tag": "00000000",
            "data": {"node": chat_id, "last_message": -1, "content": ""}
        }]
        payload = {
            "objects": json.dumps(objects),
            "request": json.dumps(request),
            "csrf_token": self.csrf_token
        }
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        resp = self.session.post(f"{BASE_URL}/runner/", headers=headers, data=payload, timeout=10)
        return resp.json()

    def get_updates(self, last_msg_tag, last_order_tag):
        payload = {
            "objects": json.dumps([
                {"type": "orders_counters", "id": self.user_id, "tag": last_order_tag, "data": False},
                {"type": "chat_bookmarks", "id": self.user_id, "tag": last_msg_tag, "data": False}
            ]),
            "request": False,
            "csrf_token": self.csrf_token
        }
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        resp = self.session.post(f"{BASE_URL}/runner/", headers=headers, data=payload, timeout=10)
        return resp.json()

    def parse_chat_bookmarks(self, obj):
        data = obj.get("data", {})
        html = data.get("html", "")
        soup = BeautifulSoup(html, "html.parser")
        chats = []
        for a in soup.find_all("a", {"class": "contact-item"}):
            chat_id = a.get("data-id")
            msg_id = a.get("data-node-msg")
            name_el = a.find("div", {"class": "media-user-name"})
            msg_el = a.find("div", {"class": "contact-item-message"})
            unread = "unread" in (a.get("class") or [])
            if chat_id:
                chats.append({
                    "id": int(chat_id),
                    "msg_id": int(msg_id) if msg_id else 0,
                    "name": name_el.text.strip() if name_el else "?",
                    "last_msg": msg_el.text.strip() if msg_el else "",
                    "unread": unread
                })
        return chats

    def get_chat_info(self, chat_id):
        resp = self.session.get(f"{BASE_URL}/chat/?node={chat_id}", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        listing = ""
        panel = soup.find("div", {"class": "chat-panel-mobile"})
        if panel:
            listing = panel.get_text(strip=True)
        messages = []
        last_author = ""
        for div in soup.find_all("div", {"class": "chat-msg-item"}):
            author_el = div.find("a", {"class": "chat-msg-author-link"})
            label_el = div.find("span", {"class": "chat-msg-author-label"})
            text_el = div.find("div", {"class": "chat-msg-text"})
            date_el = div.find("div", {"class": "chat-msg-date"})
            if text_el:
                author = author_el.text.strip() if author_el else ""
                if not author and not label_el:
                    author = last_author
                if author:
                    last_author = author
                messages.append({
                    "author": author,
                    "label": label_el.text.strip() if label_el else "",
                    "text": text_el.text.strip(),
                    "date": date_el.text.strip() if date_el else ""
                })
        return {"listing": listing, "messages": messages}

    def get_orders(self):
        resp = self.session.get(f"{BASE_URL}/orders/trade", timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        orders = []
        for a in soup.find_all("a", {"class": "tc-item"}):
            order_el = a.find("div", {"class": "tc-order"})
            desc_el = a.find("div", {"class": "order-desc"})
            status_el = a.find("div", {"class": "tc-status"})
            price_el = a.find("div", {"class": "tc-price"})
            buyer_el = a.find("span", {"class": "pseudo-a"})
            if order_el:
                order_id = order_el.text.strip().replace("#", "")
                orders.append({
                    "id": order_id,
                    "description": desc_el.get_text(strip=True)[:120] if desc_el else "",
                    "status": status_el.text.strip() if status_el else "",
                    "price": price_el.get_text(strip=True) if price_el else "",
                    "buyer": buyer_el.text.strip() if buyer_el else ""
                })
        return orders

    def get_chats_list(self):
        payload = {
            "objects": json.dumps([
                {"type": "orders_counters", "id": self.user_id, "tag": "0", "data": False},
                {"type": "chat_bookmarks", "id": self.user_id, "tag": "0", "data": False}
            ]),
            "request": False,
            "csrf_token": self.csrf_token
        }
        headers = {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
            "x-requested-with": "XMLHttpRequest"
        }
        resp = self.session.post(f"{BASE_URL}/runner/", headers=headers, data=payload, timeout=10)
        data = resp.json()
        for obj in data.get("objects", []):
            if obj["type"] == "chat_bookmarks":
                return self.parse_chat_bookmarks(obj)
        return []


fp = FunPayAPI(GOLDEN_KEY)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        await update.message.reply_text("Нет доступа.")
        return
    await update.message.reply_text(
        "✅ Доступ открыт!\n\n"
        "Команды:\n"
        "/chats - список чатов\n"
        "/reply ID_ЧАТА текст - ответить в чат\n\n"
        "Или просто ответь на сообщение бота — оно уйдёт в FunPay."
    )


async def cmd_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        return
    try:
        chats = fp.get_chats_list()
        if not chats:
            await update.message.reply_text("Чатов нет.")
            return
        lines = []
        for c in chats[:20]:
            status = "🔵" if c["unread"] else "⚪"
            lines.append(f"{status} <b>{c['name']}</b> — ID: <code>{c['id']}</code>\n📝 {c['last_msg'][:60]}")
        text = "💬 <b>Чаты:</b>\n\n" + "\n\n".join(lines)
        await update.message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def cmd_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        return
    if not context.args or len(context.args) < 2:
        await update.message.reply_text("Формат: /reply ID_ЧАТА текст\n\nID чата смотри в /chats")
        return
    try:
        chat_id = int(context.args[0])
        text = " ".join(context.args[1:])
        fp.send_message(chat_id, text)
        await update.message.reply_text(f"✅ Отправлено в чат {chat_id}:\n{text}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ALLOWED_USER_IDS:
        return
    if not update.message or not update.message.reply_to_message:
        return
    replied_msg_id = update.message.reply_to_message.message_id
    chat_id = reply_map.get(replied_msg_id)
    if not chat_id:
        return
    text = update.message.text
    try:
        fp.send_message(chat_id, text)
        await update.message.reply_text(f"✅ Отправлено в чат {chat_id}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")


telegram_app = None


async def send_telegram(text: str, chat_id_for_reply: int = None):
    global telegram_app
    if not telegram_app:
        return
    for user_id in ALLOWED_USER_IDS:
        try:
            msg = await telegram_app.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML"
            )
            if chat_id_for_reply:
                reply_map[msg.message_id] = chat_id_for_reply
        except Exception as e:
            logger.error(f"Telegram (user {user_id}): {e}")


def run_funpay_monitor():
    logger.info("Запуск мониторинга FunPay...")
    fp.init_account()

    last_msg_tag = ""
    last_order_tag = ""
    known_msg_ids = {}
    known_orders = {}

    data = fp.get_updates(last_msg_tag, last_order_tag)
    for obj in data.get("objects", []):
        if obj["type"] == "chat_bookmarks":
            last_msg_tag = obj.get("tag", "")
            chats = fp.parse_chat_bookmarks(obj)
            for c in chats:
                known_msg_ids[c["id"]] = c["msg_id"]
                logger.info(f"  Чат: {c['name']} (ID: {c['id']})")
        elif obj["type"] == "orders_counters":
            last_order_tag = obj.get("tag", "")

    orders = fp.get_orders()
    for o in orders:
        known_orders[o["id"]] = o
        logger.info(f"  Заказ: {o['id']} | {o['status']} | {o['buyer']}")

    for obj in data.get("objects", []):
        if obj["type"] == "chat_bookmarks":
            for c in fp.parse_chat_bookmarks(obj):
                if c["unread"]:
                    asyncio.run_coroutine_threadsafe(
                        send_telegram(f"📩 <b>Непрочитанный чат!</b>\n👤 {c['name']}\n📝 {c['last_msg']}", c["id"]),
                        main_loop
                    )

    logger.info("Ожидаю события...")

    while True:
        try:
            time.sleep(3)
            data = fp.get_updates(last_msg_tag, last_order_tag)

            for obj in data.get("objects", []):
                if obj["type"] == "chat_bookmarks":
                    new_tag = obj.get("tag", "")
                    if new_tag != last_msg_tag:
                        last_msg_tag = new_tag
                        chats = fp.parse_chat_bookmarks(obj)
                        for c in chats:
                            old_msg_id = known_msg_ids.get(c["id"], 0)
                            if c["msg_id"] > old_msg_id:
                                known_msg_ids[c["id"]] = c["msg_id"]
                                chat_info = fp.get_chat_info(c["id"])
                                messages = chat_info["messages"]
                                listing = chat_info["listing"]
                                if messages:
                                    last = messages[-1]
                                    if last["author"] == fp.username:
                                        continue
                                    if last["label"] == "автоответ":
                                        continue
                                    if not last["author"] and not last["label"]:
                                        continue
                                    listing_text = f"\n🏷 Товар: {listing}" if listing else ""
                                    if last["label"] == "оповещение":
                                        text = (
                                            f"🔔 <b>Оповещение!</b>\n"
                                            f"💬 Чат: {c['name']}\n"
                                            f"📝 {last['text']}"
                                            f"{listing_text}"
                                        )
                                    else:
                                        text = (
                                            f"📩 <b>Новое сообщение!</b>\n\n"
                                            f"👤 От: {last['author']}\n"
                                            f"💬 Чат: {c['name']}\n"
                                            f"📝 {last['text']}\n"
                                            f"🕐 {last['date']}"
                                            f"{listing_text}"
                                        )
                                    asyncio.run_coroutine_threadsafe(
                                        send_telegram(text, c["id"]),
                                        main_loop
                                    )

                elif obj["type"] == "orders_counters":
                    new_tag = obj.get("tag", "")
                    if new_tag != last_order_tag:
                        last_order_tag = new_tag
                        time.sleep(1)
                        orders = fp.get_orders()
                        for o in orders:
                            if o["id"] not in known_orders:
                                known_orders[o["id"]] = o
                                text = (
                                    f"🛒 <b>Новый заказ!</b>\n\n"
                                    f"📦 ID: {o['id']}\n"
                                    f"👤 {o['buyer']}\n"
                                    f"💰 {o['price']}\n"
                                    f"📝 {o['description']}\n"
                                    f"📊 {o['status']}"
                                )
                                asyncio.run_coroutine_threadsafe(
                                    send_telegram(text),
                                    main_loop
                                )
                            else:
                                old_status = known_orders[o["id"]].get("status", "")
                                if o["status"] != old_status:
                                    known_orders[o["id"]] = o
                                    text = (
                                        f"🔄 <b>Статус заказа!</b>\n\n"
                                        f"📦 {o['id']}\n"
                                        f"👤 {o['buyer']}\n"
                                        f"💰 {o['price']}\n"
                                        f"📊 {old_status} → <b>{o['status']}</b>"
                                    )
                                    asyncio.run_coroutine_threadsafe(
                                        send_telegram(text),
                                        main_loop
                                    )

        except Exception as e:
            logger.error(f"Ошибка: {e}", exc_info=True)
            time.sleep(10)


def main():
    global telegram_app, main_loop

    main_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(main_loop)

    application = Application.builder().token(TELEGRAM_TOKEN).build()
    telegram_app = application

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("chats", cmd_chats))
    application.add_handler(CommandHandler("reply", cmd_reply))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply))

    funpay_thread = threading.Thread(target=run_funpay_monitor, daemon=True)
    funpay_thread.start()

    asyncio.run_coroutine_threadsafe(
        send_telegram("✅ Бот запущен! Напиши /start в Telegram боте."),
        main_loop
    )

    application.run_polling()


if __name__ == "__main__":
    main()
