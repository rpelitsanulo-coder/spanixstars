import asyncio
import html
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {
    8759868224,
    *(
        int(x.strip())
        for x in os.getenv("ADMIN_IDS", "").split(",")
        if x.strip().isdigit()
    ),
}
BOT_NAME = "Razor Stars"
DB_PATH = os.getenv("DB_PATH", str(Path(__file__).resolve().with_name("bot.db")))
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@support")
REVIEWS_URL = os.getenv("REVIEWS_URL", "https://t.me/")

BANK_DETAILS = {
    "private": os.getenv("PRIVATE_DETAILS", "Реквізити Privat24 не налаштовані."),
    "mono": os.getenv("MONO_DETAILS", "Реквізити Mono не налаштовані."),
    "pumb": os.getenv("PUMB_DETAILS", "Реквізити PUMB не налаштовані."),
    "alliance": os.getenv("ALLIANCE_DETAILS", "Реквізити Альянс не налаштовані."),
    "abank": os.getenv("ABANK_DETAILS", "Реквізити А-Банк не налаштовані."),
}

MAIN_EMOJI = {
    "buy_stars": "5848021027782661221",
    "withdraw_stars": "5920281855378068765",
    "buy_gram": "5265151230790884988",
    "nft": "5296437159849376813",
    "sell_stars": "5301176488756788169",
    "profile": "5920108570627544286",
    "calculator": "6035084557378654059",
    "reviews": "5816567393136154162",
    "support": "5300801237464135848",
}

WELCOME_EMOJI = {
    "stars": "5920281855378068765",
    "ton": "5264760470371328402",
    "fire": "5303061717406727152",
}

EMOJI_POOL = [
    "5848021027782661221", "5474311027095000780", "5920281855378068765",
    "5271934564699226262", "5206607081334906820", "5296588050640420683",
    "5296437159849376813", "5326056199215406977", "5429515712198637494",
    "5296727834646036322", "5265151230790884988", "5264760470371328402",
    "5301246586918024418", "6039402906476613311", "5301276827782755360",
    "5474174000458389011", "5303061717406727152", "5440660757194744323",
    "5443038326535759644", "5305522282695768654", "5440539497383087970",
    "5235579174072112613", "5416041192905265756", "5262622667579603340",
    "5296562641613897196", "5296727834646036322", "5848021027782661221",
    "6035084557378654059", "5816567393136154162", "5300801237464135848",
]


def pe(emoji_id: str, fallback: str = "⭐") -> str:
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'


def esc(value) -> str:
    return html.escape(str(value or ""))


def parse_nft_details(raw_text: str):
    text = " ".join(raw_text.split())
    if "|" in text:
        parts = [part.strip() for part in text.split("|", 2)]
        if len(parts) == 3 and parts[0] and parts[1] and parts[2]:
            return parts
        return None

    match = re.fullmatch(r"(.+?)\s+(\d+(?:[.,]\d+)?)\s+(.+)", text)
    if not match:
        return None
    return [match.group(1).strip(), match.group(2).strip(), match.group(3).strip()]


def normalize_reviews_url(raw_value: str):
    value = raw_value.strip()
    if value.startswith("@"):
        username = value[1:].strip()
        return f"https://t.me/{username}" if username else None
    if value.startswith(("t.me/", "telegram.me/")):
        return f"https://{value}"
    if value.startswith(("https://t.me/", "http://t.me/", "https://telegram.me/", "http://telegram.me/")):
        return value
    return None


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


db = sqlite3.connect(DB_PATH)
db.row_factory = sqlite3.Row

db.executescript(
    """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance_stars INTEGER DEFAULT 0,
    bought_stars INTEGER DEFAULT 0,
    bought_ton REAL DEFAULT 0,
    premium_months INTEGER DEFAULT 0,
    spent_uah REAL DEFAULT 0,
    invited INTEGER DEFAULT 0,
    status TEXT DEFAULT 'Новачок',
    registered_at TEXT
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    order_type TEXT NOT NULL,
    quantity TEXT NOT NULL,
    amount REAL NOT NULL,
    payment_method TEXT,
    receipt_file_id TEXT,
    receipt_type TEXT,
    status TEXT DEFAULT 'waiting_payment',
    created_at TEXT NOT NULL,
    admin_note TEXT,
    nft_id INTEGER
);

CREATE TABLE IF NOT EXISTS balance_adjustments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    amount INTEGER NOT NULL,
    balance_before INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nfts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    price REAL NOT NULL,
    emoji TEXT DEFAULT '🎁',
    description TEXT DEFAULT '',
    sticker_file_id TEXT,
    sticker_type TEXT,
    custom_emoji_id TEXT,
    active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS ui_messages (
    user_id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    message_id INTEGER NOT NULL,
    screen_key TEXT
);
""")

def ensure_column(table: str, column: str, definition: str):
    cols = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        db.commit()


ensure_column("orders", "nft_id", "INTEGER")
ensure_column("nfts", "sticker_file_id", "TEXT")
ensure_column("nfts", "sticker_type", "TEXT")
ensure_column("nfts", "custom_emoji_id", "TEXT")
ensure_column("ui_messages", "screen_key", "TEXT")

DEFAULTS = {
    "stars_rate": "0.73",
    "ton_rate": "66.71",
    "min_withdraw": "50",
    "support": SUPPORT_USERNAME,
    "reviews_url": REVIEWS_URL,
}
for method, details in BANK_DETAILS.items():
    DEFAULTS[f"bank_{method}"] = details
for key, value in DEFAULTS.items():
    db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (key, value))
db.commit()


def setting(key):
    row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


def set_setting(key, value):
    db.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))
    db.commit()


def delete_setting(key):
    db.execute("DELETE FROM settings WHERE key=?", (key,))
    db.commit()


def ensure_user(user):
    row = db.execute("SELECT id FROM users WHERE id=?", (user.id,)).fetchone()
    if not row:
        db.execute(
            "INSERT INTO users(id,username,first_name,registered_at) VALUES(?,?,?,?)",
            (user.id, user.username, user.first_name, datetime.now().strftime("%Y-%m-%d")),
        )
    else:
        db.execute(
            "UPDATE users SET username=?, first_name=? WHERE id=?",
            (user.username, user.first_name, user.id),
        )
    db.commit()


def user_row(uid):
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


def find_user_by_identifier(identifier):
    value = identifier.strip()
    if value.startswith("@"):
        value = value[1:]
    if not value:
        return None
    if value.isdigit():
        return user_row(int(value))
    return db.execute(
        "SELECT * FROM users WHERE username=? COLLATE NOCASE",
        (value,),
    ).fetchone()


def create_order(uid, order_type, quantity, amount, nft_id=None):
    cur = db.execute(
        """INSERT INTO orders(user_id,order_type,quantity,amount,status,created_at,nft_id)
           VALUES(?,?,?,?,?,?,?)""",
        (uid, order_type, str(quantity), float(amount), "waiting_payment", now(), nft_id),
    )
    db.commit()
    return cur.lastrowid


def kb_button(text, *, emoji_id=None, style=None, callback_data=None, url=None):
    kwargs = {"text": text}
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = str(emoji_id)
    if style:
        kwargs["style"] = style
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    return InlineKeyboardButton(**kwargs)


def reply_button(text, *, emoji_id=None, style=None):
    kwargs = {"text": text}
    if emoji_id:
        kwargs["icon_custom_emoji_id"] = str(emoji_id)
    if style:
        kwargs["style"] = style
    return KeyboardButton(**kwargs)


