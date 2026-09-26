import asyncio
import csv
import difflib
import html
import json
import os
import re
import secrets
import sqlite3
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, ContentType
from aiogram.exceptions import TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    CallbackQuery,
    ErrorEvent,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    Update,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import ClientSession, ClientTimeout, web
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().with_name(".env"))

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMIN_IDS = {
    int(x) for x in re.split(
        r"[\s,;]+", os.getenv("ADMIN_IDS") or "8759868224"
    ) if x.isdigit()
}
for _admin_env_name in ("ADMIN_ID", "OWNER_ID"):
    _admin_env_value = os.getenv(_admin_env_name, "").strip()
    if _admin_env_value.isdigit():
        ADMIN_IDS.add(int(_admin_env_value))
BOT_NAME = "Spanix Stars"
PROJECT_DIR = Path(__file__).resolve().parent
RENDER_DISK_PATH = os.getenv("RENDER_DISK_PATH", "/var/data").strip()
render_disk_dir = Path(RENDER_DISK_PATH).expanduser()
default_db_path = (
    render_disk_dir / "bot.db"
    if render_disk_dir.is_dir()
    else PROJECT_DIR / "bot.db"
)
configured_db_path = os.getenv("DB_PATH", "").strip()
DB_PATH = configured_db_path or str(default_db_path)
if DB_PATH != ":memory:":
    db_file = Path(DB_PATH).expanduser()
    if not db_file.is_absolute():
        db_file = PROJECT_DIR / db_file
    try:
        db_file.parent.mkdir(parents=True, exist_ok=True)
        probe_file = db_file.parent / f".{db_file.name}.write-test"
        probe_file.touch(exist_ok=True)
        probe_file.unlink(missing_ok=True)
    except OSError as error:
        fallback_db_file = PROJECT_DIR / "bot.db"
        fallback_db_file.parent.mkdir(parents=True, exist_ok=True)
        print(
            f"Database path {db_file} is unavailable ({error}). "
            f"Using fallback {fallback_db_file}."
        )
        db_file = fallback_db_file
    legacy_db_file = PROJECT_DIR / "bot.db"
    if db_file != legacy_db_file and not db_file.exists() and legacy_db_file.exists():
        try:
            shutil.copy2(legacy_db_file, db_file)
        except OSError as error:
            print(f"Could not migrate legacy database to {db_file}: {error}")
    DB_PATH = str(db_file.resolve())
SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "@support")
REVIEWS_URL = os.getenv("REVIEWS_URL", "https://t.me/")
KEEPALIVE_URL = os.getenv("KEEPALIVE_URL", "").strip()
try:
    KEEPALIVE_INTERVAL = max(300, int(os.getenv("KEEPALIVE_INTERVAL", "600")))
except ValueError:
    KEEPALIVE_INTERVAL = 600
WEBHOOK_URL = (
    os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
).strip().rstrip("/")
WEBHOOK_PATH = "/telegram/webhook"
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "").strip()
# Comma/semicolon-separated channel configuration. Each item can be:
#   @public_channel
#   -1001234567890|https://t.me/+invite_link|Channel title
# The bot must be an administrator in every configured channel.
REQUIRED_CHANNELS = os.getenv("REQUIRED_CHANNELS", "").strip()

BANK_DETAILS = {
    "private": os.getenv("PRIVATE_DETAILS", "Реквізити Privat24 не налаштовані."),
    "mono": os.getenv("MONO_DETAILS", "Реквізити Mono не налаштовані."),
    "pumb": os.getenv("PUMB_DETAILS", "Реквізити PUMB не налаштовані."),
    "alliance": os.getenv("ALLIANCE_DETAILS", "Реквізити Альянс не налаштовані."),
    "abank": os.getenv("ABANK_DETAILS", "Реквізити А-Банк не налаштовані."),
}

# One source of truth for the banks shown to customers and administrators.
# The same keys are used by payment_method, settings and receipt validation.
BANK_OPTIONS = (
    ("Privat24", "private", "ПриватБанк"),
    ("Mono", "mono", "Monobank"),
    ("PUMB", "pumb", "ПУМБ"),
    ("Альянс", "alliance", "Альянс Банк"),
    ("А-Банк", "abank", "А-Банк"),
)

BANK_DISPLAY_NAMES = {code: display for _, code, display in BANK_OPTIONS}

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


def _compact_spaces(value):
    return re.sub(r"\s+", " ", str(value or "")).strip(" \t:;-")


def _label_value(lines, labels, start=0, end=None):
    """Find a value on the same line as a label or on the following line."""
    end = len(lines) if end is None else end
    aliases = sorted((label.lower() for label in labels), key=len, reverse=True)
    for index in range(start, end):
        line = _compact_spaces(lines[index])
        lowered = line.lower()
        for label in aliases:
            if not lowered.startswith(label):
                continue
            remainder = line[len(label):].lstrip(" \t:;-")
            if remainder:
                return remainder
            for next_index in range(index + 1, min(index + 3, end)):
                value = _compact_spaces(lines[next_index])
                if value:
                    return value
    return ""


def _section_bounds(lines, section_labels, next_section_labels):
    start = next((i for i, line in enumerate(lines) if any(
        label in line.lower() for label in section_labels
    )), None)
    if start is None:
        return 0, len(lines)
    end = next(
        (i for i in range(start + 1, len(lines))
         if any(label in lines[i].lower() for label in next_section_labels)),
        len(lines),
    )
    return start, end


def _number(value):
    if not value:
        return ""
    match = re.search(r"(?<!\d)(\d[\d\s]*(?:[.,]\d{1,2})?)(?!\d)", value)
    if not match:
        return ""
    return match.group(1).replace(" ", "").replace(",", ".")


def _text_value(value):
    """Remove OCR punctuation around a text field without destroying its value."""
    return _compact_spaces(value).strip(" .,:;|-")


def _identifier(value):
    """Keep receipt identifiers readable while removing common OCR separators."""
    return _text_value(value).replace("№", "").strip()


def _find_value_by_patterns(text, patterns):
    """Return the first value captured by one of several label patterns."""
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = _text_value(match.group(1))
            if value:
                return value
    return ""


def _bank_method_match(expected_method, detected_bank):
    """Classify a receipt bank against the bank selected before payment."""
    expected_aliases = {
        "private": ("privat", "приват", "приват24"),
        "mono": ("mono", "монобанк", "monobank"),
        "pumb": ("pumb", "пумб"),
        "alliance": ("alliance", "альянс"),
        "abank": ("a-bank", "a bank", "абанк", "а-банк"),
    }.get(expected_method, ())
    if not expected_method:
        return ""
    if not detected_bank:
        return "Банк не визначено"
    detected_key = _bank_key(detected_bank)
    if any(_bank_key(alias) in detected_key or detected_key in _bank_key(alias)
           for alias in expected_aliases):
        return "Збігається"
    return "Не збігається"


def _amount_match(receipt_amount, order_amount):
    """Compare a parsed receipt amount to the amount of the current order."""
    if not receipt_amount or order_amount in (None, ""):
        return ""
    try:
        receipt_value = round(float(str(receipt_amount).replace(",", ".")), 2)
        order_value = round(float(order_amount), 2)
    except (TypeError, ValueError):
        return "Не вдалося перевірити"
    return "Збігається" if receipt_value == order_value else "Не збігається"


def _is_payment_system(value):
    return bool(re.fullmatch(
        r"(visa|mastercard|maestro|amex|мир|віза|master card)",
        value.strip(),
        re.IGNORECASE,
    ))


def _is_money_line(value):
    return bool(re.fullmatch(r"\d{1,6}(?:[.,]\d{1,2})?", value.replace(" ", "")))


RECEIPT_BANK_MARKERS = (
    # Ukrainian banks and the names commonly printed on their receipts.
    # Keep aliases compact and include the names used by mobile banking apps:
    # OCR often drops spaces, hyphens, quotes, or the "АТ" prefix.
    ("monobank", "Monobank"),
    ("mono", "Monobank"),
    ("mono bank", "Monobank"),
    ("приватбанк", "ПриватБанк"),
    ("privatbank", "PrivatBank"),
    ("приват банк", "ПриватБанк"),
    ("приват24", "Privat24"),
    ("privat24", "Privat24"),
    ("пумб", "ПУМБ"),
    ("pumb", "PUMB"),
    ("pumb bank", "PUMB"),
    ("а-банк", "А-Банк"),
    ("а банк", "А-Банк"),
    ("a-bank", "A-Bank"),
    ("a bank", "A-Bank"),
    ("абанк", "А-Банк"),
    ("альянс", "Альянс Банк"),
    ("alliance bank", "Alliance Bank"),
    ("ощадбанк", "Ощадбанк"),
    ("oschadbank", "Oschadbank"),
    ("райффайзен", "Райффайзен Банк"),
    ("raiffeisen", "Raiffeisen Bank"),
    ("райф", "Райффайзен Банк"),
    ("сенс банк", "Sense Bank"),
    ("sense bank", "Sense Bank"),
    ("сенсбанк", "Sense Bank"),
    ("sensebank", "Sense Bank"),
    ("альфа-банк", "Альфа-Банк"),
    ("alfabank", "Alfa Bank"),
    ("укрсиббанк", "УкрСиббанк"),
    ("ukrsibbank", "Ukrsibbank"),
    ("укрсиб", "УкрСиббанк"),
    ("укргазбанк", "Укргазбанк"),
    ("ukrgasbank", "Ukrgasbank"),
    ("укрексімбанк", "Укрексімбанк"),
    ("укрэксимбанк", "Укрэксимбанк"),
    ("ukreximbank", "Ukreximbank"),
    ("otp bank", "OTP Bank"),
    ("otp банк", "OTP Bank"),
    ("отп банк", "OTP Bank"),
    ("креді агріколь", "Credit Agricole"),
    ("креди агриколь", "Credit Agricole"),
    ("credit agricole", "Credit Agricole"),
    ("універсал банк", "Універсал Банк"),
    ("universal bank", "Universal Bank"),
    ("універсалбанк", "Універсал Банк"),
    ("universalbank", "Universal Bank"),
    ("таскомбанк", "ТАСКОМБАНК"),
    ("taskombank", "Tascombank"),
    ("кредобанк", "Кредобанк"),
    ("kredobank", "KredoBank"),
    ("банк кредит дніпро", "Банк Кредит Дніпро"),
    ("credit dnipro", "Credit Dnipro"),
    ("про kredit", "ProCredit Bank"),
    ("procredit", "ProCredit Bank"),
    ("ідея банк", "Ідея Банк"),
    ("idea bank", "Idea Bank"),
    ("піреус", "Піреус Банк"),
    ("piraeus", "Piraeus Bank"),
    ("банк восток", "Банк Восток"),
    ("bank vostok", "Bank Vostok"),
    ("банк львів", "Банк Львів"),
    ("bank lviv", "Bank Lviv"),
    ("мтб банк", "МТБ БАНК"),
    ("mtb bank", "MTB Bank"),
    ("izibank", "izibank"),
    ("izi банк", "izibank"),
    ("ізібанк", "izibank"),
    ("іsіbank", "izibank"),
    ("бісбанк", "BISBANK"),
    ("bisbank", "BISBANK"),
    ("банк альянс", "Альянс Банк"),
    ("банк інвестицій та заощаджень", "Банк інвестицій та заощаджень"),
    ("банк інвестицій", "Банк інвестицій та заощаджень"),
    ("бізбанк", "БІЗБАНК"),
    ("глобус банк", "Глобус Банк"),
    ("globus bank", "Globus Bank"),
    ("глобусбанк", "Глобус Банк"),
    ("необанк", "NEOBANK"),
    ("neobank", "NEOBANK"),
    ("юнекс банк", "Юнекс Банк"),
    ("unex bank", "Unex Bank"),
    ("юникс банк", "Юнекс Банк"),
    ("правекс банк", "Правекс Банк"),
    ("pravex bank", "Pravex Bank"),
    ("індустріалбанк", "Індустріалбанк"),
    ("industrialbank", "Industrialbank"),
    ("кристалбанк", "Кристалбанк"),
    ("crystalbank", "CrystalBank"),
    ("комінбанк", "COMINBANK"),
    ("cominbank", "COMINBANK"),
    ("мегабанк", "МЕГАБАНК"),
    ("megabank", "MEGABANK"),
    ("банк південний", "Банк Південний"),
    ("bank pivdennyi", "Bank Pivdennyi"),
    ("південний", "Банк Південний"),
    ("мiжнародний інвестиційний банк", "МІБ"),
    ("міжнародний інвестиційний банк", "МІБ"),
    ("mib", "MIB"),
    ("сredit agricole", "Credit Agricole"),
    ("сredit agricole", "Credit Agricole"),
    ("кредитвест банк", "Кредитвест Банк"),
    ("creditwest bank", "Creditwest Bank"),
    ("банк 3/4", "Банк 3/4"),
    ("банк три чверті", "Банк 3/4"),
    ("сhіпабанк", "Чінабaнк"),
    ("чинaбанк", "Чінабaнк"),
    ("china construction bank", "China Construction Bank"),
    ("сітібанк", "Citibank"),
    ("citibank", "Citibank"),
    ("деutsche bank", "Deutsche Bank"),
    ("deutsche bank", "Deutsche Bank"),
    ("юсіb", "USB"),
    ("укркапітал", "Український капітал"),
    ("український капітал", "Український капітал"),
    ("ukrcapital", "Ukrainian Capital Bank"),
)