def main_menu():
    rows = [
        [
            reply_button("Купити Stars", emoji_id=MAIN_EMOJI["buy_stars"], style="danger"),
            reply_button("Купити TON", emoji_id=MAIN_EMOJI["buy_gram"], style="danger"),
            reply_button("NFT", emoji_id=MAIN_EMOJI["nft"], style="danger"),
        ],
        [
            reply_button("Вивести Stars", emoji_id=MAIN_EMOJI["withdraw_stars"], style="success"),
            reply_button("Продати Stars", emoji_id=MAIN_EMOJI["sell_stars"], style="success"),
            reply_button("Профіль", emoji_id=MAIN_EMOJI["profile"], style="success"),
        ],
        [
            reply_button("Калькулятор", emoji_id=MAIN_EMOJI["calculator"], style="primary"),
            reply_button("Відгуки", emoji_id=MAIN_EMOJI["reviews"], style="primary"),
            reply_button("Підтримка", emoji_id=MAIN_EMOJI["support"], style="primary"),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


ASSET_DIR = Path(os.getenv("ASSET_DIR", "attached_assets"))

SCREEN_IMAGES = {
    "welcome": "0DAC8ABF-4E80-4DAC-9765-68EBFE20BAD1_1790343358458.png",
    "stars": "8F1E5F14-6C85-481A-89C0-CB8DDB51C6E7_1790343358459.png",
    "ton": "CBAC6203-7823-4978-B81E-835F062AFBAE_1790343358459.png",
    "nft": "IMG_0464_1790343358459.jpeg",
    "sell": "IMG_0465_1790343358459.jpeg",
    "support": "IMG_0466_1790343358459.jpeg",
    "withdraw": "IMG_0467_1790343358459.jpeg",
    "calculator": "IMG_0468_1790343358459.jpeg",
    "reviews": "IMG_0469_1790343358459.jpeg",
}


async def replace_screen(
    user_id: int,
    text: str,
    *,
    image=None,
    reply_markup=None,
    screen_key=None,
):
    previous = db.execute(
        "SELECT chat_id, message_id FROM ui_messages WHERE user_id=?",
        (user_id,),
    ).fetchone()
    if previous:
        try:
            await bot.delete_message(
                chat_id=previous["chat_id"],
                message_id=previous["message_id"],
            )
        except Exception:
            pass

    image_name = SCREEN_IMAGES.get(image) if image else None
    image_path = ASSET_DIR / image_name if image_name else None
    if image_path and image_path.is_file():
        sent = await bot.send_photo(
            chat_id=user_id,
            photo=FSInputFile(str(image_path)),
            caption=text,
            reply_markup=reply_markup,
        )
    else:
        sent = await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=reply_markup,
        )
    db.execute(
        "INSERT OR REPLACE INTO ui_messages(user_id,chat_id,message_id,screen_key) VALUES(?,?,?,?)",
        (user_id, user_id, sent.message_id, screen_key),
    )
    db.commit()
    return sent


def cancel_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[reply_button("Скасувати", emoji_id=EMOJI_POOL[3], style="danger")]],
        resize_keyboard=True,
    )


def back_inline(callback_data="back_main"):
    return kb_button("Назад", emoji_id=EMOJI_POOL[1], style="primary", callback_data=callback_data)


def stars_catalog_text(rate=None):
    if rate is None:
        rate = float(setting("stars_rate"))
    return (
        f"{pe(MAIN_EMOJI['buy_stars'], '⭐')} <b>Оберіть кількість Stars</b>\n\n"
        f"💱 Актуальний курс: <b>{rate:g} грн / 1 Star</b>"
    )


def stars_kb():
    b = InlineKeyboardBuilder()
    rate = float(setting("stars_rate"))
    for stars in (50, 100, 500, 1000):
        price = round(stars * rate, 2)
        b.row(kb_button(f"{stars} Stars — {price:g} грн", emoji_id=MAIN_EMOJI["buy_stars"], style="danger", callback_data=f"stars:{stars}"))
    b.row(kb_button("Власна кількість Stars", emoji_id=MAIN_EMOJI["buy_stars"], style="danger", callback_data="stars:custom"))
    b.row(back_inline())
    return b.as_markup()


async def refresh_stars_catalog_screens():
    text = stars_catalog_text()
    markup = stars_kb()
    screens = db.execute(
        "SELECT chat_id, message_id FROM ui_messages WHERE screen_key='stars_catalog'"
    ).fetchall()
    for screen in screens:
        try:
            await bot.edit_message_caption(
                chat_id=screen["chat_id"],
                message_id=screen["message_id"],
                caption=text,
                reply_markup=markup,
            )
        except Exception:
            try:
                await bot.edit_message_text(
                    chat_id=screen["chat_id"],
                    message_id=screen["message_id"],
                    text=text,
                    reply_markup=markup,
                )
            except Exception:
                # A user may have deleted the message or blocked the bot.
                pass


def payment_kb(order_id):
    b = InlineKeyboardBuilder()
    b.row(kb_button("Українська картка", emoji_id=EMOJI_POOL[0], style="danger", callback_data=f"pay:{order_id}:ua"))
    b.row(kb_button("Скасувати замовлення", emoji_id=EMOJI_POOL[3], style="danger", callback_data=f"cancel_order:{order_id}"))
    return b.as_markup()


def bank_kb(order_id):
    b = InlineKeyboardBuilder()
    banks = [
        ("Privat24", "private"),
        ("Mono", "mono"),
        ("PUMB", "pumb"),
        ("Альянс", "alliance"),
        ("А-Банк", "abank"),
    ]
    for name, code in banks:
        b.row(kb_button(name, emoji_id=EMOJI_POOL[3], style="danger", callback_data=f"bank:{order_id}:{code}"))
    b.row(back_inline(f"backpay:{order_id}"))
    b.row(kb_button("Скасувати", emoji_id=EMOJI_POOL[3], style="danger", callback_data=f"cancel_order:{order_id}"))
    return b.as_markup()


def receipt_kb(order_id):
    b = InlineKeyboardBuilder()
    b.row(kb_button("Я оплатив — надіслати квитанцію", emoji_id=EMOJI_POOL[0], style="success", callback_data=f"receipt:{order_id}"))
    b.row(kb_button("Скасувати", emoji_id=EMOJI_POOL[3], style="danger", callback_data=f"cancel_order:{order_id}"))
    return b.as_markup()


def admin_order_kb(order_id):
    b = InlineKeyboardBuilder()
    b.row(kb_button("Підтвердити", emoji_id=EMOJI_POOL[0], style="success", callback_data=f"admin_ok:{order_id}"))
    b.row(kb_button("Відхилити", emoji_id=EMOJI_POOL[3], style="danger", callback_data=f"admin_no:{order_id}"))
    return b.as_markup()


def bank_details_kb():
    b = InlineKeyboardBuilder()
    banks = [
        ("Privat24", "private"),
        ("Mono", "mono"),
        ("PUMB", "pumb"),
        ("Альянс", "alliance"),
        ("А-Банк", "abank"),
    ]
    for name, code in banks:
        b.row(kb_button(name, emoji_id=EMOJI_POOL[3], style="primary", callback_data=f"adm_bank:{code}"))
    b.row(back_inline("admin:back"))
    return b.as_markup()


def support_reply_kb(user_id):
    b = InlineKeyboardBuilder()
    b.row(kb_button("Відповісти", emoji_id=MAIN_EMOJI["support"], style="primary", callback_data=f"support_reply:{user_id}"))
    return b.as_markup()


def admin_menu_kb():
    b = InlineKeyboardBuilder()
    items = [
        ("Курс Stars", EMOJI_POOL[0], "success", "adm:stars_rate"),
        ("Курс TON", EMOJI_POOL[2], "success", "adm:ton_rate"),
        ("Баланс Stars", MAIN_EMOJI["buy_stars"], "primary", "adm:balance"),
        ("NFT", MAIN_EMOJI["nft"], "primary", "adm:nft"),
        ("Реквізити карток", EMOJI_POOL[3], "success", "adm:bank_details"),
        ("Розсилка", EMOJI_POOL[16], "primary", "adm:broadcast"),
        ("Підтримка", MAIN_EMOJI["support"], "success", "adm:support"),
        ("Канал відгуків", MAIN_EMOJI["reviews"], "primary", "adm:reviews"),
        ("Замовлення", EMOJI_POOL[16], "primary", "adm:orders"),
        ("Користувачі", EMOJI_POOL[3], "primary", "adm:users"),
        ("Статистика", EMOJI_POOL[27], "primary", "adm:stats"),
    ]
    for text, eid, style, data in items:
        b.row(kb_button(text, emoji_id=eid, style=style, callback_data=data))
    return b.as_markup()


def nft_admin_kb():
    b = InlineKeyboardBuilder()
    b.row(kb_button("Додати NFT", emoji_id=MAIN_EMOJI["nft"], style="success", callback_data="nftadm:add"))
    b.row(kb_button("Змінити ціну", emoji_id=EMOJI_POOL[4], style="primary", callback_data="nftadm:price"))
    b.row(kb_button("Видалити NFT", emoji_id=EMOJI_POOL[3], style="danger", callback_data="nftadm:delete"))
    b.row(back_inline("admin:back"))
    return b.as_markup()


class Form(StatesGroup):
    custom_stars = State()
    ton_amount = State()
    calculator = State()
    support = State()
    withdraw = State()
    sell_stars = State()
    broadcast = State()
    stars_rate = State()
    ton_rate = State()
    support_setting = State()
    nft_add_wait_emoji = State()
    nft_add_details = State()
    nft_price = State()
    nft_delete = State()
    reject_reason = State()
    receipt = State()
    support_reply = State()
    bank_details = State()
    reviews_setting = State()
    balance_target = State()
    balance_amount = State()


bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


async def notify_admins(text, reply_markup=None, photo=None, document=None):
    for aid in ADMIN_IDS:
        try:
            if photo:
                await bot.send_photo(aid, photo=photo, caption=text, reply_markup=reply_markup)
            elif document:
                await bot.send_document(aid, document=document, caption=text, reply_markup=reply_markup)
            else:
                await bot.send_message(aid, text, reply_markup=reply_markup)
        except Exception:
            pass


async def configure_bot_commands():
    await bot.set_my_commands(
        [BotCommand(command="start", description="Відкрити головне меню")],
        scope=BotCommandScopeAllPrivateChats(),
    )
    for aid in ADMIN_IDS:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Відкрити головне меню"),
                BotCommand(command="id", description="Показати Telegram ID"),
                BotCommand(command="admin", description="Відкрити адмін-панель"),
            ],
            scope=BotCommandScopeChat(chat_id=aid),
        )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"{pe(WELCOME_EMOJI['stars'], '⭐')} <b>Вітаємо у {BOT_NAME}!</b>\n\n"
        f"{pe(WELCOME_EMOJI['stars'], '⭐')} Купуйте Stars\n"
        f"{pe(WELCOME_EMOJI['ton'], '🪙')} Купуйте TON\n"
        f"{pe(WELCOME_EMOJI['fire'], '🔥')} Обирайте NFT та інші цифрові товари\n\n"
        "Швидко, зручно та без зайвих кроків.\n\n"
        "Оберіть потрібний розділ нижче 👇",
        image="welcome",
        reply_markup=main_menu(),
    )


@dp.message(Command("id"))
async def show_user_id(message: Message):
    await message.answer(
        f"🆔 Ваш Telegram ID: <code>{message.from_user.id}</code>\n\n"
        "Цей ID можна додати до змінної ADMIN_IDS."
    )


@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await message.answer("⚙️ <b>Адмін-панель</b>", reply_markup=admin_menu_kb())


@dp.message(F.text == "Скасувати")
@dp.message(F.text == "❌ Скасувати")
async def cancel_state(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in ADMIN_IDS:
        delete_setting(f"pending_bank:{message.from_user.id}")
    await replace_screen(
        message.from_user.id,
        "✅ Дію скасовано.\n\nОберіть потрібний розділ нижче 👇",
        image="welcome",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await replace_screen(
        call.from_user.id,
        "🏠 <b>Головне меню</b>\n\nОберіть потрібний розділ нижче 👇",
        image="welcome",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "Купити Stars")
async def buy_stars(message: Message):
    rate = float(setting("stars_rate"))
    await replace_screen(
        message.from_user.id,
        stars_catalog_text(rate),
        image="stars",
        reply_markup=stars_kb(),
        screen_key="stars_catalog",
    )


@dp.callback_query(F.data.startswith("stars:"))
async def stars_select(call: CallbackQuery, state: FSMContext):
    await call.answer()
    value = call.data.split(":", 1)[1]
    if value == "custom":
        await state.set_state(Form.custom_stars)
        await replace_screen(
            call.from_user.id,
            "⭐ Вкажіть кількість Stars від <b>50</b>.",
            image="stars",
            reply_markup=cancel_kb(),
        )
        return
    stars = int(value)
    amount = round(stars * float(setting("stars_rate")), 2)
    oid = create_order(call.from_user.id, "buy_stars", stars, amount)
    await replace_screen(
        call.from_user.id,
        f"💳 <b>До оплати:</b> {amount:.2f} грн\n"
        f"⭐ <b>Кількість:</b> {stars} Stars\n\n"
        "💳 Оберіть спосіб оплати:",
        image="stars",
        reply_markup=payment_kb(oid),
    )


@dp.message(Form.custom_stars)
async def custom_stars(message: Message, state: FSMContext):
    try:
        stars = int(message.text.strip())
        if stars < 50:
            raise ValueError
    except (ValueError, TypeError):
        await replace_screen(
            message.from_user.id,
            "❌ Введіть коректну кількість Stars від 50.",
            image="stars",
            reply_markup=cancel_kb(),
        )
        return
    amount = round(stars * float(setting("stars_rate")), 2)
    oid = create_order(message.from_user.id, "buy_stars", stars, amount)
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"💳 <b>До оплати:</b> {amount:.2f} грн\n"
        f"⭐ <b>Кількість:</b> {stars} Stars\n\n"
        "💳 Оберіть спосіб оплати:",
        image="stars",
        reply_markup=payment_kb(oid),
    )


@dp.callback_query(F.data.startswith("pay:"))
async def choose_payment(call: CallbackQuery):
    await call.answer()
    _, oid_s, method = call.data.split(":")
    oid = int(oid_s)
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not order or order["user_id"] != call.from_user.id:
        await replace_screen(call.from_user.id, "❌ Замовлення не знайдено.", image="stars", reply_markup=main_menu())
        return
    if method != "ua":
        return
    await replace_screen(
        call.from_user.id,
        "🏦 <b>Оберіть банк для оплати</b>",
        image="stars",
        reply_markup=bank_kb(oid),
    )


@dp.callback_query(F.data.startswith("bank:"))
async def choose_bank(call: CallbackQuery):
    await call.answer()
    _, oid_s, method = call.data.split(":")
    oid = int(oid_s)
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not order or order["user_id"] != call.from_user.id:
        return
    db.execute("UPDATE orders SET payment_method=? WHERE id=?", (method, oid))
    db.commit()
    details = setting(f"bank_{method}") or BANK_DETAILS.get(method, "Реквізити не налаштовані.")
    await replace_screen(
        call.from_user.id,
        f"💳 <b>Замовлення #{oid}</b>\n"
        f"💰 Сума до оплати: <b>{order['amount']:.2f} грн</b>\n\n"
        f"📌 <b>Реквізити:</b>\n<code>{esc(details)}</code>\n\n"
        "Після оплати надішліть квитанцію.",
        image="stars",
        reply_markup=receipt_kb(oid),
    )


@dp.callback_query(F.data.startswith("backpay:"))
async def back_payment(call: CallbackQuery):
    await call.answer()
    oid = int(call.data.split(":")[1])
    await replace_screen(
        call.from_user.id,
        "💳 <b>Оберіть спосіб оплати</b>",
        image="stars",
        reply_markup=payment_kb(oid),
    )


@dp.callback_query(F.data.startswith("receipt:"))
async def receipt_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    oid = int(call.data.split(":")[1])
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not order or order["user_id"] != call.from_user.id:
        return
    await state.update_data(receipt_order=oid)
    await state.set_state(Form.receipt)
    await replace_screen(
        call.from_user.id,
        "🧾 Надішліть фото або документ квитанції.",
        image="stars",
        reply_markup=cancel_kb(),
    )


async def save_receipt(message: Message, state: FSMContext, file_id: str, file_type: str):
    data = await state.get_data()
    oid = data.get("receipt_order")
    if not oid:
        await state.clear()
        return
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not order or order["user_id"] != message.from_user.id:
        await state.clear()
        return
    db.execute(
        "UPDATE orders SET receipt_file_id=?,receipt_type=?,status='waiting_review' WHERE id=?",
        (file_id, file_type, oid),
    )
    db.commit()
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"{pe(EMOJI_POOL[5], '✅')} Квитанцію отримано.\n"
        f"📦 Замовлення #{oid} передано на перевірку.",
        image="stars",
        reply_markup=main_menu(),
    )
    u = user_row(message.from_user.id)
    text = (
        f"🔔 <b>Нове замовлення #{oid}</b>\n\n"
        f"👤 @{esc(u['username'] or 'без_username')}\n"
        f"🆔 <code>{u['id']}</code>\n"
        f"📦 {esc(order['order_type'])}: <b>{esc(order['quantity'])}</b>\n"
        f"💰 <b>{order['amount']:.2f} грн</b>\n"
        f"💳 {esc(order['payment_method'] or '—')}\n"
        f"🕒 {order['created_at']}"
    )
    if file_type == "photo":
        await notify_admins(text, admin_order_kb(oid), photo=file_id)
    else:
        await notify_admins(text, admin_order_kb(oid), document=file_id)