def _bank_key(value):
    """Normalize a bank name for OCR-tolerant matching."""
    value = str(value or "").lower()
    # OCR may mix visually similar Latin/Cyrillic characters in one word.
    value = value.translate(str.maketrans({
        "а": "a", "е": "e", "і": "i", "ї": "i", "є": "e",
        "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    }))
    return re.sub(r"[^a-z0-9а-яіїєґ]", "", value)


def _bank_alias_matches(alias, normalized_text, lines):
    alias_key = _bank_key(alias)
    if not alias_key:
        return False
    if alias_key in normalized_text:
        return True

    # A short OCR typo (for example "monobark") should not turn a receipt
    # into an unknown bank. Only use fuzzy matching for longer aliases and
    # compare individual OCR words to avoid matching a whole unrelated line.
    if len(alias_key) < 7:
        return False
    for line in lines:
        for word in re.findall(r"[a-zа-яіїєґ0-9]{5,}", line.lower()):
            word_key = _bank_key(word)
            if abs(len(word_key) - len(alias_key)) > 2:
                continue
            if difflib.SequenceMatcher(None, alias_key, word_key).ratio() >= 0.84:
                return True
    return False


def _detect_receipt_bank(lines, raw_text):
    """Return a known bank name or a bank name read directly by OCR."""
    normalized_text = _bank_key(raw_text)
    for marker, bank_name in RECEIPT_BANK_MARKERS:
        if _bank_alias_matches(marker, normalized_text, lines):
            return bank_name

    # Keep working with a bank not listed above. Do not mistake field labels
    # such as "Банк одержувача" for the bank itself.
    ignored = (
        "банк одержувача", "банк получателя", "банк відправника",
        "банк отправителя", "код банку", "bank code", "recipient bank",
        "sender bank",
    )
    for line in lines:
        lowered = line.lower()
        if ("банк" in lowered or "bank" in lowered) and not any(
            label in lowered for label in ignored
        ):
            return line
    return ""


def _parse_columnar_receipt(lines, result):
    """Handle bank receipts where OCR reads the left column before the right."""
    bank_code_index = next(
        (
            i for i, line in enumerate(lines)
            if re.fullmatch(r"\d{6}", line.replace(" ", ""))
        ),
        None,
    )
    if bank_code_index is None or bank_code_index < 2:
        return

    sender_bank = lines[bank_code_index - 1]
    sender_name = lines[bank_code_index - 2]
    if "банк" not in sender_bank.lower() and "bank" not in sender_bank.lower():
        return

    result["sender_name"] = sender_name
    result["sender_bank"] = sender_bank
    result["sender_bank_code"] = lines[bank_code_index].replace(" ", "")

    sender_payment_index = next(
        (i for i in range(bank_code_index + 1, min(bank_code_index + 5, len(lines)))
         if _is_payment_system(lines[i])),
        None,
    )
    if sender_payment_index is None:
        return
    result["sender_payment_system"] = lines[sender_payment_index]

    receiver_bank_index = next(
        (
            i for i in range(sender_payment_index + 2, len(lines))
            if ("банк" in lines[i].lower() or "bank" in lines[i].lower())
            and "код" not in lines[i].lower()
        ),
        None,
    )
    if receiver_bank_index is None or receiver_bank_index < sender_payment_index + 2:
        return
    receiver_name_index = receiver_bank_index - 1
    result["receiver_name"] = lines[receiver_name_index]
    result["receiver_bank"] = lines[receiver_bank_index]

    receiver_payment_index = next(
        (i for i in range(receiver_bank_index + 1, min(receiver_bank_index + 4, len(lines)))
         if _is_payment_system(lines[i])),
        None,
    )
    if receiver_payment_index is None:
        return
    result["receiver_payment_system"] = lines[receiver_payment_index]

    sender_instrument_lines = lines[sender_payment_index + 1:receiver_name_index]
    if sender_instrument_lines:
        result["sender_instrument"] = " ".join(sender_instrument_lines)

    receiver_instrument_index = receiver_payment_index + 1
    if receiver_instrument_index < len(lines):
        result["receiver_instrument"] = lines[receiver_instrument_index]

    amount_index = next(
        (
            i for i in range(receiver_instrument_index + 1, len(lines))
            if re.fullmatch(r"\d{1,6}[.,]\d{1,2}", lines[i].replace(" ", ""))
        ),
        None,
    )
    if amount_index is None:
        return
    result["amount"] = lines[amount_index].replace(" ", "").replace(",", ".")

    fee_index = next(
        (i for i in range(amount_index + 1, min(amount_index + 4, len(lines)))
         if _is_money_line(lines[i])),
        None,
    )
    if fee_index is not None:
        result["fee"] = lines[fee_index].replace(" ", "").replace(",", ".")
        if result["fee"] in {"0", "00", "000"}:
            result["fee"] = "0.00"

    date_index = next(
        (
            i for i in range(amount_index + 1, len(lines))
            if re.fullmatch(
                r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?",
                lines[i],
            )
        ),
        None,
    )
    auth_index = next(
        (
            i for i in range((fee_index or amount_index) + 1, len(lines))
            if re.fullmatch(r"\d{6}", lines[i].replace(" ", ""))
        ),
        None,
    )
    if auth_index is not None:
        result["authorization_code"] = lines[auth_index].replace(" ", "")
    if date_index is not None:
        result["operation_datetime"] = lines[date_index]
        if auth_index is not None and auth_index < date_index:
            purpose_lines = [
                line for line in lines[auth_index + 1:date_index]
                if line and "сум" not in line.lower() and len(line) > 2
            ]
            if purpose_lines:
                result["payment_purpose"] = " ".join(purpose_lines)
        if date_index + 1 < len(lines):
            result["device_id"] = lines[date_index + 1].rstrip(":")


def parse_receipt_text(raw_text):
    """Extract common receipt fields while keeping the original OCR text."""
    text = raw_text or ""
    lines = [_compact_spaces(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    lower_text = text.lower()
    result = {
        "ocr_status": "Розпізнано" if lines else "Потрібна перевірка",
        "receipt_number": "",
        "bank": "",
        "transaction_id": "",
        "operation_id": "",
        "rrn": "",
        "status": "",
        "operation_datetime": "",
        "currency": "",
        "sender_name": "",
        "sender_bank": "",
        "sender_bank_code": "",
        "sender_account": "",
        "sender_card": "",
        "sender_payment_system": "",
        "sender_instrument": "",
        "receiver_name": "",
        "receiver_bank": "",
        "receiver_bank_code": "",
        "receiver_account": "",
        "receiver_card": "",
        "receiver_payment_system": "",
        "receiver_instrument": "",
        "amount": "",
        "fee": "",
        "total_amount": "",
        "authorization_code": "",
        "payment_purpose": "",
        "comment": "",
        "merchant": "",
        "device_id": "",
    }

    receipt_line = _label_value(lines, (
        "квитанція", "квитанция", "receipt number", "receipt no", "receipt №",
    ))
    if receipt_line:
        number_match = re.search(
            r"(?:№|no\.?)\s*([A-Za-zА-Яа-яІіЇїЄє0-9][A-Za-zА-Яа-яІіЇїЄє0-9/_-]*)",
            receipt_line,
            re.IGNORECASE,
        )
        result["receipt_number"] = number_match.group(1) if number_match else receipt_line

    result["bank"] = _detect_receipt_bank(lines, lower_text)

    # Bank apps use different names for the same identifiers. Parse these
    # before sender/receiver sections so compact receipts are covered too.
    result["transaction_id"] = _identifier(_label_value(lines, (
        "ідентифікатор транзакції", "идентификатор транзакции",
        "transaction id", "transaction number", "номер транзакції",
        "номер транзакции", "номер операції", "номер операции",
    )))
    result["operation_id"] = _identifier(_label_value(lines, (
        "id операції", "id операции", "operation id", "операція id",
        "операция id", "reference", "референс", "референс платежу",
    )))
    result["rrn"] = _identifier(_label_value(lines, (
        "rrn", "retrieval reference number", "код трансакції",
        "код транзакції", "код транзакции",
    )))
    result["status"] = _text_value(_label_value(lines, (
        "статус платежу", "статус платежа", "payment status", "status",
    )))
    result["currency"] = _text_value(_label_value(lines, (
        "валюта", "currency", "валюта операції", "валюта платежу",
    )))

    result["operation_datetime"] = _label_value(lines, (
        "дата та час операції", "дата і час операції", "дата операції",
        "дата платежу", "дата и время операции", "transaction date",
        "дата переказу", "дата перевода", "created at",
    ))
    if not result["operation_datetime"]:
        date_match = re.search(
            r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?)\b"
            r"|\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b",
            text,
        )
        if date_match:
            result["operation_datetime"] = date_match.group(1) or date_match.group(2)

    sender_start, sender_end = _section_bounds(
        lines,
        ("відправник", "отправитель", "sender", "payer"),
        ("одержувач", "получатель", "receiver", "recipient", "деталі транзакції",
         "детали операции", "transaction details"),
    )
    receiver_start, receiver_end = _section_bounds(
        lines,
        ("одержувач", "получатель", "receiver", "recipient"),
        ("деталі транзакції", "детали операции", "transaction details"),
    )
    sender = (
        ("sender_name", ("ім'я", "ім’я", "имя", "name")),
        ("sender_bank", ("банк відправника", "банк отправителя", "sender bank", "bank")),
        ("sender_bank_code", ("код банку", "bank code")),
        ("sender_account", (
            "рахунок відправника", "счет отправителя", "sender account",
            "рахунок платника", "счет плательщика", "payer account",
            "iban відправника", "iban отправителя",
        )),
        ("sender_card", (
            "картка відправника", "карта отправителя", "sender card",
            "картка платника", "карта плательщика", "payer card",
        )),
        ("sender_payment_system", ("платіжна система", "платежная система", "payment system")),
        ("sender_instrument", ("платіжний інструмент", "платежный инструмент", "payment instrument")),
    )
    for key, labels in sender:
        result[key] = _label_value(lines, labels, sender_start, sender_end)

    receiver = (
        ("receiver_name", ("ім'я", "ім’я", "имя", "name")),
        ("receiver_bank", ("банк одержувача", "банк получателя", "recipient bank", "bank")),
        ("receiver_bank_code", ("код банку одержувача", "код банка получателя", "recipient bank code")),
        ("receiver_account", (
            "рахунок одержувача", "счет получателя", "receiver account",
            "рахунок отримувача", "счет получателя", "recipient account",
            "iban одержувача", "iban получателя",
        )),
        ("receiver_card", (
            "картка одержувача", "карта получателя", "receiver card",
            "картка отримувача", "карта получателя", "recipient card",
        )),
        ("receiver_payment_system", ("платіжна система", "платежная система", "payment system")),
        ("receiver_instrument", ("платіжний інструмент", "платежный инструмент", "payment instrument")),
    )
    for key, labels in receiver:
        result[key] = _label_value(lines, labels, receiver_start, receiver_end)

    # Mobile receipts frequently put the party name directly after the label
    # instead of creating a separate "sender" section.
    if not result["sender_name"]:
        result["sender_name"] = _label_value(lines, (
            "відправник", "отправитель", "sender", "payer",
            "платник", "плательщик",
        ))
    if not result["receiver_name"]:
        result["receiver_name"] = _label_value(lines, (
            "одержувач", "получатель", "receiver", "recipient",
            "отримувач", "получатель платежа", "одержувач платежу",
        ))

    result["amount"] = _number(_label_value(lines, (
        "сума (грн)", "сума платежу", "сумма (грн)", "сумма платежа",
        "сума", "сумма", "amount", "payment amount",
    )))
    result["fee"] = _number(_label_value(lines, (
        "комісія (грн)", "комиссия (грн)", "комісія", "комиссия", "fee",
    )))
    result["total_amount"] = _number(_label_value(lines, (
        "сума з комісією", "сумма с комиссией", "total amount", "total",
    )))
    result["authorization_code"] = _label_value(lines, (
        "код авторизації", "код авторизации", "authorization code", "auth code",
    ))
    result["payment_purpose"] = _label_value(lines, (
        "призначення платежу", "назначение платежа", "payment purpose", "description",
        "призначення переказу", "назначение перевода", "деталі платежу",
        "детали платежа",
    ))
    result["comment"] = _label_value(lines, (
        "коментар", "комментарий", "comment", "примітка", "примечание",
    ))
    result["merchant"] = _label_value(lines, (
        "торговець", "торговец", "merchant", "одержувач платежу",
        "получатель платежа",
    ))
    result["device_id"] = _label_value(lines, (
        "ідентифікатор платіжного пристрою", "идентификатор платежного устройства",
        "device id", "terminal id",
    ))

    # Compact receipt variants often have no visible sender/receiver section.
    compact_fields = {
        "sender_account": ("рахунок платника", "счет плательщика", "payer account"),
        "receiver_account": ("рахунок отримувача", "счет получателя", "recipient account"),
        "sender_card": ("картка платника", "карта плательщика", "payer card"),
        "receiver_card": ("картка отримувача", "карта получателя", "recipient card"),
        "authorization_code": ("код авторизації", "код авторизации", "authorization code", "auth code"),
    }
    for key, labels in compact_fields.items():
        if not result[key]:
            result[key] = _label_value(lines, labels)

    # Last-resort patterns for labelled identifiers and IBANs.
    if not result["transaction_id"]:
        result["transaction_id"] = _find_value_by_patterns(lower_text, (
            r"(?:номер\s+(?:операції|операции|транзакції|транзакции)|"
            r"transaction\s+(?:id|number))\s*[:№#-]?\s*([a-zа-яіїєґ0-9/_-]{4,})",
        ))
    if not result["rrn"]:
        result["rrn"] = _find_value_by_patterns(lower_text, (
            r"\brrn\s*[:#-]?\s*([a-z0-9-]{6,})",
        ))
    iban_match = re.search(r"\b([A-Z]{2}\d{2}[A-Z0-9]{11,30})\b", text, re.IGNORECASE)
    if iban_match and not result["receiver_account"]:
        result["receiver_account"] = iban_match.group(1).upper()
    if not result["currency"]:
        currency_match = re.search(
            r"(?:сума|сумма|amount|total)\s*[:(]?[^\n]{0,40}?\b(UAH|грн|₴|USD|EUR)\b",
            text,
            re.IGNORECASE,
        )
        if currency_match:
            result["currency"] = currency_match.group(1).upper()

    # Some banks print all labels first and all values below them.
    _parse_columnar_receipt(lines, result)

    # Some banks print fields in a compact line without a visible label.
    if not result["sender_bank_code"]:
        result["sender_bank_code"] = _label_value(lines, ("код банку", "bank code"))
    if not result["total_amount"] and result["amount"] and result["fee"] in {"0", "0.00"}:
        result["total_amount"] = result["amount"]

    found_values = sum(bool(value) for key, value in result.items() if key != "ocr_status")
    if not found_values:
        result["ocr_status"] = "Потрібна перевірка"
    return result


def ocr_receipt_file(path):
    """OCR an image/PDF if optional OCR packages are installed."""
    try:
        from PIL import Image, ImageEnhance, ImageOps
        import pytesseract
    except ImportError:
        return {}, "", "Для OCR потрібні пакети Pillow та pytesseract."

    suffix = path.suffix.lower()
    images = []
    try:
        if suffix == ".pdf":
            try:
                import fitz
            except ImportError:
                return {}, "", "Для OCR PDF потрібен пакет PyMuPDF."
            pdf = fitz.open(path)
            for page in pdf:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                images.append(Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples))
        else:
            images.append(Image.open(path))
    except Exception as exc:
        return {}, "", f"Не вдалося відкрити файл квитанції: {exc}"

    requested_languages = [
        item.strip()
        for item in os.getenv("TESSERACT_LANG", "ukr+rus+eng").split("+")
        if item.strip()
    ]
    try:
        installed_languages = set(pytesseract.get_languages(config=""))
    except Exception:
        installed_languages = set()
    available_languages = [
        language for language in requested_languages
        if not installed_languages or language in installed_languages
    ]
    language = "+".join(available_languages) or "eng"
    pages = []
    for image in images:
        try:
            # Receipts use small grey text and bank logos. A second,
            # high-contrast pass with a different page segmentation mode
            # recovers bank names that a single OCR pass commonly misses.
            prepared = ImageOps.autocontrast(ImageOps.grayscale(image))
            prepared = ImageEnhance.Contrast(prepared).enhance(1.6)
            if max(prepared.size) < 1800:
                scale = 1800 / max(prepared.size)
                prepared = prepared.resize(
                    (int(prepared.width * scale), int(prepared.height * scale))
                )
            candidates = [
                pytesseract.image_to_string(image, lang=language, config="--psm 6"),
                pytesseract.image_to_string(prepared, lang=language, config="--psm 11"),
            ]
            # Preserve all useful OCR lines; parse_receipt_text deduplicates
            # fields while the original text remains available to the admin.
            pages.append("\n".join(text for text in candidates if text.strip()))
        except Exception:
            # Try each installed language before giving up. This keeps Cyrillic
            # receipts working when only one of ukr/rus is installed.
            try:
                page_text = ""
                for fallback_language in ("ukr", "rus", "eng"):
                    if installed_languages and fallback_language not in installed_languages:
                        continue
                    try:
                        page_text = pytesseract.image_to_string(
                            image,
                            lang=fallback_language,
                            config="--psm 6",
                        )
                        if page_text.strip():
                            break
                    except Exception:
                        continue
                if page_text:
                    pages.append(page_text)
                else:
                    raise RuntimeError("не знайдено доступну мову Tesseract")
            except Exception as exc:
                return {}, "", f"Tesseract не налаштований: {exc}"
    text = "\n".join(page for page in pages if page).strip()
    data = parse_receipt_text(text)
    return data, text, ""


def receipt_summary(data, error=""):
    if error:
        return f"⚠️ OCR: {esc(error)}"
    if not data:
        return "⚠️ Дані квитанції не розпізнано — перевірте файл вручну."
    fields = [
        ("№ квитанції", data.get("receipt_number")),
        ("Банк", data.get("bank")),
        ("Перевірка банку", data.get("bank_match")),
        ("Сума", data.get("amount")),
        ("Перевірка суми", data.get("amount_match")),
        ("Відправник", data.get("sender_name")),
        ("Одержувач", data.get("receiver_name")),
        ("Дата операції", data.get("operation_datetime")),
    ]
    visible = "\n".join(f"• {label}: <b>{esc(value)}</b>" for label, value in fields if value)
    return f"🧾 <b>{esc(data.get('ocr_status', 'Потрібна перевірка'))}</b>\n{visible or '• Поля не знайдені'}"


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


db = sqlite3.connect(DB_PATH, timeout=30)
db.row_factory = sqlite3.Row
# Keep the database durable across async handlers and Render restarts.
db.execute("PRAGMA busy_timeout=5000")
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA synchronous=FULL")
db.execute("PRAGMA foreign_keys=ON")

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
    referrer_id INTEGER,
    referral_earned_stars INTEGER DEFAULT 0,
    language_code TEXT DEFAULT '',
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

CREATE TABLE IF NOT EXISTS receipt_archive (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    receipt_file_id TEXT NOT NULL,
    receipt_type TEXT,
    receipt_file_name TEXT,
    receipt_ocr_text TEXT,
    receipt_data_json TEXT,
    receipt_parsed_at TEXT,
    receipt_error TEXT,
    created_at TEXT NOT NULL
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

CREATE TABLE IF NOT EXISTS raffles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_stars INTEGER NOT NULL,
    pool_stars INTEGER NOT NULL DEFAULT 0,
    rules TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    winner_id INTEGER,
    prize_stars INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS raffle_entries (
    raffle_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    joined_at TEXT NOT NULL,
    PRIMARY KEY (raffle_id, user_id)
);

CREATE TABLE IF NOT EXISTS raffle_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raffle_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    purchased_stars INTEGER NOT NULL,
    contributed_stars INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (raffle_id, order_id)
);

CREATE TABLE IF NOT EXISTS raffle_consents (
    raffle_id INTEGER NOT NULL,
    order_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('accepted','declined')),
    created_at TEXT NOT NULL,
    PRIMARY KEY (raffle_id, order_id)
);

CREATE TABLE IF NOT EXISTS referral_rewards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL UNIQUE,
    referrer_id INTEGER NOT NULL,
    referred_user_id INTEGER NOT NULL,
    purchased_stars INTEGER NOT NULL,
    bonus_stars INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
""")

def ensure_column(table: str, column: str, definition: str):
    cols = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        db.commit()


ensure_column("orders", "nft_id", "INTEGER")
ensure_column("orders", "receipt_ocr_text", "TEXT")
ensure_column("orders", "receipt_data_json", "TEXT")
ensure_column("orders", "receipt_parsed_at", "TEXT")
ensure_column("orders", "receipt_error", "TEXT")
ensure_column("nfts", "sticker_file_id", "TEXT")
ensure_column("nfts", "sticker_type", "TEXT")
ensure_column("nfts", "custom_emoji_id", "TEXT")
ensure_column("ui_messages", "screen_key", "TEXT")
ensure_column("users", "referrer_id", "INTEGER")
ensure_column("users", "referral_earned_stars", "INTEGER DEFAULT 0")
ensure_column("users", "language_code", "TEXT DEFAULT ''")

# Preserve receipts saved by an earlier version before the archive table
# existed. This migration is idempotent for each order/file pair.
db.execute(
    """INSERT INTO receipt_archive(
           order_id,user_id,receipt_file_id,receipt_type,receipt_ocr_text,
           receipt_data_json,receipt_parsed_at,receipt_error,created_at
       )
       SELECT orders.id,orders.user_id,orders.receipt_file_id,orders.receipt_type,
              orders.receipt_ocr_text,orders.receipt_data_json,
              orders.receipt_parsed_at,orders.receipt_error,
              COALESCE(orders.receipt_parsed_at, orders.created_at)
       FROM orders
       WHERE orders.receipt_file_id IS NOT NULL
         AND NOT EXISTS (
             SELECT 1
             FROM receipt_archive
             WHERE receipt_archive.order_id=orders.id
               AND receipt_archive.receipt_file_id=orders.receipt_file_id
         )"""
)
db.commit()

DEFAULTS = {
    "stars_rate": "0.73",
    "ton_rate": "66.71",
    "min_withdraw": "50",
    "support": SUPPORT_USERNAME,
    "reviews_url": REVIEWS_URL,
    # This is a reporting checkpoint, not a data deletion flag. Resetting
    # statistics keeps users, orders and receipts intact.
    "stats_reset_at": "",
    # This is an archive checkpoint, not a data deletion flag. Resetting the
    # receipts screen keeps the source records available in the database.
    "receipts_reset_at": "",
    "required_channels": REQUIRED_CHANNELS,
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
            (user.id, user.username, user.first_name, now()),
        )
    else:
        db.execute(
            "UPDATE users SET username=?, first_name=? WHERE id=?",
            (user.username, user.first_name, user.id),
        )
    db.commit()


def user_row(uid):
    return db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()


LANGUAGE_NAMES = {
    "uk": "Українська",
    "ru": "Русский",
    "en": "English",
}

MENU_LABELS = {
    "buy_stars": {
        "uk": "Купити Stars",
        "ru": "Купить Stars",
        "en": "Buy Stars",
    },
    "buy_ton": {
        "uk": "Купити TON",
        "ru": "Купить TON",
        "en": "Buy TON",
    },
    "nft": {"uk": "NFT", "ru": "NFT", "en": "NFT"},
    "withdraw_stars": {
        "uk": "Вивести Stars",
        "ru": "Вывести Stars",
        "en": "Withdraw Stars",
    },
    "sell_stars": {
        "uk": "Продати Stars",
        "ru": "Продать Stars",
        "en": "Sell Stars",
    },
    "profile": {"uk": "Профіль", "ru": "Профиль", "en": "Profile"},
    "calculator": {
        "uk": "Калькулятор",
        "ru": "Калькулятор",
        "en": "Calculator",
    },
    "reviews": {"uk": "Відгуки", "ru": "Отзывы", "en": "Reviews"},
    "support": {"uk": "Підтримка", "ru": "Поддержка", "en": "Support"},
}


def user_language(uid):
    row = user_row(uid)
    language = row["language_code"] if row else ""
    return language if language in LANGUAGE_NAMES else "uk"


def menu_text(key, language):
    return MENU_LABELS[key].get(language, MENU_LABELS[key]["uk"])


def parse_required_channels(raw_value=None):
    raw = setting("required_channels") if raw_value is None else raw_value
    channels = []
    for item in re.split(r"[\n,;]+", raw or ""):
        item = item.strip()
        if not item:
            continue
        parts = [part.strip() for part in item.split("|", 2)]
        chat_id = parts[0]
        url = ""
        title = chat_id
        if len(parts) > 1:
            url = parts[1]
        if len(parts) > 2 and parts[2]:
            title = parts[2]
        if chat_id.startswith(("https://t.me/", "http://t.me/")):
            url = chat_id
            chat_id = chat_id.rstrip("/").rsplit("/", 1)[-1]
            if not chat_id.startswith("@"):
                chat_id = f"@{chat_id.split('+', 1)[0]}"
        elif chat_id.startswith("t.me/"):
            url = f"https://{chat_id}"
            chat_id = chat_id.rstrip("/").rsplit("/", 1)[-1]
            if not chat_id.startswith("@"):
                chat_id = f"@{chat_id.split('+', 1)[0]}"
        elif chat_id.startswith("@") and not url:
            url = f"https://t.me/{chat_id[1:]}"
        channels.append({"chat_id": chat_id, "url": url, "title": title})
    return channels


def serialize_required_channels(channels):
    return "\n".join(
        f"{channel['chat_id']}|{channel['url']}|{channel['title']}"
        for channel in channels
    )


def referral_start_id(raw_text):
    match = re.match(r"^/start(?:@\w+)?(?:\s+(.+))?$", raw_text or "", re.IGNORECASE)
    payload = (match.group(1) or "").strip() if match else ""
    if payload.startswith("ref_") and payload[4:].isdigit():
        return int(payload[4:])
    return None


def register_referral(user_id, referrer_id):
    if not referrer_id or referrer_id == user_id:
        return False
    ensure_user_referrer = db.execute(
        "SELECT referrer_id FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not ensure_user_referrer or ensure_user_referrer["referrer_id"]:
        return False
    if not user_row(referrer_id):
        return False
    db.execute(
        "UPDATE users SET referrer_id=? WHERE id=? AND referrer_id IS NULL",
        (referrer_id, user_id),
    )
    db.execute(
        "UPDATE users SET invited=invited+1 WHERE id=?",
        (referrer_id,),
    )
    db.commit()
    return True


def referral_link(username, user_id):
    if not username:
        return f"https://t.me/?start=ref_{user_id}"
    return f"https://t.me/{username.lstrip('@')}?start=ref_{user_id}"


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


def credit_referral_bonus(order_id, buyer_id, purchased_stars):
    buyer = db.execute(
        "SELECT referrer_id FROM users WHERE id=?", (buyer_id,)
    ).fetchone()
    referrer_id = buyer["referrer_id"] if buyer else None
    if not referrer_id or referrer_id == buyer_id:
        return None, 0
    bonus_stars = int(purchased_stars) * 10 // 100
    if bonus_stars <= 0:
        return None, 0
    cur = db.execute(
        """INSERT OR IGNORE INTO referral_rewards(
               order_id,referrer_id,referred_user_id,purchased_stars,
               bonus_stars,created_at
           ) VALUES(?,?,?,?,?,?)""",
        (
            order_id,
            referrer_id,
            buyer_id,
            int(purchased_stars),
            bonus_stars,
            now(),
        ),
    )
    if cur.rowcount == 0:
        return referrer_id, 0
    db.execute(
        """UPDATE users
           SET balance_stars=balance_stars+?,
               referral_earned_stars=referral_earned_stars+?
           WHERE id=?""",
        (bonus_stars, bonus_stars, referrer_id),
    )
    return referrer_id, bonus_stars


def active_raffle():
    return db.execute(
        "SELECT * FROM raffles WHERE status='active' ORDER BY id DESC LIMIT 1"
    ).fetchone()


def current_raffle():
    return db.execute(
        "SELECT * FROM raffles WHERE status IN ('active','ready') ORDER BY id DESC LIMIT 1"
    ).fetchone()


def raffle_fee(stars: int) -> int:
    """Round 3% of an integer Stars purchase to the nearest whole Star."""
    return (max(0, int(stars)) * 3 + 50) // 100


def record_raffle_contribution(raffle_id: int, order_id: int, user_id: int, purchased_stars: int):
    fee = raffle_fee(purchased_stars)
    cur = db.execute(
        """INSERT OR IGNORE INTO raffle_contributions
           (raffle_id,order_id,user_id,purchased_stars,contributed_stars,created_at)
           VALUES(?,?,?,?,?,?)""",
        (raffle_id, order_id, user_id, purchased_stars, fee, now()),
    )
    if cur.rowcount == 0:
        return 0

    db.execute(
        "UPDATE raffles SET pool_stars=pool_stars+? WHERE id=? AND status='active'",
        (fee, raffle_id),
    )
    raffle = db.execute("SELECT target_stars,pool_stars,status FROM raffles WHERE id=?", (raffle_id,)).fetchone()
    if raffle and raffle["status"] == "active" and raffle["pool_stars"] >= raffle["target_stars"]:
        db.execute("UPDATE raffles SET status='ready' WHERE id=? AND status='active'", (raffle_id,))
    return fee


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


def main_menu(language="uk"):
    language = language if language in LANGUAGE_NAMES else "uk"
    rows = [
        [
            reply_button(menu_text("buy_stars", language), emoji_id=MAIN_EMOJI["buy_stars"], style="danger"),
            reply_button(menu_text("buy_ton", language), emoji_id=MAIN_EMOJI["buy_gram"], style="danger"),
            reply_button(menu_text("nft", language), emoji_id=MAIN_EMOJI["nft"], style="danger"),
        ],
        [
            reply_button(menu_text("withdraw_stars", language), emoji_id=MAIN_EMOJI["withdraw_stars"], style="success"),
            reply_button(menu_text("sell_stars", language), emoji_id=MAIN_EMOJI["sell_stars"], style="success"),
            reply_button(menu_text("profile", language), emoji_id=MAIN_EMOJI["profile"], style="success"),
        ],
        [
            reply_button(menu_text("calculator", language), emoji_id=MAIN_EMOJI["calculator"], style="primary"),
            reply_button(menu_text("reviews", language), emoji_id=MAIN_EMOJI["reviews"], style="primary"),
            reply_button(menu_text("support", language), emoji_id=MAIN_EMOJI["support"], style="primary"),
        ],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


ASSET_DIRS = (
    PROJECT_DIR / "assets",
    PROJECT_DIR / "attached_assets",
)

SCREEN_IMAGES = {
    "welcome": "0DAC8ABF-4E80-4DAC-9765-68EBFE20BAD1_1790276163145.png",
    "stars": "8F1E5F14-6C85-481A-89C0-CB8DDB51C6E7_1790276163149.png",
    "ton": "CBAC6203-7823-4978-B81E-835F062AFBAE_1790276163149.png",
    "nft": "IMG_0464_1790276163150.jpeg",
    "sell": "IMG_0465_1790276163150.jpeg",
    "support": "IMG_0466_1790276163150.jpeg",
    "withdraw": "IMG_0467_1790276163150.jpeg",
    "calculator": "IMG_0468_1790276163150.jpeg",
    "reviews": "IMG_0469_1790276163150.jpeg",
}


def find_asset(image_name):
    if not image_name:
        return None
    for asset_dir in ASSET_DIRS:
        exact_path = asset_dir / image_name
        if exact_path.is_file():
            return exact_path
        # GitHub exports may preserve the asset UUID but change the timestamp suffix.
        prefix = image_name.split("_", 1)[0]
        matches = sorted(asset_dir.glob(f"{prefix}_*"))
        if matches:
            return matches[0]
    return None


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
    image_path = find_asset(image_name)
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


def language_kb():
    b = InlineKeyboardBuilder()
    for code, title in LANGUAGE_NAMES.items():
        b.row(kb_button(title, emoji_id=EMOJI_POOL[0], style="primary", callback_data=f"lang:{code}"))
    return b.as_markup()


def subscription_kb():
    b = InlineKeyboardBuilder()
    for channel in parse_required_channels():
        if channel["url"]:
            b.row(kb_button(
                f"Підписатися: {channel['title']}",
                emoji_id=EMOJI_POOL[0],
                style="primary",
                url=channel["url"],
            ))
    b.row(kb_button(
        "✅ Перевірити підписку",
        emoji_id=EMOJI_POOL[5],
        style="success",
        callback_data="subscription:check",
    ))
    return b.as_markup()


def subscription_gate_text():
    channels = parse_required_channels()
    channel_lines = "\n".join(f"• {esc(channel['title'])}" for channel in channels)
    return (
        "🔒 <b>Спочатку підпишіться на наші Telegram-канали</b>\n\n"
        f"{channel_lines}\n\n"
        "Після підписки натисніть «Перевірити підписку»."
    )


async def is_user_subscribed(user_id, bot_instance=None):
    channels = parse_required_channels()
    if not channels:
        return True
    bot_instance = bot_instance or bot
    for channel in channels:
        try:
            member = await bot_instance.get_chat_member(channel["chat_id"], user_id)
            if member.status not in ("creator", "administrator", "member") and not (
                member.status == "restricted" and member.is_member
            ):
                return False
        except Exception as error:
            # A missing admin permission must fail closed: users should not
            # get access when Telegram cannot verify the channel membership.
            print(
                f"Subscription check failed for {channel['chat_id']}: "
                f"{type(error).__name__}: {error}",
                flush=True,
            )
            return False
    return True


async def show_subscription_gate(user_id):
    await replace_screen(
        user_id,
        subscription_gate_text(),
        image="welcome",
        reply_markup=subscription_kb(),
        screen_key="subscription_gate",
    )


async def show_language_picker(user_id):
    await replace_screen(
        user_id,
        "🌐 <b>Оберіть мову інтерфейсу / Choose interface language</b>",
        image="welcome",
        reply_markup=language_kb(),
        screen_key="language_picker",
    )


async def show_welcome(user_id):
    language = user_language(user_id)
    welcome_text = {
        "uk": (
            f"{pe(WELCOME_EMOJI['stars'], '⭐')} <b>Вітаємо у {BOT_NAME}!</b>\n\n"
            f"{pe(WELCOME_EMOJI['stars'], '⭐')} Купуйте Stars\n"
            f"{pe(WELCOME_EMOJI['ton'], '🪙')} Купуйте TON\n"
            f"{pe(WELCOME_EMOJI['fire'], '🔥')} Обирайте NFT та інші цифрові товари\n\n"
            "Швидко, зручно та без зайвих кроків.\n\n"
            "Оберіть потрібний розділ нижче 👇"
        ),
        "ru": (
            f"{pe(WELCOME_EMOJI['stars'], '⭐')} <b>Добро пожаловать в {BOT_NAME}!</b>\n\n"
            "⭐ Покупайте Stars\n🪙 Покупайте TON\n🔥 Выбирайте NFT и другие цифровые товары\n\n"
            "Быстро, удобно и без лишних шагов.\n\nВыберите нужный раздел ниже 👇"
        ),
        "en": (
            f"{pe(WELCOME_EMOJI['stars'], '⭐')} <b>Welcome to {BOT_NAME}!</b>\n\n"
            "⭐ Buy Stars\n🪙 Buy TON\n🔥 Choose NFTs and other digital goods\n\n"
            "Fast, convenient and simple.\n\nChoose a section below 👇"
        ),
    }[language]
    await replace_screen(
        user_id,
        welcome_text,
        image="welcome",
        reply_markup=main_menu(language),
    )


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
    for name, code, _ in BANK_OPTIONS:
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


def raffle_consent_kb(raffle_id, order_id):
    b = InlineKeyboardBuilder()
    b.row(kb_button(
        "Так, внести 3% з цього поповнення",
        emoji_id=EMOJI_POOL[0],
        style="success",
        callback_data=f"raffle_consent:{raffle_id}:{order_id}:yes",
    ))
    b.row(kb_button(
        "Відмовитись",
        emoji_id=EMOJI_POOL[3],
        style="danger",
        callback_data=f"raffle_consent:{raffle_id}:{order_id}:no",
    ))
    return b.as_markup()


def raffle_admin_kb(raffle):
    b = InlineKeyboardBuilder()
    if not raffle:
        b.row(kb_button("Створити розіграш", emoji_id=EMOJI_POOL[0], style="success", callback_data="adm:raffle:create"))
    elif raffle["status"] == "ready":
        b.row(kb_button("Провести розіграш", emoji_id=EMOJI_POOL[0], style="success", callback_data=f"raffle:draw:{raffle['id']}"))
    else:
        b.row(kb_button("Оновити дані", emoji_id=EMOJI_POOL[27], style="primary", callback_data="adm:raffle"))
    b.row(back_inline("admin:back"))
    return b.as_markup()


def bank_details_kb():
    b = InlineKeyboardBuilder()
    for name, code, _ in BANK_OPTIONS:
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
        ("Розіграш", EMOJI_POOL[16], "success", "adm:raffle"),
        ("Баланс Stars", MAIN_EMOJI["buy_stars"], "primary", "adm:balance"),
        ("NFT", MAIN_EMOJI["nft"], "primary", "adm:nft"),
        ("Реквізити карток", EMOJI_POOL[3], "success", "adm:bank_details"),
        ("Розсилка", EMOJI_POOL[16], "primary", "adm:broadcast"),
        ("Підтримка", MAIN_EMOJI["support"], "success", "adm:support"),
        ("Канал відгуків", MAIN_EMOJI["reviews"], "primary", "adm:reviews"),
        ("Обов'язкова підписка", EMOJI_POOL[0], "success", "adm:channels"),
        ("Підтвердження оплат", EMOJI_POOL[16], "primary", "adm:orders"),
        ("Користувачі", EMOJI_POOL[3], "primary", "adm:users"),
        ("Статистика", EMOJI_POOL[27], "primary", "adm:stats"),
        ("Квитанції", EMOJI_POOL[5], "primary", "adm:receipts"),
    ]
    for text, eid, style, data in items:
        b.row(kb_button(text, emoji_id=eid, style=style, callback_data=data))
    return b.as_markup()


def required_channels_admin_kb():
    b = InlineKeyboardBuilder()
    for index, channel in enumerate(parse_required_channels()):
        b.row(kb_button(
            f"🗑 {channel['title']}",
            emoji_id=EMOJI_POOL[3],
            style="danger",
            callback_data=f"adm_channel_delete:{index}",
        ))
    b.row(kb_button(
        "➕ Додати канал",
        emoji_id=EMOJI_POOL[0],
        style="success",
        callback_data="adm:channels:add",
    ))
    b.row(back_inline("admin:back"))
    return b.as_markup()


def stats_kb():
    b = InlineKeyboardBuilder()
    b.row(kb_button("Оновити", emoji_id=EMOJI_POOL[27], style="primary", callback_data="adm:stats"))
    b.row(kb_button("Скинути статистику", emoji_id=EMOJI_POOL[3], style="danger", callback_data="adm:stats_reset"))
    b.row(back_inline("admin:back"))
    return b.as_markup()


def receipts_kb():
    b = InlineKeyboardBuilder()
    b.row(kb_button(
        "Вигрузити всі квитанції",
        emoji_id=EMOJI_POOL[5],
        style="success",
        callback_data="adm:receipts_export",
    ))
    b.row(kb_button(
        "Скинути архів квитанцій",
        emoji_id=EMOJI_POOL[3],
        style="danger",
        callback_data="adm:receipts_reset",
    ))
    b.row(back_inline("admin:back"))
    return b.as_markup()


def receipts_reset_confirm_kb():
    b = InlineKeyboardBuilder()
    b.row(kb_button(
        "Так, скинути архів",
        emoji_id=EMOJI_POOL[3],
        style="danger",
        callback_data="adm:receipts_reset_confirm",
    ))
    b.row(back_inline("adm:receipts"))
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
    raffle_target = State()
    raffle_rules = State()
    required_channel = State()


# The token is supplied through Replit Secrets. Keep Bot construction lazy so
# importing this module for checks or migrations does not fail before secrets
# have been configured.
bot: Bot | None = None
dp = Dispatcher()
_processed_start_messages: set[tuple[int, int]] = set()
_last_start_at: dict[int, float] = {}
START_DEDUP_SECONDS = 2.0


class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if not user or user.id in ADMIN_IDS:
            return await handler(event, data)

        callback_data = getattr(event, "data", "") or ""
        message_text = getattr(event, "text", "") or ""
        is_start = message_text.startswith("/start")
        is_subscription_flow = (
            callback_data == "subscription:check"
            or callback_data.startswith("lang:")
        )
        if is_start or is_subscription_flow:
            return await handler(event, data)

        bot_instance = data.get("bot") or bot
        if await is_user_subscribed(user.id, bot_instance):
            return await handler(event, data)

        if isinstance(event, CallbackQuery):
            await event.answer("Спочатку підпишіться на канал.", show_alert=True)
        await show_subscription_gate(user.id)
        return None


dp.message.outer_middleware(SubscriptionMiddleware())
dp.callback_query.outer_middleware(SubscriptionMiddleware())


@dp.errors()
async def ignore_forbidden_delivery(event: ErrorEvent):
    if isinstance(event.exception, TelegramForbiddenError):
        return True


async def notify_admins(
    text,
    reply_markup=None,
    photo=None,
    document=None,
    recipient_ids=None,
):
    delivered = 0
    for aid in ADMIN_IDS if recipient_ids is None else recipient_ids:
        try:
            if photo:
                await bot.send_photo(aid, photo=photo, caption=text, reply_markup=reply_markup)
            elif document:
                await bot.send_document(aid, document=document, caption=text, reply_markup=reply_markup)
            else:
                await bot.send_message(aid, text, reply_markup=reply_markup)
            delivered += 1
            print(f"Admin notification delivered for {aid}.", flush=True)
        except Exception as exc:
            # A file_id can occasionally fail while a plain message still
            # works. Never lose the payment request silently.
            print(f"Admin notification failed for {aid}: {exc}")
            if photo or document:
                try:
                    await bot.send_message(aid, text, reply_markup=reply_markup)
                    delivered += 1
                except Exception as fallback_exc:
                    print(f"Admin text notification failed for {aid}: {fallback_exc}")
    if not ADMIN_IDS:
        print("Admin notification skipped: ADMIN_IDS is empty.")
    return delivered


async def configure_bot_commands():
    await bot.set_my_commands(
        [BotCommand(command="start", description="Відкрити головне меню")],
        scope=BotCommandScopeAllPrivateChats(),
    )
    for aid in ADMIN_IDS:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Відкрити головне меню"),
                BotCommand(command="admin", description="Відкрити адмін-панель"),
            ],
            scope=BotCommandScopeChat(chat_id=aid),
        )


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    now = asyncio.get_running_loop().time()
    start_key = (message.chat.id, message.message_id)
    last_start = _last_start_at.get(message.chat.id)
    if start_key in _processed_start_messages or (
        last_start is not None and now - last_start < START_DEDUP_SECONDS
    ):
        print(
            f"Ignored duplicate /start from chat {message.chat.id}.",
            flush=True,
        )
        return
    _processed_start_messages.add(start_key)
    _last_start_at[message.chat.id] = now
    if len(_processed_start_messages) > 5000:
        _processed_start_messages.clear()
    ensure_user(message.from_user)
    await state.clear()
    register_referral(
        message.from_user.id,
        referral_start_id(message.text or ""),
    )
    if not await is_user_subscribed(message.from_user.id):
        await show_subscription_gate(message.from_user.id)
        return
    if not user_row(message.from_user.id)["language_code"]:
        await show_language_picker(message.from_user.id)
        return
    await show_welcome(message.from_user.id)


@dp.callback_query(F.data == "subscription:check")
async def check_subscription(call: CallbackQuery):
    await call.answer()
    if not await is_user_subscribed(call.from_user.id):
        await show_subscription_gate(call.from_user.id)
        return
    if not user_row(call.from_user.id)["language_code"]:
        await show_language_picker(call.from_user.id)
    else:
        await show_welcome(call.from_user.id)


@dp.callback_query(F.data.startswith("lang:"))
async def choose_language(call: CallbackQuery):
    language = call.data.split(":", 1)[1]
    if language not in LANGUAGE_NAMES:
        await call.answer("Невідома мова.", show_alert=True)
        return
    if not await is_user_subscribed(call.from_user.id):
        await call.answer("Спочатку підпишіться на канал.", show_alert=True)
        await show_subscription_gate(call.from_user.id)
        return
    db.execute(
        "UPDATE users SET language_code=? WHERE id=?",
        (language, call.from_user.id),
    )
    db.commit()
    await call.answer(f"Обрано: {LANGUAGE_NAMES[language]}")
    await show_welcome(call.from_user.id)


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


@dp.message(F.text.in_({"Скасувати", "❌ Скасувати", "Cancel", "Отмена"}))
async def cancel_state(message: Message, state: FSMContext):
    await state.clear()
    if message.from_user.id in ADMIN_IDS:
        delete_setting(f"pending_bank:{message.from_user.id}")
    await replace_screen(
        message.from_user.id,
        "✅ Дію скасовано.\n\nОберіть потрібний розділ нижче 👇",
        image="welcome",
        reply_markup=main_menu(user_language(message.from_user.id)),
    )


@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await replace_screen(
        call.from_user.id,
        "🏠 <b>Головне меню</b>\n\nОберіть потрібний розділ нижче 👇",
        image="welcome",
        reply_markup=main_menu(user_language(call.from_user.id)),
    )


@dp.message(F.text.in_(set(MENU_LABELS["buy_stars"].values())))
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
        stars = int((message.text or "").strip())
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
        await replace_screen(
            call.from_user.id,
            "❌ Замовлення не знайдено.",
            image="stars",
            reply_markup=main_menu(user_language(call.from_user.id)),
        )
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
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if (
        not order
        or order["user_id"] != call.from_user.id
        or order["status"] not in ("waiting_payment", "waiting_review")
    ):
        await replace_screen(
            call.from_user.id,
            "❌ Замовлення більше недоступне.",
            image="stars",
            reply_markup=main_menu(user_language(call.from_user.id)),
        )
        return
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
    if (
        not order
        or order["user_id"] != call.from_user.id
        or order["status"] not in ("waiting_payment", "waiting_review")
        or not order["payment_method"]
    ):
        await replace_screen(
            call.from_user.id,
            "❌ Спочатку оберіть банк для цього замовлення.",
            image="stars",
            reply_markup=main_menu(user_language(call.from_user.id)),
        )
        return
    await state.update_data(receipt_order=oid)
    await state.set_state(Form.receipt)
    await replace_screen(
        call.from_user.id,
        "🧾 Надішліть фото або документ квитанції.",
        image="stars",
        reply_markup=cancel_kb(),
    )


async def save_receipt(
    message: Message,
    state: FSMContext,
    file_id: str,
    file_type: str,
    file_name: str = "",
):
    data = await state.get_data()
    oid = data.get("receipt_order")
    if not oid:
        await state.clear()
        return
    order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
    if (
        not order
        or order["user_id"] != message.from_user.id
        or order["status"] not in ("waiting_payment", "waiting_review")
    ):
        await state.clear()
        return

    receipt_data = {}
    ocr_text = ""
    receipt_error = ""
    suffix = Path(file_name or "").suffix.lower()
    if not suffix:
        suffix = ".jpg" if file_type == "photo" else ".bin"
    temp_path = None
    try:
        telegram_file = await bot.get_file(file_id)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
        await bot.download_file(telegram_file.file_path, destination=temp_path)
        receipt_data, ocr_text, receipt_error = await asyncio.to_thread(
            ocr_receipt_file,
            temp_path,
        )
    except Exception as exc:
        receipt_error = f"Не вдалося завантажити квитанцію для OCR: {exc}"
    finally:
        if temp_path:
            temp_path.unlink(missing_ok=True)

    if not receipt_data and receipt_error:
        receipt_data = {"ocr_status": "Потрібна перевірка"}
    if receipt_data:
        expected_method = order["payment_method"] or ""
        receipt_data["expected_bank"] = BANK_DISPLAY_NAMES.get(expected_method, "")
        receipt_data["bank_match"] = _bank_method_match(
            expected_method,
            receipt_data.get("bank", ""),
        )
        receipt_data["order_amount"] = f"{float(order['amount']):.2f}"
        receipt_data["amount_match"] = _amount_match(
            receipt_data.get("amount", ""),
            order["amount"],
        )
    parsed_at = now()
    db.execute(
        """UPDATE orders
           SET receipt_file_id=?,receipt_type=?,receipt_ocr_text=?,
               receipt_data_json=?,receipt_parsed_at=?,receipt_error=?,
               status='waiting_review'
           WHERE id=?""",
        (
            file_id,
            file_type,
            ocr_text,
            json.dumps(receipt_data, ensure_ascii=False),
            parsed_at,
            receipt_error,
            oid,
        ),
    )
    db.execute(
        """INSERT INTO receipt_archive(
               order_id,user_id,receipt_file_id,receipt_type,receipt_file_name,
               receipt_ocr_text,receipt_data_json,receipt_parsed_at,
               receipt_error,created_at
           ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            oid,
            order["user_id"],
            file_id,
            file_type,
            file_name,
            ocr_text,
            json.dumps(receipt_data, ensure_ascii=False),
            parsed_at,
            receipt_error,
            parsed_at,
        ),
    )
    db.commit()
    await state.clear()
    await replace_screen(
        message.from_user.id,
        f"{pe(EMOJI_POOL[5], '✅')} Квитанцію отримано.\n"
        f"📦 Замовлення #{oid} передано на перевірку.",
        image="stars",
        reply_markup=main_menu(user_language(message.from_user.id)),
    )
    u = user_row(message.from_user.id)
    text = (
        f"🔔 <b>Нове замовлення #{oid}</b>\n\n"
        f"👤 @{esc(u['username'] or 'без_username')}\n"
        f"🆔 <code>{u['id']}</code>\n"
        f"📦 {esc(order['order_type'])}: <b>{esc(order['quantity'])}</b>\n"
        f"💰 <b>{order['amount']:.2f} грн</b>\n"
        f"💳 {esc(order['payment_method'] or '—')}\n"
        f"🕒 {order['created_at']}\n\n"
        f"{receipt_summary(receipt_data, receipt_error)}"
    )
    sender_is_admin = message.from_user.id in ADMIN_IDS
    other_admin_ids = ADMIN_IDS - {message.from_user.id} if sender_is_admin else None
    if file_type == "photo":
        delivered = await notify_admins(
            text,
            admin_order_kb(oid),
            photo=file_id,
            recipient_ids=other_admin_ids,
        )
    else:
        delivered = await notify_admins(
            text,
            admin_order_kb(oid),
            document=file_id,
            recipient_ids=other_admin_ids,
        )
    if sender_is_admin:
        try:
            if file_type == "photo":
                await bot.send_photo(
                    message.from_user.id,
                    photo=file_id,
                    caption=text,
                    reply_markup=admin_order_kb(oid),
                )
            else:
                await bot.send_document(
                    message.from_user.id,
                    document=file_id,
                    caption=text,
                    reply_markup=admin_order_kb(oid),
                )
            delivered += 1
            print(
                f"Admin notification delivered directly to sender {message.from_user.id}.",
                flush=True,
            )
        except Exception as exc:
            print(
                f"Direct admin notification failed for {message.from_user.id}: {exc}",
                flush=True,
            )
    if not delivered:
        await message.answer(
            "⚠️ Квитанцію збережено, але повідомлення адміністратору не доставлено.\n"
            "Перевірте, що ваш Telegram ID доданий у ADMIN_IDS, а адмін відкрив боту "
            "та натиснув /start.",
            reply_markup=main_menu(user_language(message.from_user.id)),
        )


@dp.message(Form.receipt, F.photo)
async def receipt_photo(message: Message, state: FSMContext):
    await save_receipt(message, state, message.photo[-1].file_id, "photo")


@dp.message(Form.receipt, F.document)
async def receipt_document(message: Message, state: FSMContext):
    await save_receipt(
        message,
        state,
        message.document.file_id,
        "document",
        message.document.file_name or "",
    )


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
    if (
        not order
        or order["user_id"] != call.from_user.id
        or order["status"] not in ("waiting_payment", "waiting_review")
    ):
        return
    db.execute("UPDATE orders SET status='cancelled' WHERE id=?", (oid,))
    db.commit()
    await replace_screen(
        call.from_user.id,
        "❌ Дію скасовано.\n\nОберіть потрібний розділ нижче 👇",
        image="welcome",
        reply_markup=main_menu(user_language(call.from_user.id)),
    )


@dp.message(F.text.in_({"Купити Gram", *MENU_LABELS["buy_ton"].values()}))
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


@dp.message(F.text.in_(set(MENU_LABELS["withdraw_stars"].values())))
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
            reply_markup=main_menu(user_language(message.from_user.id)),
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
        reply_markup=main_menu(user_language(message.from_user.id)),
    )
    await notify_admins(
        f"📤 <b>Запит на вивід #{oid}</b>\n"
        f"👤 @{esc(message.from_user.username or 'без_username')}\n"
        f"🆔 <code>{message.from_user.id}</code>\n"
        f"⭐ Кількість: <b>{amount}</b>",
        admin_order_kb(oid),
    )