@dp.message(Form.receipt, F.photo)
async def receipt_photo(message: Message, state: FSMContext):
    await save_receipt(message, state, message.photo[-1].file_id, "photo")


@dp.message(Form.receipt, F.document)
async def receipt_document(message: Message, state: FSMContext):
    await save_receipt(message, state, message.document.file_id, "document")


@dp.message(Form.receipt)
async def receipt_invalid(message: Message):
    await replace_screen(
        message.from_user.id,
        "❌ Надішліть саме фото або документ квитанції.",
        image="stars",
        reply_markup=cancel_kb(),
    )


@dp.callback_query(F.data.startswith("cancel_order:"))
async def cancel_order(call: CallbackQuery):
    await call.answer()
    oid = int(call.data.split(":")[1])
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not order or order["user_id"] != call.from_user.id:
        return
    db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))
    db.commit()
    await replace_screen(
        call.from_user.id,
        "❌ Дію скасовано.\n\nОберіть потрібний розділ нижче 👇",
        image="welcome",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "Купити Gram")
@dp.message(F.text == "Купити TON")
async def buy_ton(message: Message, state: FSMContext):
    await state.set_state(Form.ton_amount)
    await replace_screen(
        message.from_user.id,
        f"{pe(MAIN_EMOJI['buy_gram'], '💎')} <b>Курс TON: {setting('ton_rate')} грн</b>\n\n"
        "💎 Вкажіть кількість TON для покупки.\n"
        "📌 Мінімальна кількість: <b>0.25 TON</b>",
        image="ton",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.ton_amount)
async def ton_amount(message: Message, state: FSMContext):
    try:
        ton = float(message.text.replace(",", "."))
        if ton < 0.25:
            raise ValueError
    except (ValueError, AttributeError):
        await replace_screen(
            message.from_user.id,
            "❌ Введіть коректну кількість TON від 0.25.",
            image="ton",
            reply_markup=cancel_kb(),
        )
        return
    amount = round(ton * float(setting("ton_rate")), 2)
    oid = create_order(message.from_user.id, "buy_ton", ton, amount)
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"💳 До оплати: <b>{amount:.2f} грн</b>\n"
        f"💎 Кількість: <b>{ton:g} TON</b>\n\n"
        "💳 Оберіть спосіб оплати:",
        image="ton",
        reply_markup=payment_kb(oid),
    )


@dp.message(F.text == "Вивести Stars")
async def withdraw(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    u = user_row(message.from_user.id)
    minimum = int(setting("min_withdraw"))
    balance = int(u["balance_stars"])
    if balance < minimum:
        await state.clear()
        await replace_screen(
            message.from_user.id,
            f"❌ <b>Недостатньо коштів</b>\n\n"
            f"Ваш баланс: <b>{balance} Stars</b>\n"
            f"Мінімум для виводу: <b>{minimum} Stars</b>.",
            image="withdraw",
            reply_markup=main_menu(),
        )
        return
    await state.set_state(Form.withdraw)
    await replace_screen(
        message.from_user.id,
        f"⭐ Ваш баланс: <b>{balance} Stars</b>\n"
        f"📌 Мінімум для виводу: <b>{minimum} Stars</b>\n\n"
        "⭐ Вкажіть кількість Stars для виводу.",
        image="withdraw",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.withdraw)
async def withdraw_amount(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    u = user_row(message.from_user.id)
    minimum = int(setting("min_withdraw"))
    balance = int(u["balance_stars"])
    try:
        amount = int((message.text or "").strip())
    except (ValueError, TypeError, AttributeError):
        await replace_screen(
            message.from_user.id,
            f"❌ Введіть ціле число. Мінімум для виводу — {minimum} Stars.",
            image="withdraw",
            reply_markup=cancel_kb(),
        )
        return
    if amount < minimum:
        await replace_screen(
            message.from_user.id,
            f"❌ Мінімальна сума для виводу — {minimum} Stars.",
            image="withdraw",
            reply_markup=cancel_kb(),
        )
        return
    if amount > balance:
        await replace_screen(
            message.from_user.id,
            f"❌ <b>Недостатньо коштів</b>\nВаш баланс: <b>{balance} Stars</b>.",
            image="withdraw",
            reply_markup=cancel_kb(),
        )
        return
    oid = create_order(message.from_user.id, "withdraw_stars", amount, 0)
    db.execute("UPDATE orders SET status='waiting_review' WHERE id=?", (oid,))
    db.commit()
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"{pe(EMOJI_POOL[5], '✅')} Запит на вивід <b>#{oid}</b> створено.\n"
        "⏳ Очікуйте обробки заявки адміністратором.",
        image="withdraw",
        reply_markup=main_menu(),
    )
    await notify_admins(
        f"📤 <b>Запит на вивід #{oid}</b>\n"
        f"👤 @{esc(message.from_user.username or 'без_username')}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"⭐ Кількість: <b>{amount}</b>",
        admin_order_kb(oid),
    )


@dp.message(F.text == "Продати Stars")
async def sell_stars(message: Message, state: FSMContext):
    await state.set_state(Form.sell_stars)
    await replace_screen(
        message.from_user.id,
        "⭐ Вкажіть кількість Stars, яку бажаєте продати.",
        image="sell",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.sell_stars)
async def sell_stars_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount <= 0:
            raise ValueError
    except (ValueError, TypeError):
        await replace_screen(
            message.from_user.id,
            "❌ Вкажіть коректну кількість Stars.",
            image="sell",
            reply_markup=cancel_kb(),
        )
        return
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"{pe(EMOJI_POOL[5], '✅')} Запит на продаж <b>{amount} Stars</b> прийнято.\n"
        f"🆘 Для отримання реквізитів зверніться до підтримки: {esc(setting('support'))}",
        image="sell",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "NFT")
async def nft_list(message: Message):
    rows = db.execute("SELECT * FROM nfts WHERE active=1 ORDER BY id DESC").fetchall()
    if not rows:
        await replace_screen(
            message.from_user.id,
            "🎁 Наразі доступних NFT немає.",
            image="nft",
            reply_markup=main_menu(),
        )
        return
    b = InlineKeyboardBuilder()
    for r in rows:
        b.row(kb_button(
            f"{r['title']} — {r['price']:g} грн",
            emoji_id=r["custom_emoji_id"] or MAIN_EMOJI["nft"],
            style="danger",
            callback_data=f"nft:{r['id']}",
        ))
    b.row(back_inline())
    await replace_screen(
        message.from_user.id,
        "🎁 <b>NFT</b>\n\nОберіть NFT зі списку.",
        image="nft",
        reply_markup=b.as_markup(),
    )


@dp.callback_query(F.data.startswith("nft:"))
async def nft_buy(call: CallbackQuery):
    await call.answer()
    nid = int(call.data.split(":")[1])
    r = db.execute("SELECT * FROM nfts WHERE id=? AND active=1", (nid,)).fetchone()
    if not r:
        await replace_screen(
            call.from_user.id,
            "❌ Цей NFT більше недоступний.",
            image="nft",
            reply_markup=main_menu(),
        )
        return
    oid = create_order(call.from_user.id, "nft", r["title"], r["price"], nft_id=nid)
    if r["sticker_file_id"] and r["sticker_type"] == "sticker":
        try:
            await bot.send_sticker(call.message.chat.id, r["sticker_file_id"])
        except Exception:
            pass
    nft_emoji_id = r["custom_emoji_id"] or MAIN_EMOJI["nft"]
    await replace_screen(
        call.from_user.id,
        f"{pe(nft_emoji_id, r['emoji'] or '🎁')} <b>{esc(r['title'])}</b>\n"
        f"💰 Ціна: <b>{r['price']:g} грн</b>\n"
        f"{esc(r['description'])}\n\n"
        "💳 Оберіть спосіб оплати:",
        image="nft",
        reply_markup=payment_kb(oid),
    )


@dp.message(F.text == "Профіль")
async def profile(message: Message):
    ensure_user(message.from_user)
    u = user_row(message.from_user.id)
    await replace_screen(
        message.from_user.id,
        f"{pe(MAIN_EMOJI['profile'], '👤')} <b>Ваш профіль</b>\n\n"
        f"🆔 ID: <code>{u['id']}</code>\n"
        f"👤 Username: @{esc(u['username'] or '—')}\n"
        f"⭐ Баланс: <b>{u['balance_stars']} Stars</b>\n"
        f"📊 Статус: <b>{esc(u['status'])}</b>\n"
        f"⭐ Придбано Stars: {u['bought_stars']}\n"
        f"💎 Придбано TON: {u['bought_ton']}\n"
        f"🚀 Premium: {u['premium_months']} міс.\n"
        f"💰 Витрачено: {u['spent_uah']:.2f} грн\n"
        f"👥 Запрошено друзів: {u['invited']}\n"
        f"📅 Дата реєстрації: <b>{u['registered_at']}</b>",
        image="welcome",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "Калькулятор")
async def calculator(message: Message, state: FSMContext):
    await state.set_state(Form.calculator)
    await replace_screen(
        message.from_user.id,
        "🧮 Вкажіть кількість Stars для розрахунку.",
        image="calculator",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.calculator)
async def calculator_value(message: Message, state: FSMContext):
    try:
        stars = int(message.text)
        if stars < 1:
            raise ValueError
    except (ValueError, TypeError):
        await replace_screen(
            message.from_user.id,
            "❌ Введіть коректне ціле число.",
            image="calculator",
            reply_markup=cancel_kb(),
        )
        return
    amount = stars * float(setting("stars_rate"))
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"🧮 <b>Розрахунок</b>\n\n⭐ Stars: <b>{stars}</b>\n💰 Вартість: <b>{amount:.2f} грн</b>",
        image="calculator",
        reply_markup=main_menu(),
    )


@dp.message(F.text == "Відгуки")
async def reviews(message: Message):
    b = InlineKeyboardMarkup(inline_keyboard=[[
        kb_button("Переглянути відгуки", emoji_id=MAIN_EMOJI["reviews"], style="primary", url=setting("reviews_url"))
    ]])
    await replace_screen(
        message.from_user.id,
        f"{pe(MAIN_EMOJI['reviews'], '💬')} <b>Відгуки наших клієнтів</b>\n\n"
        "Тут ви можете переглянути відгуки наших клієнтів 👇",
        image="reviews",
        reply_markup=b,
    )


@dp.message(F.text == "Підтримка")
async def support(message: Message, state: FSMContext):
    await state.set_state(Form.support)
    await replace_screen(
        message.from_user.id,
        f"{pe(MAIN_EMOJI['support'], '🆘')} <b>Опишіть ваше питання або проблему</b>\n\n"
        "За потреби можете додати фото або відео.",
        image="support",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.support)
async def support_message(message: Message, state: FSMContext):
    if message.content_type not in {ContentType.TEXT, ContentType.PHOTO, ContentType.VIDEO}:
        await message.answer("❌ Надішліть текст, фото або відео.")
        return
    await state.clear()
    ensure_user(message.from_user)
    u = user_row(message.from_user.id)
    reply_markup = support_reply_kb(message.from_user.id)
    text = (
        f"🆘 <b>Нове звернення в підтримку</b>\n"
        f"👤 @{esc(u['username'] or 'без_username')}\n"
        f"🆔 <code>{u['id']}</code>\n\n"
        f"{esc(message.text or message.caption or '[медіа]')}"
    )
    for aid in ADMIN_IDS:
        try:
            if message.photo:
                await bot.send_photo(aid, message.photo[-1].file_id, caption=text, reply_markup=reply_markup)
            elif message.video:
                await bot.send_video(aid, message.video.file_id, caption=text, reply_markup=reply_markup)
            else:
                await bot.send_message(aid, text, reply_markup=reply_markup)
        except Exception:
            pass
    await replace_screen(
        message.from_user.id,
        "✅ Звернення передано в підтримку.",
        image="support",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data.startswith("support_reply:"))