@dp.message(F.text.in_(set(MENU_LABELS["sell_stars"].values())))
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
        reply_markup=main_menu(user_language(message.from_user.id)),
    )


@dp.message(F.text.in_(set(MENU_LABELS["nft"].values())))
async def nft_list(message: Message):
    rows = db.execute("SELECT * FROM nfts WHERE active=1 ORDER BY id DESC").fetchall()
    if not rows:
        await replace_screen(
            message.from_user.id,
            "🎁 Наразі доступних NFT немає.",
            image="nft",
            reply_markup=main_menu(user_language(message.from_user.id)),
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
            reply_markup=main_menu(user_language(call.from_user.id)),
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


@dp.message(F.text.in_(set(MENU_LABELS["profile"].values())))
async def profile(message: Message):
    ensure_user(message.from_user)
    u = user_row(message.from_user.id)
    bot_info = await bot.get_me()
    user_referral_link = referral_link(bot_info.username, u["id"])
    await replace_screen(
        message.from_user.id,
        f"{pe(MAIN_EMOJI['profile'], '👤')} <b>Ваш профіль</b>\n\n"
        f"🆔 ID: <code>{u['id']}</code>\n"
        f"👤 Username: @{esc(u['username'] or '—')}\n"
        f"⭐ Баланс: <b>{u['balance_stars']} Stars</b>\n"
        f"📊 Статус: <b>{esc(u['status'])}</b>\n"
        f"⭐ Придбано Stars: {u['bought_stars']}\n"
        f"💎 Придбано TON: {u['bought_ton']}\n"
        f"💰 Витрачено: {u['spent_uah']:.2f} грн\n"
        f"👥 Запрошено друзів: {u['invited']}\n"
        f"🎁 Зароблено з рефералів: <b>{u['referral_earned_stars']} Stars</b>\n\n"
        f"🔗 <b>Ваша реферальна ссылка:</b>\n<code>{esc(user_referral_link)}</code>\n"
        "Отправьте её друзьям: вы получите 10% Stars с их подтверждённых покупок.\n"
        f"📅 Дата реєстрації: <b>{u['registered_at']}</b>",
        image="welcome",
        reply_markup=main_menu(user_language(message.from_user.id)),
    )


@dp.message(F.text.in_(set(MENU_LABELS["calculator"].values())))
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
        reply_markup=main_menu(user_language(message.from_user.id)),
    )