async def support_reply_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    await call.answer()
    user_id = int(call.data.split(":", 1)[1])
    await state.update_data(support_reply_user_id=user_id)
    await state.set_state(Form.support_reply)
    await call.message.answer(
        "✍️ Напишіть відповідь клієнту.\nМожна надіслати текст, фото або відео.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.support_reply)
async def send_support_reply(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    user_id = data.get("support_reply_user_id")
    if not user_id:
        await state.clear()
        await message.answer("❌ Не вдалося визначити отримувача.")
        return
    await state.clear()
    try:
        await bot.copy_message(chat_id=user_id, from_chat_id=message.chat.id, message_id=message.message_id)
    except Exception:
        await message.answer(
            "❌ Не вдалося надіслати відповідь. Можливо, користувач заблокував бота.",
            reply_markup=main_menu(),
        )
        return
    await message.answer("✅ Відповідь надіслано клієнту.", reply_markup=main_menu())


@dp.callback_query(F.data == "admin:back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.clear()
    await call.message.edit_text("⚙️ <b>Адмін-панель</b>", reply_markup=admin_menu_kb())


@dp.callback_query(F.data == "adm:stars_rate")
async def adm_stars_rate(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.set_state(Form.stars_rate)
    await call.message.answer(
        f"⭐ Поточний курс Stars: <b>{setting('stars_rate')} грн</b>\nВведіть новий курс:",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.stars_rate)
async def set_stars_rate(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        value = float(message.text.replace(",", "."))
        if value <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введіть коректне додатне число.")
        return
    set_setting("stars_rate", value)
    await refresh_stars_catalog_screens()
    await state.clear()
    await message.answer(
        f"{pe(EMOJI_POOL[5], '✅')} Курс Stars успішно оновлено: <b>{value:g} грн</b>",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "adm:ton_rate")
async def adm_ton_rate(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.set_state(Form.ton_rate)
    await call.message.answer(
        f"💎 Поточний курс TON: <b>{setting('ton_rate')} грн</b>\nВведіть новий курс:",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.ton_rate)
async def set_ton_rate(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        value = float(message.text.replace(",", "."))
        if value <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введіть коректне додатне число.")
        return
    set_setting("ton_rate", value)
    await state.clear()
    await message.answer(
        f"{pe(EMOJI_POOL[5], '✅')} Курс TON успішно оновлено: <b>{value:g} грн</b>",
        reply_markup=main_menu(),
    )


@dp.callback_query(F.data == "adm:support")
async def adm_support(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.set_state(Form.support_setting)
    await call.message.answer(
        f"🆘 Поточний контакт підтримки: <b>{esc(setting('support'))}</b>\nВведіть новий @username:",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.support_setting)
async def set_support(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    value = message.text.strip()
    if not value.startswith("@"):
        await message.answer("❌ Вкажіть username у форматі @username.")
        return
    set_setting("support", value)
    await state.clear()
    await message.answer("✅ Контакт підтримки оновлено.", reply_markup=main_menu())


@dp.callback_query(F.data == "adm:reviews")
async def adm_reviews(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.set_state(Form.reviews_setting)
    await call.message.answer(
        "💬 <b>Канал відгуків</b>\n\n"
        f"Поточне посилання:\n<code>{esc(setting('reviews_url'))}</code>\n\n"
        "Надішліть @username каналу або посилання, наприклад:\n"
        "<code>@spanix_reviews</code>\n"
        "<code>https://t.me/spanix_reviews</code>",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.reviews_setting)
async def set_reviews(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text:
        await message.answer("❌ Надішліть username або посилання на Telegram-канал.")
        return
    url = normalize_reviews_url(message.text)
    if not url:
        await message.answer("❌ Не вдалося розпізнати канал.\nВикористайте @username або посилання https://t.me/...")
        return
    set_setting("reviews_url", url)
    await state.clear()
    await message.answer("✅ Канал відгуків оновлено.", reply_markup=admin_menu_kb())


@dp.callback_query(F.data == "adm:bank_details")
async def adm_bank_details(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await call.message.answer(
        "💳 <b>Реквізити карток</b>\n\nОберіть банк, щоб переглянути або змінити реквізити:",
        reply_markup=bank_details_kb(),
    )


@dp.callback_query(F.data.startswith("adm_bank:"))
async def adm_bank_choose(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    method = call.data.split(":", 1)[1]
    bank_names = {
        "private": "Privat24",
        "mono": "Mono",
        "pumb": "PUMB",
        "alliance": "Альянс",
        "abank": "А-Банк",
    }
    if method not in bank_names:
        await call.message.answer("❌ Банк не знайдено.")
        return
    current = setting(f"bank_{method}") or "не налаштовані"
    await state.update_data(bank_method=method)
    await state.set_state(Form.bank_details)
    set_setting(f"pending_bank:{call.from_user.id}", method)
    await call.message.answer(
        f"💳 <b>{bank_names[method]}</b>\n\n"
        f"Поточні реквізити:\n<code>{esc(current)}</code>\n\n"
        "Надішліть нові реквізити одним повідомленням.\n"
        "Можна вказати номер картки, ім'я отримувача та додаткову інформацію.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.bank_details)
async def set_bank_details(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    value = (message.text or "").strip()
    if len(value) < 3:
        await message.answer("❌ Вкажіть коректні реквізити одним повідомленням.")
        return
    data = await state.get_data()
    pending_key = f"pending_bank:{message.from_user.id}"
    method = data.get("bank_method") or setting(pending_key)
    if not method:
        await state.clear()
        await message.answer("❌ Не вдалося визначити банк.")
        return
    set_setting(f"bank_{method}", value)
    delete_setting(pending_key)
    await state.clear()
    await message.answer(
        "✅ Реквізити збережено. Вони вже використовуються в нових замовленнях.",
        reply_markup=admin_menu_kb(),
    )


@dp.callback_query(F.data == "adm:broadcast")
async def adm_broadcast(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.set_state(Form.broadcast)
    await call.message.answer(
        "📢 Надішліть повідомлення для розсилки: текст, фото або відео з підписом.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.broadcast)
async def do_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    users = db.execute("SELECT id FROM users").fetchall()
    ok = 0
    for row in users:
        try:
            await bot.copy_message(chat_id=row["id"], from_chat_id=message.chat.id, message_id=message.message_id)
            ok += 1
            await asyncio.sleep(0.04)
        except Exception:
            pass
    await state.clear()
    await message.answer(f"📢 Розсилку завершено.\n✅ Доставлено: {ok}", reply_markup=main_menu())


@dp.callback_query(F.data == "adm:balance")
async def adm_balance(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    await call.answer()
    await state.clear()
    await state.set_state(Form.balance_target)
    await call.message.answer(
        "⭐ <b>Зміна балансу Stars</b>\n\n"
        "Надішліть числовий Telegram ID або username користувача "
        "(наприклад, <code>123456789</code> чи <code>@username</code>).\n"
        "Користувач має хоча б раз відкрити бота командою /start.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.balance_target)
async def balance_target(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text:
        await message.answer("❌ Надішліть ID або username текстом.")
        return
    target = find_user_by_identifier(message.text)
    if not target:
        await message.answer(
            "❌ Користувача не знайдено. Перевірте ID/username або попросіть його "
            "спочатку надіслати боту /start."
        )
        return

    await state.update_data(balance_target_id=target["id"])
    username = f"@{esc(target['username'])}" if target["username"] else esc(target["first_name"] or "без username")
    b = InlineKeyboardBuilder()
    b.row(
        kb_button("Додати Stars", emoji_id=EMOJI_POOL[0], style="success", callback_data="balance_action:add"),
        kb_button("Забрати Stars", emoji_id=EMOJI_POOL[3], style="danger", callback_data="balance_action:remove"),
    )
    await message.answer(
        f"👤 Користувач: <b>{username}</b>\n"
        f"🆔 ID: <code>{target['id']}</code>\n"
        f"⭐ Поточний баланс: <b>{target['balance_stars']} Stars</b>\n\n"
        "Оберіть дію:",
        reply_markup=b.as_markup(),
    )


@dp.callback_query(F.data.startswith("balance_action:"))
async def balance_action(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    data = await state.get_data()
    target_id = data.get("balance_target_id")
    action = call.data.split(":", 1)[1]
    if action not in {"add", "remove"} or not target_id or not user_row(target_id):
        await call.answer("Спочатку виберіть користувача.", show_alert=True)
        return

    await call.answer()
    await state.update_data(balance_action=action)
    await state.set_state(Form.balance_amount)
    verb = "додати" if action == "add" else "забрати"
    await call.message.answer(
        f"Введіть цілу кількість Stars, яку потрібно {verb}.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.balance_amount)
async def balance_amount(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введіть додатне ціле число Stars.")
        return

    data = await state.get_data()
    target_id = data.get("balance_target_id")
    action = data.get("balance_action")
    if not target_id or action not in {"add", "remove"}:
        await state.clear()
        await message.answer("❌ Сеанс зміни балансу завершився. Почніть знову в адмін-панелі.")
        return

    db.execute("BEGIN IMMEDIATE")
    try:
        target = db.execute(
            "SELECT balance_stars FROM users WHERE id=?",
            (target_id,),
        ).fetchone()
        if not target:
            db.rollback()
            await state.clear()
            await message.answer("❌ Користувача більше немає в базі.")
            return

        before = int(target["balance_stars"] or 0)
        if action == "remove" and amount > before:
            db.rollback()
            await message.answer(
                f"❌ У користувача лише <b>{before} Stars</b>. Введіть меншу кількість "
                "або натисніть «Скасувати»."
            )
            return

        after = before + amount if action == "add" else before - amount
        if after > 9_223_372_036_854_775_807:
            db.rollback()
            await message.answer("❌ Такий баланс завеликий.")
            return
        db.execute("UPDATE users SET balance_stars=? WHERE id=?", (after, target_id))
        db.execute(
            """INSERT INTO balance_adjustments
               (user_id,admin_id,action,amount,balance_before,balance_after,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (target_id, message.from_user.id, action, amount, before, after, now()),
        )
        db.commit()
    except Exception:
        db.rollback()
        raise

    await state.clear()
    operation = "додано" if action == "add" else "забрано"
    notification_error = False
    try:
        await bot.send_message(
            target_id,
            f"⭐ Адміністратор змінив ваш баланс: {operation} <b>{amount} Stars</b>.\n"
            f"Поточний баланс: <b>{after} Stars</b>.",
        )
    except Exception:
        notification_error = True

    result = (
        f"✅ {operation.capitalize()} <b>{amount} Stars</b> користувачу "
        f"<code>{target_id}</code>.\n"
        f"Баланс: <b>{before} → {after} Stars</b>."
    )
    if notification_error:
        result += "\n⚠️ Баланс змінено, але повідомлення користувачу надіслати не вдалося."
    await message.answer(result, reply_markup=admin_menu_kb())


@dp.callback_query(F.data == "adm:users")
async def adm_users(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    count = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    rows = db.execute(
        "SELECT id,username,first_name,balance_stars FROM users ORDER BY id DESC LIMIT 30"
    ).fetchall()
    lines = []
    for user in rows:
        label = f"@{esc(user['username'])}" if user["username"] else esc(user["first_name"] or "без username")
        lines.append(
            f"• {label} — <code>{user['id']}</code> — {user['balance_stars']} Stars"
        )
    listing = "\n".join(lines) if lines else "Користувачів поки немає."
    await call.message.answer(
        f"👥 <b>Користувачі: {count}</b>\n"
        f"Показано останніх: {len(rows)}\n\n{listing}"
    )


@dp.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    users = db.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    orders = db.execute("SELECT COUNT(*) c FROM orders").fetchone()["c"]
    done = db.execute("SELECT COUNT(*) c FROM orders WHERE status='completed'").fetchone()["c"]
    money = db.execute("SELECT COALESCE(SUM(amount),0) s FROM orders WHERE status='completed'").fetchone()["s"]
    recent_users = db.execute(
        "SELECT id,username,first_name FROM users ORDER BY registered_at DESC,id DESC LIMIT 10"
    ).fetchall()
    user_lines = []
    for user in recent_users:
        label = f"@{esc(user['username'])}" if user["username"] else esc(user["first_name"] or "без username")
        user_lines.append(f"• {label} — <code>{user['id']}</code>")
    recent_user_list = "\n".join(user_lines) if user_lines else "Поки немає користувачів."
    await call.message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Користувачів: {users}\n"
        f"📦 Замовлень: {orders}\n"
        f"✅ Виконано: {done}\n"
        f"💰 Підтверджено оплат: {money:.2f} грн\n\n"
        f"👤 <b>Останні користувачі</b>\n{recent_user_list}"
    )


@dp.callback_query(F.data == "adm:orders")
async def adm_orders(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    rows = db.execute(
        "SELECT * FROM orders WHERE status IN ('waiting_payment','waiting_review') "
        "ORDER BY id DESC LIMIT 30"
    ).fetchall()
    if not rows:
        await call.message.answer("📦 Нових непідтверджених заявок немає.")
        return
    for order in rows:
        u = user_row(order["user_id"])
        await call.message.answer(
            f"📦 <b>Замовлення #{order['id']}</b>\n"
            f"👤 @{esc(u['username'] or 'без_username')}\n"
            f"🆔 <code>{order['user_id']}</code>\n"
            f"📌 Тип: {esc(order['order_type'])}\n"
            f"📌 Кількість: {esc(order['quantity'])}\n"
            f"💰 Сума: <b>{order['amount']:.2f} грн</b>\n"
            f"📊 Статус: {esc(order['status'])}\n"
            f"💳 Оплата: {esc(order['payment_method'] or '—')}",
            reply_markup=admin_order_kb(order["id"]),
        )


@dp.callback_query(F.data == "adm:nft")
async def adm_nft(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    rows = db.execute("SELECT * FROM nfts ORDER BY id DESC").fetchall()
    text = "🎁 <b>Керування NFT</b>\n\n"
    if rows:
        text += "\n".join(
            f"#{r['id']} — <b>{esc(r['title'])}</b> — {r['price']:g} грн — {'активний' if r['active'] else 'вимкнений'}"
            for r in rows
        )
    else:
        text += "NFT ще не додані."
    await call.message.answer(text, reply_markup=nft_admin_kb())


@dp.callback_query(F.data == "nftadm:add")
async def nft_add_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.set_state(Form.nft_add_wait_emoji)
    await call.message.answer(
        "🎁 <b>Додавання NFT</b>\n\n"
        "Надішліть NFT-стікер або окреме повідомлення з Telegram Premium Emoji.\n"
        "Після цього я попрошу назву, ціну та опис."
    )


@dp.message(Form.nft_add_wait_emoji, F.sticker)
async def nft_receive_sticker(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.update_data(
        sticker_file_id=message.sticker.file_id,
        sticker_type="sticker",
        custom_emoji_id=None,
        nft_emoji=message.sticker.emoji or "🎁",
    )
    await state.set_state(Form.nft_add_details)
    await message.answer(
        "✅ NFT-стікер отримано.\n\n"
        "Тепер надішліть одним повідомленням:\n"
        "<code>Назва | ціна | опис</code>\n\n"
        "Наприклад:\n"
        "<code>Gift #1 | 350 | Опис подарунка</code>"
    )


@dp.message(Form.nft_add_wait_emoji, F.text)
async def nft_receive_custom_emoji(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    custom_emoji_id = next(
        (
            entity.custom_emoji_id
            for entity in (message.entities or [])
            if entity.type == "custom_emoji" and entity.custom_emoji_id
        ),
        None,
    )
    if not custom_emoji_id:
        await message.answer(
            "❌ Не бачу Premium Emoji.\nНадішліть NFT-стікер або Telegram Premium Emoji."
        )
        return
    await state.update_data(
        sticker_file_id=None,
        sticker_type=None,
        custom_emoji_id=custom_emoji_id,
        nft_emoji=message.text.strip() or "🎁",
    )
    await state.set_state(Form.nft_add_details)
    await message.answer(
        "✅ Premium Emoji NFT отримано.\n\n"
        "Тепер надішліть одним повідомленням:\n"
        "<code>Назва | ціна | опис</code>\n\n"
        "Наприклад:\n"
        "<code>Gift #1 | 350 | Опис подарунка</code>"
    )


@dp.message(Form.nft_add_wait_emoji)
async def nft_expected_custom_emoji(message: Message):
    await message.answer("❌ Надішліть NFT-стікер або Telegram Premium Emoji.")


@dp.message(Form.nft_add_details)
async def nft_add_details(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    if not message.text:
        await message.answer("❌ Надішліть текст у форматі: Назва | ціна | опис")
        return
    parts = parse_nft_details(message.text)
    if not parts:
        await message.answer(
            "❌ Не вдалося розпізнати NFT.\n"
            "Надішліть: <code>Назва | ціна | опис</code>\n"
            "або коротко: <code>Мавпа 350 nft</code>"
        )
        return
    title, price_raw, description = parts
    try:
        price = float(price_raw.replace(",", "."))
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer("❌ Ціна має бути числом не менше 0.")
        return
    data = await state.get_data()
    db.execute(
        """INSERT INTO nfts(title,price,emoji,description,sticker_file_id,sticker_type,custom_emoji_id,active)
           VALUES(?,?,?,?,?,?,?,1)""",
        (
            title,
            price,
            data.get("nft_emoji", "🎁"),
            description,
            data.get("sticker_file_id"),
            data.get("sticker_type"),
            data.get("custom_emoji_id"),
        ),
    )
    db.commit()
    await state.clear()
    await message.answer(f"{pe(EMOJI_POOL[5], '✅')} NFT успішно додано.", reply_markup=main_menu())


@dp.callback_query(F.data == "nftadm:price")
async def nft_price_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    rows = db.execute("SELECT id,title,price FROM nfts WHERE active=1 ORDER BY id DESC").fetchall()
    if not rows:
        await call.message.answer("🎁 Немає NFT для редагування.")
        return
    b = InlineKeyboardBuilder()
    for r in rows:
        b.row(kb_button(
            f"#{r['id']} {r['title']} — {r['price']:g} грн",
            emoji_id=MAIN_EMOJI["nft"],
            style="primary",
            callback_data=f"nftprice:{r['id']}",
        ))
    b.row(back_inline("adm:nft"))
    await call.message.answer("💰 Оберіть NFT, для якого змінити ціну:", reply_markup=b.as_markup())


@dp.callback_query(F.data.startswith("nftprice:"))
async def nft_price_choose(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    nid = int(call.data.split(":")[1])
    row = db.execute("SELECT * FROM nfts WHERE id=? AND active=1", (nid,)).fetchone()
    if not row:
        await call.message.answer("❌ NFT не знайдено.")
        return
    await state.update_data(nft_edit_id=nid)
    await state.set_state(Form.nft_price)
    await call.message.answer(
        f"💰 Поточна ціна <b>{row['price']:g} грн</b>. Введіть нову ціну:",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.nft_price)
async def nft_set_price(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        price = float(message.text.replace(",", "."))
        if price < 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введіть коректну ціну.")
        return
    data = await state.get_data()
    nid = data.get("nft_edit_id")
    db.execute("UPDATE nfts SET price=? WHERE id=?", (price, nid))
    db.commit()
    await state.clear()
    await message.answer("✅ Ціну NFT успішно оновлено.", reply_markup=main_menu())


@dp.callback_query(F.data == "nftadm:delete")
async def nft_delete_start(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    rows = db.execute("SELECT id,title,price FROM nfts WHERE active=1 ORDER BY id DESC").fetchall()
    if not rows:
        await call.message.answer("🎁 Немає NFT для видалення.")
        return
    b = InlineKeyboardBuilder()
    for r in rows:
        b.row(kb_button(
            f"#{r['id']} {r['title']}",
            emoji_id=MAIN_EMOJI["nft"],
            style="danger",
            callback_data=f"nftdelete:{r['id']}",
        ))
    b.row(back_inline("adm:nft"))
    await call.message.answer("🗑 Оберіть NFT для видалення:", reply_markup=b.as_markup())


@dp.callback_query(F.data.startswith("nftdelete:"))
async def nft_delete(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    nid = int(call.data.split(":")[1])
    db.execute("UPDATE nfts SET active=0 WHERE id=?", (nid,))
    db.commit()
    await call.message.answer("🗑 NFT видалено з каталогу.")


@dp.callback_query(F.data.startswith("admin_ok:"))
async def admin_ok(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    await call.answer()
    oid = int(call.data.split(":")[1])
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not order or order["status"] not in ("waiting_review", "waiting_payment"):
        await call.message.answer("Замовлення вже оброблене або не існує.")
        return

    db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
    if order["order_type"] == "buy_stars":
        db.execute(
            "UPDATE users SET balance_stars=balance_stars+?, bought_stars=bought_stars+?, spent_uah=spent_uah+?, status='Клієнт' WHERE id=?",
            (int(order["quantity"]), int(order["quantity"]), order["amount"], order["user_id"]),
        )
    elif order["order_type"] == "buy_ton":
        db.execute(
            "UPDATE users SET bought_ton=bought_ton+?, spent_uah=spent_uah+?, status='Клієнт' WHERE id=?",
            (float(order["quantity"]), order["amount"], order["user_id"]),
        )
    elif order["order_type"] == "nft":
        db.execute(
            "UPDATE users SET spent_uah=spent_uah+?, status='Клієнт' WHERE id=?",
            (order["amount"], order["user_id"]),
        )
    elif order["order_type"] == "withdraw_stars":
        db.execute(
            "UPDATE users SET balance_stars=MAX(balance_stars-?,0) WHERE id=?",
            (int(order["quantity"]), order["user_id"]),
        )
    db.commit()

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"{pe(EMOJI_POOL[5], '✅')} Замовлення #{oid} підтверджено.")

    await bot.send_message(
        order["user_id"],
        f"{pe(EMOJI_POOL[5], '✅')} <b>Замовлення #{oid} підтверджено!</b>",
        reply_markup=main_menu(),
    )

    if order["order_type"] == "nft" and order["nft_id"]:
        nft = db.execute("SELECT * FROM nfts WHERE id=?", (order["nft_id"],)).fetchone()
        if nft and nft["sticker_file_id"] and nft["sticker_type"] == "sticker":
            try:
                await bot.send_sticker(order["user_id"], nft["sticker_file_id"])
            except Exception:
                pass


@dp.callback_query(F.data.startswith("admin_no:"))
async def admin_no(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    await call.answer()
    oid = int(call.data.split(":")[1])
    await state.update_data(reject_order=oid)
    await state.set_state(Form.reject_reason)
    await call.message.answer(
        f"🔴 Вкажіть причину відхилення замовлення #{oid}:",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.reject_reason)
async def reject_reason(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    data = await state.get_data()
    oid = data.get("reject_order")
    reason = message.text or "Без причини"
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if not order:
        await state.clear()
        return
    db.execute(
        "UPDATE orders SET status='rejected',admin_note=? WHERE id=?",
        (reason, oid),
    )
    db.commit()
    await state.clear()
    await message.answer(f"🔴 Замовлення #{oid} відхилено.", reply_markup=main_menu())
    await bot.send_message(
        order["user_id"],
        f"🔴 <b>Ваше замовлення #{oid} відхилено.</b>\n\nПричина: {esc(reason)}",
    )


@dp.message()
async def fallback(message: Message, state: FSMContext):
    ensure_user(message.from_user)
    if message.from_user.id in ADMIN_IDS:
        pending_key = f"pending_bank:{message.from_user.id}"
        method = setting(pending_key)
        if method and message.text:
            value = message.text.strip()
            if len(value) < 3:
                await message.answer("❌ Вкажіть коректні реквізити одним повідомленням.")
                return
            set_setting(f"bank_{method}", value)
            delete_setting(pending_key)
            await state.clear()
            await message.answer(
                "✅ Реквізити збережено. Вони вже використовуються в нових замовленнях.",
                reply_markup=admin_menu_kb(),
            )
            return
    await message.answer(
        "🤔 Не вдалося розпізнати команду. Оберіть потрібний розділ у меню.",
        reply_markup=main_menu(),
    )


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задано BOT_TOKEN у Replit Secrets.")
    if not ADMIN_IDS:
        print("ADMIN_IDS не задано: надішліть боту /id, додайте ID в ADMIN_IDS і перезапустіть бота.")
    await configure_bot_commands()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