@dp.message(F.text.in_(set(MENU_LABELS["reviews"].values())))
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


@dp.message(F.text.in_(set(MENU_LABELS["support"].values())))
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
        reply_markup=main_menu(user_language(message.from_user.id)),
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


@dp.callback_query(F.data == "adm:raffle")
async def adm_raffle(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    await call.answer()
    raffle = current_raffle()
    if not raffle:
        text = (
            "🎁 <b>Розіграші</b>\n\n"
            "Активного розіграшу зараз немає.\n"
            "Створіть його, задайте ціль у Stars і напишіть умови."
        )
    else:
        entries = db.execute(
            "SELECT COUNT(*) AS total FROM raffle_entries WHERE raffle_id=?",
            (raffle["id"],),
        ).fetchone()["total"]
        status_text = "Ціль досягнута — можна проводити розіграш." if raffle["status"] == "ready" else "Набираються внески."
        text = (
            f"🎁 <b>Розіграш #{raffle['id']}</b>\n\n"
            f"📊 Статус: {status_text}\n"
            f"⭐ Пул: <b>{raffle['pool_stars']} / {raffle['target_stars']} Stars</b>\n"
            f"👥 Учасників: <b>{entries}</b>\n\n"
            f"📜 <b>Умови:</b>\n{esc(raffle['rules'])}"
        )
    await call.message.edit_text(text, reply_markup=raffle_admin_kb(raffle))


@dp.callback_query(F.data == "adm:raffle:create")
async def raffle_create_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    if current_raffle():
        await call.answer("Спочатку завершіть поточний розіграш.", show_alert=True)
        return
    await call.answer()
    await state.set_state(Form.raffle_target)
    await call.message.answer(
        "🎁 <b>Новий розіграш</b>\n\n"
        "Введіть ціль пулу в цілих Stars. Коли внески досягнуть цієї суми, "
        "у меню з'явиться кнопка для випадкового вибору переможця.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.raffle_target)
async def raffle_target_entered(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    try:
        target = int((message.text or "").strip())
        if target < 1 or target > 100_000_000:
            raise ValueError
    except (ValueError, TypeError):
        await message.answer("❌ Введіть ціле число Stars від 1 до 100 000 000.")
        return
    await state.update_data(raffle_target=target)
    await state.set_state(Form.raffle_rules)
    await message.answer(
        "📜 Надішліть умови участі одним повідомленням.\n"
        "Надішліть <code>-</code>, щоб використати стандартні умови.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.raffle_rules)
async def raffle_rules_entered(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    rules = (message.text or "").strip()
    if rules == "-":
        rules = (
            "Участь добровільна. Один запис на користувача. "
            "Після кожного підтвердженого поповнення Stars бот окремо запитує згоду. "
            "Лише після натискання кнопки згоди 3% саме з цього поповнення "
            "(округлення до цілої Stars) надходять у спільний пул. "
            "Відмова не списує Stars. "
            "Після досягнення цілі адмін проводить випадковий розіграш. "
            "Переможець отримує весь пул Stars на баланс."
        )
    if not rules or len(rules) > 3000:
        await message.answer("❌ Умови мають містити до 3000 символів.")
        return
    data = await state.get_data()
    target = int(data.get("raffle_target", 0))
    if current_raffle():
        await state.clear()
        await message.answer(
            "❌ Інший розіграш уже активний. Спочатку завершіть його.",
            reply_markup=admin_menu_kb(),
        )
        return
    cur = db.execute(
        """INSERT INTO raffles(target_stars,pool_stars,rules,status,created_by,created_at)
           VALUES(?,0,?,'active',?,?)""",
        (target, rules, message.from_user.id, now()),
    )
    db.commit()
    raffle_id = cur.lastrowid
    await state.clear()
    await message.answer(
        f"✅ <b>Розіграш #{raffle_id} створено</b>\n"
        f"🎯 Ціль: <b>{target} Stars</b>\n"
        "Запрошення надсилатиметься після підтвердження поповнення Stars.",
        reply_markup=raffle_admin_kb(current_raffle()),
    )


def raffle_consent_text(raffle, order, user_id):
    already_entered = db.execute(
        "SELECT 1 FROM raffle_entries WHERE raffle_id=? AND user_id=?",
        (raffle["id"], user_id),
    ).fetchone()
    contribution = raffle_fee(int(order["quantity"]))
    if already_entered:
        intro = (
            "Ви вже маєте один квиток у цьому розіграші. "
            "Вирішіть, чи внести 3% саме з цього поповнення."
        )
        refusal = "Якщо відмовитесь, ваш квиток залишиться, але з цього поповнення нічого не спишеться."
    else:
        intro = "Згода оформить вам один квиток у цьому розіграші."
        refusal = "Якщо відмовитесь, ви не будете додані до учасників і списання не буде."
    return (
        f"🎁 <b>Внесок у розіграш #{raffle['id']} з поповнення #{order['id']}?</b>\n\n"
        f"{esc(intro)}\n"
        f"⭐ Згода спише <b>{contribution} Stars</b> — 3% саме з поповнення "
        f"на {int(order['quantity'])} Stars, округлено до цілої Stars.\n"
        f"🔁 Для кожного наступного поповнення бот запитає дозвіл окремо.\n"
        f"↩️ {esc(refusal)}\n\n"
        f"🎯 Ціль пулу: <b>{raffle['target_stars']} Stars</b>\n"
        f"📜 <b>Умови:</b>\n{esc(raffle['rules'])}"
    )


@dp.callback_query(F.data.startswith("raffle_consent:"))
async def raffle_consent(call: CallbackQuery):
    try:
        _, raffle_s, order_s, decision = call.data.split(":")
        raffle_id, order_id = int(raffle_s), int(order_s)
    except (AttributeError, TypeError, ValueError):
        await call.answer("Не вдалося перевірити відповідь.", show_alert=True)
        return

    if decision not in {"yes", "no"} or not call.from_user:
        await call.answer("Некоректна відповідь.", show_alert=True)
        return

    contribution = 0
    already_contributed = False
    already_entered = False
    try:
        db.execute("BEGIN IMMEDIATE")
        raffle = db.execute("SELECT * FROM raffles WHERE id=?", (raffle_id,)).fetchone()
        order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if (
            not raffle
            or raffle["status"] not in {"active", "ready", "completed"}
            or not order
            or order["user_id"] != call.from_user.id
            or order["order_type"] != "buy_stars"
            or order["status"] != "completed"
        ):
            db.rollback()
            await call.answer("Не вдалося перевірити це поповнення або розіграш.", show_alert=True)
            return

        previous_response = db.execute(
            "SELECT decision FROM raffle_consents WHERE raffle_id=? AND order_id=?",
            (raffle_id, order_id),
        ).fetchone()
        if previous_response:
            db.rollback()
            await call.answer("Відповідь для цього поповнення вже збережена.", show_alert=True)
            return

        if decision == "no":
            db.execute(
                """INSERT INTO raffle_consents(raffle_id,order_id,user_id,decision,created_at)
                   VALUES(?,?,?,'declined',?)""",
                (raffle_id, order_id, call.from_user.id, now()),
            )
            db.commit()
        else:
            if raffle["status"] != "active":
                db.rollback()
                await call.answer("Цей розіграш уже не приймає внески.", show_alert=True)
                return

            prior_contribution = db.execute(
                "SELECT contributed_stars FROM raffle_contributions WHERE raffle_id=? AND order_id=?",
                (raffle_id, order_id),
            ).fetchone()
            already_contributed = prior_contribution is not None
            contribution = int(prior_contribution["contributed_stars"]) if prior_contribution else raffle_fee(
                int(order["quantity"])
            )
            entered = db.execute(
                "SELECT 1 FROM raffle_entries WHERE raffle_id=? AND user_id=?",
                (raffle_id, call.from_user.id),
            ).fetchone()
            already_entered = entered is not None
            if not entered:
                db.execute(
                    "INSERT INTO raffle_entries(raffle_id,user_id,joined_at) VALUES(?,?,?)",
                    (raffle_id, call.from_user.id, now()),
                )

            if not already_contributed:
                cursor = db.execute(
                    "UPDATE users SET balance_stars=balance_stars-? WHERE id=? AND balance_stars>=?",
                    (contribution, call.from_user.id, contribution),
                )
                if cursor.rowcount != 1:
                    db.rollback()
                    await call.answer(
                        "На балансі недостатньо Stars. Нічого не списано.",
                        show_alert=True,
                    )
                    return
                recorded = record_raffle_contribution(
                    raffle_id,
                    order_id,
                    call.from_user.id,
                    int(order["quantity"]),
                )
                if recorded != contribution:
                    raise RuntimeError("Raffle contribution could not be recorded exactly once")

            db.execute(
                """INSERT INTO raffle_consents(raffle_id,order_id,user_id,decision,created_at)
                   VALUES(?,?,?,'accepted',?)""",
                (raffle_id, order_id, call.from_user.id, now()),
            )
            db.commit()
    except Exception:
        db.rollback()
        raise

    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    if decision == "no":
        await call.answer("Відмову збережено. 0 Stars списано.")
        await call.message.answer(
            f"✅ Ви відмовились від внеску з поповнення #{order_id}. "
            "Списання не було."
        )
        return

    updated_user = user_row(call.from_user.id)
    updated_raffle = db.execute("SELECT * FROM raffles WHERE id=?", (raffle_id,)).fetchone()
    if already_contributed:
        contribution_line = (
            f"Ці <b>{contribution} Stars</b> з цього поповнення вже були враховані раніше; "
            "повторного списання не було."
        )
    else:
        contribution_line = (
            f"До пулу додано <b>{contribution} Stars</b> з цього поповнення."
        )
    entry_line = "Ваш квиток збережено." if already_entered else "Ви отримали один квиток."
    await call.answer("Згоду збережено для цього поповнення.")
    await call.message.answer(
        f"🎟 <b>Згоду на внесок з поповнення #{order_id} збережено.</b>\n\n"
        f"{entry_line}\n"
        f"{contribution_line}\n"
        f"💳 Баланс: <b>{updated_user['balance_stars']} Stars</b>\n"
        f"🎁 Пул: <b>{updated_raffle['pool_stars']} / "
        f"{updated_raffle['target_stars']} Stars</b>\n\n"
        "Наступного разу бот знову окремо запитає ваш дозвіл."
    )


@dp.callback_query(F.data.startswith("raffle_join:"))
async def refresh_legacy_raffle_invite(call: CallbackQuery):
    try:
        _, raffle_s, order_s = call.data.split(":")
        raffle_id, order_id = int(raffle_s), int(order_s)
    except (AttributeError, TypeError, ValueError):
        await call.answer("Це старе запрошення більше не діє.", show_alert=True)
        return

    raffle = db.execute("SELECT * FROM raffles WHERE id=?", (raffle_id,)).fetchone()
    order = db.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if (
        not call.from_user
        or not raffle
        or raffle["status"] != "active"
        or not order
        or order["user_id"] != call.from_user.id
        or order["order_type"] != "buy_stars"
        or order["status"] != "completed"
    ):
        await call.answer("Це запрошення більше неактивне.", show_alert=True)
        return

    previous_contribution = db.execute(
        "SELECT contributed_stars FROM raffle_contributions WHERE raffle_id=? AND order_id=?",
        (raffle_id, order_id),
    ).fetchone()
    if previous_contribution:
        await call.answer(
            "Цей внесок уже врахований. Повторного списання не буде.",
            show_alert=True,
        )
        try:
            await call.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    await call.answer(
        "Умови оновлено: тепер кожне поповнення потребує окремої згоди.",
        show_alert=True,
    )
    await call.message.edit_text(
        raffle_consent_text(raffle, order, call.from_user.id),
        reply_markup=raffle_consent_kb(raffle_id, order_id),
    )


@dp.callback_query(F.data.startswith("raffle:draw:"))
async def raffle_draw(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        await call.answer("Немає доступу.", show_alert=True)
        return
    raffle_id = int(call.data.split(":")[2])
    await call.answer()

    try:
        db.execute("BEGIN IMMEDIATE")
        raffle = db.execute("SELECT * FROM raffles WHERE id=?", (raffle_id,)).fetchone()
        if not raffle or raffle["status"] != "ready" or raffle["pool_stars"] < raffle["target_stars"]:
            db.rollback()
            await call.message.answer("❌ Розіграш ще не досяг цілі або вже оброблений.")
            return
        participants = db.execute(
            "SELECT user_id FROM raffle_entries WHERE raffle_id=? ORDER BY joined_at,user_id",
            (raffle_id,),
        ).fetchall()
        if not participants:
            db.rollback()
            await call.message.answer("❌ У розіграші ще немає учасників.")
            return

        participant_ids = [int(row["user_id"]) for row in participants]
        winner_id = secrets.choice(participant_ids)
        prize_stars = int(raffle["pool_stars"])
        db.execute(
            "UPDATE users SET balance_stars=balance_stars+? WHERE id=?",
            (prize_stars, winner_id),
        )
        db.execute(
            """UPDATE raffles SET status='completed',winner_id=?,prize_stars=?,completed_at=?
               WHERE id=? AND status='ready'""",
            (winner_id, prize_stars, now(), raffle_id),
        )
        winner = user_row(winner_id)
        winner_balance = int(winner["balance_stars"])
        db.commit()
    except Exception:
        db.rollback()
        raise

    winner_label = f"@{winner['username']}" if winner["username"] else f"ID {winner_id}"
    await call.message.edit_text(
        f"🏆 <b>Розіграш #{raffle_id} завершено!</b>\n\n"
        f"Переможець: <b>{esc(winner_label)}</b>\n"
        f"Приз зараховано: <b>{prize_stars} Stars</b>\n"
        f"Учасників: <b>{len(participant_ids)}</b>",
        reply_markup=admin_menu_kb(),
    )
    try:
        await bot.send_message(
            winner_id,
            f"🎉 <b>Вітаємо! Ви перемогли в розіграші #{raffle_id}!</b>\n\n"
            f"⭐ На ваш баланс зараховано <b>{prize_stars} Stars</b>.\n"
            f"Поточний баланс: <b>{winner_balance} Stars</b>.",
            reply_markup=main_menu(),
        )
    except Exception:
        pass

    for participant_id in participant_ids:
        if participant_id == winner_id:
            continue
        try:
            await bot.send_message(
                participant_id,
                f"🏁 Розіграш #{raffle_id} завершено.\n"
                f"Переможець: <b>{esc(winner_label)}</b>.\n"
                f"Приз <b>{prize_stars} Stars</b> зараховано на його баланс.",
            )
        except Exception:
            pass


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
    value = (message.text or "").strip()
    if not re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value):
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


@dp.callback_query(F.data == "adm:channels")
async def adm_channels(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    channels = parse_required_channels()
    if channels:
        listing = "\n".join(
            f"• <b>{esc(channel['title'])}</b> — <code>{esc(channel['chat_id'])}</code>"
            for channel in channels
        )
    else:
        listing = "Поки що канали не додані."
    await call.message.answer(
        "🔒 <b>Обов'язкова підписка</b>\n\n"
        f"{listing}\n\n"
        "Бот перевіряє підписку через Telegram API. Для кожного каналу "
        "бот має бути адміністратором.",
        reply_markup=required_channels_admin_kb(),
    )


@dp.callback_query(F.data == "adm:channels:add")
async def adm_channels_add(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await state.set_state(Form.required_channel)
    await call.message.answer(
        "➕ <b>Додати канал для обов'язкової підписки</b>\n\n"
        "Надішліть одним повідомленням:\n"
        "• публічний: <code>@channel</code>\n"
        "• приватний: <code>-1001234567890|https://t.me/+invite|Назва</code>\n\n"
        "Для приватного каналу потрібні ID чату, посилання-запрошення та назва. "
        "Перед додаванням переконайтеся, що бот уже адміністратор.",
        reply_markup=cancel_kb(),
    )


@dp.message(Form.required_channel)
async def set_required_channel(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    raw_value = (message.text or "").strip()
    channels = parse_required_channels(raw_value)
    if len(channels) != 1:
        await message.answer(
            "❌ Не вдалося розпізнати канал. Використайте @username або "
            "ID|ссылка-приглашение|название."
        )
        return
    channel = channels[0]
    if not (
        channel["chat_id"].startswith("@")
        or re.fullmatch(r"-?\d+", channel["chat_id"])
    ):
        await message.answer("❌ ID каналу має починатися з @ або бути числовим.")
        return
    if not channel["url"]:
        await message.answer(
            "❌ Для цього каналу немає кнопки підписки. Додайте посилання "
            "https://t.me/... після ID через символ |."
        )
        return
    if any(item["chat_id"] == channel["chat_id"] for item in parse_required_channels()):
        await message.answer("⚠️ Цей канал уже є у списку обов'язкової підписки.")
        return

    try:
        bot_info = await bot.get_me()
        bot_member = await bot.get_chat_member(channel["chat_id"], bot_info.id)
        if bot_member.status not in ("creator", "administrator"):
            await message.answer(
                "❌ Бот знайдений у каналі, але не має прав адміністратора. "
                "Спочатку призначте його адміністратором."
            )
            return
    except Exception as error:
        print(
            f"Required channel validation failed for {channel['chat_id']}: "
            f"{type(error).__name__}: {error}",
            flush=True,
        )
        await message.answer(
            "❌ Не вдалося перевірити канал. Переконайтеся, що ID правильний "
            "і бот уже доданий до каналу адміністратором."
        )
        return

    updated_channels = parse_required_channels()
    updated_channels.append(channel)
    set_setting("required_channels", serialize_required_channels(updated_channels))
    await state.clear()
    await message.answer(
        f"✅ Канал <b>{esc(channel['title'])}</b> додано. "
        "Перевірка підписки вже активна.",
        reply_markup=admin_menu_kb(),
    )


@dp.callback_query(F.data.startswith("adm_channel_delete:"))
async def delete_required_channel(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    try:
        index = int(call.data.split(":", 1)[1])
    except (TypeError, ValueError):
        await call.answer("Некоректний канал.", show_alert=True)
        return
    channels = parse_required_channels()
    if index < 0 or index >= len(channels):
        await call.answer("Канал уже видалений.", show_alert=True)
        return
    removed = channels.pop(index)
    set_setting("required_channels", serialize_required_channels(channels))
    await call.answer("Канал видалено")
    await call.message.answer(
        f"✅ Канал <b>{esc(removed['title'])}</b> видалено зі списку.",
        reply_markup=required_channels_admin_kb(),
    )


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
    bank_names = {code: name for name, code, _ in BANK_OPTIONS}
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


RECEIPT_EXPORT_HEADERS = [
    "№",
    "№ замовлення",
    "Дата замовлення",
    "ID користувача",
    "Username",
    "Тип замовлення",
    "Кількість",
    "Сума замовлення, грн",
    "Спосіб оплати",
    "Статус замовлення",
    "Статус OCR",
    "№ квитанції",
    "Банк",
    "Очікуваний банк",
    "Перевірка банку",
    "ID транзакції",
    "ID операції",
    "RRN",
    "Статус платежу",
    "Дата/час операції",
    "Валюта",
    "Відправник",
    "Банк відправника",
    "Код банку відправника",
    "Рахунок відправника",
    "Картка відправника",
    "Платіжна система відправника",
    "Платіжний інструмент відправника",
    "Одержувач",
    "Банк одержувача",
    "Код банку одержувача",
    "Рахунок одержувача",
    "Картка одержувача",
    "Платіжна система одержувача",
    "Платіжний інструмент одержувача",
    "Сума з квитанції, грн",
    "Перевірка суми",
    "Комісія, грн",
    "Сума з комісією, грн",
    "Код авторизації",
    "Призначення платежу",
    "Коментар",
    "Торговець",
    "Ідентифікатор пристрою",
    "Тип файлу квитанції",
    "Ім'я файлу квитанції",
    "ID файлу квитанції",
    "Дата розбору OCR",
    "Помилка OCR",
    "Повний OCR текст",
]


def export_receipts_csv():
    export_dir = PROJECT_DIR / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    export_path = export_dir / f"receipts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    reset_at = setting("receipts_reset_at")
    receipt_filter = ""
    receipt_params = ()
    if reset_at:
        receipt_filter = " AND archive.created_at >= ?"
        receipt_params = (reset_at,)
    rows = db.execute(
        f"""SELECT orders.*, users.username,
                   archive.receipt_file_id AS archive_file_id,
                   archive.receipt_type AS archive_receipt_type,
                   archive.receipt_file_name AS archive_file_name,
                   archive.receipt_ocr_text AS archive_ocr_text,
                   archive.receipt_data_json AS archive_data_json,
                   archive.receipt_error AS archive_error,
                   archive.receipt_parsed_at AS archive_receipt_parsed_at,
                   archive.created_at AS archive_created_at
            FROM receipt_archive AS archive
            JOIN orders ON orders.id=archive.order_id
            LEFT JOIN users ON users.id=archive.user_id
            WHERE 1=1{receipt_filter}
            ORDER BY archive.id ASC""",
        receipt_params,
    ).fetchall()
    with export_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=RECEIPT_EXPORT_HEADERS)
        writer.writeheader()
        for row_number, order in enumerate(rows, start=1):
            try:
                receipt = json.loads(order["archive_data_json"] or "{}")
            except (TypeError, json.JSONDecodeError):
                receipt = {}
            writer.writerow({
                "№": row_number,
                "№ замовлення": order["id"],
                "Дата замовлення": order["archive_created_at"] or order["created_at"],
                "ID користувача": order["user_id"],
                "Username": f"@{order['username']}" if order["username"] else "",
                "Тип замовлення": order["order_type"],
                "Кількість": order["quantity"],
                "Сума замовлення, грн": f"{order['amount']:.2f}",
                "Спосіб оплати": order["payment_method"] or "",
                "Статус замовлення": order["status"],
                "Статус OCR": receipt.get("ocr_status", "Потрібна перевірка"),
                "№ квитанції": receipt.get("receipt_number", ""),
                "Банк": receipt.get("bank", ""),
                "Очікуваний банк": receipt.get("expected_bank", ""),
                "Перевірка банку": receipt.get("bank_match", ""),
                "ID транзакції": receipt.get("transaction_id", ""),
                "ID операції": receipt.get("operation_id", ""),
                "RRN": receipt.get("rrn", ""),
                "Статус платежу": receipt.get("status", ""),
                "Дата/час операції": receipt.get("operation_datetime", ""),
                "Валюта": receipt.get("currency", ""),
                "Відправник": receipt.get("sender_name", ""),
                "Банк відправника": receipt.get("sender_bank", ""),
                "Код банку відправника": receipt.get("sender_bank_code", ""),
                "Рахунок відправника": receipt.get("sender_account", ""),
                "Картка відправника": receipt.get("sender_card", ""),
                "Платіжна система відправника": receipt.get("sender_payment_system", ""),
                "Платіжний інструмент відправника": receipt.get("sender_instrument", ""),
                "Одержувач": receipt.get("receiver_name", ""),
                "Банк одержувача": receipt.get("receiver_bank", ""),
                "Код банку одержувача": receipt.get("receiver_bank_code", ""),
                "Рахунок одержувача": receipt.get("receiver_account", ""),
                "Картка одержувача": receipt.get("receiver_card", ""),
                "Платіжна система одержувача": receipt.get("receiver_payment_system", ""),
                "Платіжний інструмент одержувача": receipt.get("receiver_instrument", ""),
                "Сума з квитанції, грн": receipt.get("amount", ""),
                "Перевірка суми": receipt.get("amount_match", ""),
                "Комісія, грн": receipt.get("fee", ""),
                "Сума з комісією, грн": receipt.get("total_amount", ""),
                "Код авторизації": receipt.get("authorization_code", ""),
                "Призначення платежу": receipt.get("payment_purpose", ""),
                "Коментар": receipt.get("comment", ""),
                "Торговець": receipt.get("merchant", ""),
                "Ідентифікатор пристрою": receipt.get("device_id", ""),
                "Тип файлу квитанції": order["archive_receipt_type"] or "",
                "Ім'я файлу квитанції": order["archive_file_name"] or "",
                "ID файлу квитанції": order["archive_file_id"] or "",
                "Дата розбору OCR": order["archive_receipt_parsed_at"] or "",
                "Помилка OCR": order["archive_error"] or "",
                "Повний OCR текст": order["archive_ocr_text"] or "",
            })
    return export_path, len(rows)


@dp.callback_query(F.data == "adm:receipts")
async def adm_receipts(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    reset_at = setting("receipts_reset_at")
    receipt_filter = ""
    receipt_params = ()
    if reset_at:
        receipt_filter = " AND created_at >= ?"
        receipt_params = (reset_at,)
    receipt_count = db.execute(
        f"SELECT COUNT(*) AS c FROM receipt_archive "
        f"WHERE 1=1{receipt_filter}",
        receipt_params,
    ).fetchone()["c"]
    total_receipt_count = db.execute(
        "SELECT COUNT(*) AS c FROM receipt_archive"
    ).fetchone()["c"]
    period = f"після {esc(reset_at)}" if reset_at else "за весь час"
    await call.message.answer(
        f"🧾 <b>Квитанції</b>\n\n"
        f"У поточному архіві: <b>{receipt_count}</b>\n"
        f"Період: <b>{period}</b>\n"
        f"У базі збережено всього: <b>{total_receipt_count}</b>\n\n"
        "Кнопка вигрузки сформує CSV-таблицю з усіма квитанціями "
        "поточного архіву та всіма доступними полями OCR.",
        reply_markup=receipts_kb(),
    )


@dp.callback_query(F.data == "adm:receipts_export")
async def adm_receipts_export(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer("Формую таблицю квитанцій…")
    export_path, exported_count = export_receipts_csv()
    if not exported_count:
        await call.message.answer(
            "🧾 Поточний архів квитанцій порожній.",
            reply_markup=receipts_kb(),
        )
        return
    await bot.send_document(
        call.message.chat.id,
        FSInputFile(str(export_path)),
        caption=f"📄 Таблиця квитанцій: {exported_count} записів.",
    )


@dp.callback_query(F.data == "adm:receipts_reset")
async def adm_receipts_reset(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await call.message.answer(
        "⚠️ <b>Скинути поточний архів квитанцій?</b>\n\n"
        "Старі записи не будуть видалені з бази, але зникнуть із поточного "
        "списку та наступної вигрузки. Нові квитанції почнуть новий архів.",
        reply_markup=receipts_reset_confirm_kb(),
    )


@dp.callback_query(F.data == "adm:receipts_reset_confirm")
async def adm_receipts_reset_confirm(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    set_setting("receipts_reset_at", now())
    await call.answer("Архів квитанцій скинуто")
    await call.message.answer(
        "✅ Поточний архів квитанцій скинуто. Старі записи залишилися в базі.",
        reply_markup=receipts_kb(),
    )


@dp.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    await render_admin_stats(call.message)


async def render_admin_stats(message: Message):
    reset_at = setting("stats_reset_at")
    user_where = "WHERE registered_at >= ?" if reset_at else ""
    order_where = "WHERE created_at >= ?" if reset_at else ""
    user_params = (reset_at,) if reset_at else ()
    order_params = (reset_at,) if reset_at else ()
    users = db.execute(
        f"SELECT COUNT(*) c FROM users {user_where}", user_params
    ).fetchone()["c"]
    orders = db.execute(
        f"SELECT COUNT(*) c FROM orders {order_where}", order_params
    ).fetchone()["c"]
    done = db.execute(
        f"SELECT COUNT(*) c FROM orders {order_where}"
        f"{' AND' if order_where else ' WHERE'} status='completed'",
        order_params,
    ).fetchone()["c"]
    waiting = db.execute(
        f"SELECT COUNT(*) c FROM orders {order_where}"
        f"{' AND' if order_where else ' WHERE'} status IN ('waiting_payment','waiting_review')",
        order_params,
    ).fetchone()["c"]
    rejected = db.execute(
        f"SELECT COUNT(*) c FROM orders {order_where}"
        f"{' AND' if order_where else ' WHERE'} status='rejected'",
        order_params,
    ).fetchone()["c"]
    money = db.execute(
        f"SELECT COALESCE(SUM(amount),0) s FROM orders {order_where}"
        f"{' AND' if order_where else ' WHERE'} status='completed'",
        order_params,
    ).fetchone()["s"]
    receipt_where = "WHERE created_at >= ?" if reset_at else ""
    receipt_params = (reset_at,) if reset_at else ()
    receipt_count = db.execute(
        f"SELECT COUNT(*) c FROM receipt_archive {receipt_where}",
        receipt_params,
    ).fetchone()["c"]
    receipt_parsed = db.execute(
        f"SELECT COUNT(*) c FROM receipt_archive {receipt_where}"
        f"{' AND' if receipt_where else ' WHERE'} receipt_ocr_text IS NOT NULL "
        f"AND receipt_ocr_text != ''",
        receipt_params,
    ).fetchone()["c"]
    recent_users = db.execute(
        f"SELECT id,username,first_name FROM users "
        f"{user_where} ORDER BY registered_at DESC,id DESC LIMIT 10",
        user_params,
    ).fetchall()
    user_lines = []
    for user in recent_users:
        label = f"@{esc(user['username'])}" if user["username"] else esc(user["first_name"] or "без username")
        user_lines.append(f"• {label} — <code>{user['id']}</code>")
    recent_user_list = "\n".join(user_lines) if user_lines else "Поки немає користувачів."
    period = (
        f"з {esc(reset_at)}"
        if reset_at
        else "за весь час"
    )
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"🗓 Період: <b>{period}</b>\n\n"
        f"👥 Користувачів: {users}\n"
        f"📦 Замовлень: {orders}\n"
        f"✅ Виконано: {done}\n"
        f"⏳ Очікують підтвердження: {waiting}\n"
        f"🔴 Відхилено: {rejected}\n"
        f"💰 Підтверджено оплат: {money:.2f} грн\n\n"
        f"🧾 Квитанцій: {receipt_count} (розпізнано: {receipt_parsed})\n\n"
        f"👤 <b>Останні користувачі</b>\n{recent_user_list}"
        ,
        reply_markup=stats_kb(),
    )


@dp.callback_query(F.data == "adm:stats_reset")
async def adm_stats_reset(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    reset_at = now()
    # Statistics and receipt exports share one reporting period. Historical
    # rows stay in the database, but the next export starts from this reset.
    set_setting("stats_reset_at", reset_at)
    set_setting("receipts_reset_at", reset_at)
    await call.answer("Статистику та період квитанцій скинуто")
    await render_admin_stats(call.message)


@dp.callback_query(F.data == "adm:orders")
async def adm_orders(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS:
        return
    await call.answer()
    # The admin's "Замовлення" queue is only for receipts awaiting review.
    # Orders that are still waiting for payment must not appear here.
    rows = db.execute(
        "SELECT * FROM orders WHERE status='waiting_review' "
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


@dp.message(Form.nft_add_wait_emoji)
async def nft_receive_emoji(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    sticker = message.sticker
    custom_emoji_id = next(
        (
            entity.custom_emoji_id
            for entity in (message.entities or [])
            if entity.type == "custom_emoji" and entity.custom_emoji_id
        ),
        None,
    )

    if sticker:
        custom_emoji_id = custom_emoji_id or getattr(sticker, "custom_emoji_id", None)
        sticker_type = getattr(sticker, "type", "")
        if custom_emoji_id or sticker_type == "custom_emoji":
            await state.update_data(
                sticker_file_id=None,
                sticker_type=None,
                custom_emoji_id=custom_emoji_id,
                nft_emoji=sticker.emoji or "🎁",
            )
            received_text = "✅ Premium Emoji отримано."
        else:
            await state.update_data(
                sticker_file_id=sticker.file_id,
                sticker_type="sticker",
                custom_emoji_id=None,
                nft_emoji=sticker.emoji or "🎁",
            )
            received_text = "✅ NFT-стікер отримано."
    elif custom_emoji_id:
        await state.update_data(
            sticker_file_id=None,
            sticker_type=None,
            custom_emoji_id=custom_emoji_id,
            nft_emoji=(message.text or "").strip() or "🎁",
        )
        received_text = "✅ Premium Emoji отримано."
    elif message.text and message.text.strip() and len(message.text.strip()) <= 16 and not any(
        character.isalnum() for character in message.text.strip()
    ):
        # Some Telegram clients send a plain emoji without preserving the
        # custom_emoji entity. Keep the visible emoji instead of rejecting it.
        await state.update_data(
            sticker_file_id=None,
            sticker_type=None,
            custom_emoji_id=None,
            nft_emoji=message.text.strip(),
        )
        received_text = "✅ Emoji отримано."
    else:
        await message.answer(
            "❌ Не бачу емодзі.\nНадішліть Premium Emoji, custom-emoji sticker або звичайний emoji."
        )
        return

    await state.set_state(Form.nft_add_details)
    await message.answer(
        f"{received_text}\n\n"
        "Тепер надішліть одним повідомленням:\n"
        "<code>Назва | ціна | опис</code>\n\n"
        "Наприклад:\n"
        "<code>Gift #1 | 350 | Опис подарунка</code>"
    )


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
    stars_credited = None
    raffle_offer = None
    referral_bonus = 0
    referrer_id = None
    try:
        db.execute("BEGIN IMMEDIATE")
        order = db.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not order or order["status"] != "waiting_review":
            db.rollback()
            await call.message.answer("Замовлення вже оброблене або не існує.")
            return

        if order["order_type"] == "buy_stars":
            purchased_stars = int(order["quantity"])
            raffle = active_raffle()
            if raffle:
                raffle_offer = raffle

            # Every Stars top-up is credited in full first. A separate consent
            # callback may debit only this exact order later.
            stars_credited = purchased_stars
            db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
            db.execute(
                """UPDATE users SET balance_stars=balance_stars+?, bought_stars=bought_stars+?,
                   spent_uah=spent_uah+?, status='Клієнт' WHERE id=?""",
                (stars_credited, purchased_stars, order["amount"], order["user_id"]),
            )
            referrer_id, referral_bonus = credit_referral_bonus(
                oid,
                order["user_id"],
                purchased_stars,
            )
        elif order["order_type"] == "buy_ton":
            db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
            db.execute(
                "UPDATE users SET bought_ton=bought_ton+?, spent_uah=spent_uah+?, status='Клієнт' WHERE id=?",
                (float(order["quantity"]), order["amount"], order["user_id"]),
            )
        elif order["order_type"] == "nft":
            db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
            db.execute(
                "UPDATE users SET spent_uah=spent_uah+?, status='Клієнт' WHERE id=?",
                (order["amount"], order["user_id"]),
            )
        elif order["order_type"] == "withdraw_stars":
            db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
            db.execute(
                "UPDATE users SET balance_stars=MAX(balance_stars-?,0) WHERE id=?",
                (int(order["quantity"]), order["user_id"]),
            )
        else:
            db.execute("UPDATE orders SET status='completed' WHERE id=?", (oid,))
        db.commit()
    except Exception:
        db.rollback()
        raise

    await call.message.edit_reply_markup(reply_markup=None)
    await call.message.answer(f"{pe(EMOJI_POOL[5], '✅')} Замовлення #{oid} підтверджено.")

    if order["order_type"] == "buy_stars":
        current_balance = user_row(order["user_id"])["balance_stars"]
        user_text = (
            f"{pe(EMOJI_POOL[5], '✅')} <b>Поповнення #{oid} підтверджено!</b>\n\n"
            f"⭐ На баланс зараховано: <b>{stars_credited} Stars</b>\n"
            f"💳 Поточний баланс: <b>{current_balance} Stars</b>"
        )
        await bot.send_message(
            order["user_id"],
            user_text,
            reply_markup=main_menu(user_language(order["user_id"])),
        )
        if referrer_id and referral_bonus:
            try:
                await bot.send_message(
                    referrer_id,
                    f"🎉 За покупку вашого реферала нараховано "
                    f"<b>{referral_bonus} Stars</b> (10%).\n"
                    f"⭐ Поточний баланс: <b>{user_row(referrer_id)['balance_stars']} Stars</b>",
                    reply_markup=main_menu(user_language(referrer_id)),
                )
            except Exception as error:
                print(
                    f"Referral notification failed for {referrer_id}: {error}",
                    flush=True,
                )

        if raffle_offer:
            current = db.execute(
                "SELECT * FROM raffles WHERE id=? AND status='active'",
                (raffle_offer["id"],),
            ).fetchone()
            if current:
                await bot.send_message(
                    order["user_id"],
                    raffle_consent_text(current, order, order["user_id"]),
                    reply_markup=raffle_consent_kb(current["id"], oid),
                )
    else:
        await bot.send_message(
            order["user_id"],
            f"{pe(EMOJI_POOL[5], '✅')} <b>Замовлення #{oid} підтверджено!</b>",
            reply_markup=main_menu(user_language(order["user_id"])),
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
    if not order or order["status"] != "waiting_review":
        await state.clear()
        await message.answer("❌ Це замовлення вже оброблене або не існує.")
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
        reply_markup=main_menu(user_language(message.from_user.id)),
    )


async def start_health_server():
    async def health(_request):
        return web.Response(text="Spanix Stars Bot is running")

    async def telegram_webhook(request):
        if WEBHOOK_SECRET and request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token"
        ) != WEBHOOK_SECRET:
            return web.Response(status=403, text="forbidden")
        try:
            update = Update.model_validate(await request.json())
            await dp.feed_update(bot, update)
        except Exception as error:
            print(f"Telegram webhook failed: {type(error).__name__}: {error}")
            return web.Response(status=500, text="webhook error")
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    if WEBHOOK_URL:
        app.router.add_post(WEBHOOK_PATH, telegram_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "8765"))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner


async def keepalive_loop():
    if not KEEPALIVE_URL:
        print("Self-ping disabled: set KEEPALIVE_URL in Render Environment to enable it.")
        return

    timeout = ClientTimeout(total=20)
    async with ClientSession(timeout=timeout) as session:
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            try:
                async with session.get(
                    KEEPALIVE_URL,
                    headers={"User-Agent": "Spanix-Stars-keepalive"},
                ) as response:
                    print(
                        f"Self-ping {KEEPALIVE_URL}: HTTP {response.status}"
                    )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                print(f"Self-ping failed: {type(error).__name__}: {error}")


async def configure_webhook():
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    webhook_options = {
        "url": webhook_url,
        "drop_pending_updates": False,
    }
    if WEBHOOK_SECRET:
        webhook_options["secret_token"] = WEBHOOK_SECRET
    await bot.set_webhook(**webhook_options)
    print(f"Telegram webhook configured: {webhook_url}")


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Не задано BOT_TOKEN у Replit Secrets.")
    print(f"SQLite database: {DB_PATH}")
    if not ADMIN_IDS:
        print("ADMIN_IDS не задано: надішліть боту /id, додайте ID в ADMIN_IDS і перезапустіть бота.")
    global bot
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    health_runner = None
    keepalive_task = None
    try:
        health_runner = await start_health_server()
        keepalive_task = asyncio.create_task(keepalive_loop())
        await configure_bot_commands()
        if WEBHOOK_URL:
            await configure_webhook()
            await asyncio.Event().wait()
        else:
            await bot.delete_webhook(drop_pending_updates=False)
            retry_delay = 2
            while True:
                try:
                    await dp.start_polling(bot)
                    retry_delay = 2
                    print("Telegram polling stopped; restarting.")
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    print(
                        f"Telegram polling failed: {type(error).__name__}: {error}. "
                        f"Retrying in {retry_delay}s."
                    )
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 60)
    finally:
        if keepalive_task is not None:
            keepalive_task.cancel()
            await asyncio.gather(keepalive_task, return_exceptions=True)
        if health_runner is not None:
            await health_runner.cleanup()
        await bot.session.close()
        bot = None


if __name__ == "__main__":
    asyncio.run(main())
