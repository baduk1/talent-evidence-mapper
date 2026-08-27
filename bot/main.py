"""Telegram-бот личного кабинета (aiogram 3, asyncio).

Третий интерфейс наравне с вебом и REST API. Возможности: регистрация
(аккаунт привязывается к telegram id), просмотр и пополнение баланса,
отправка достижения на классификацию с получением результата из очереди,
история операций. Язык (RU/EN) выбирается один раз на первом экране
и хранится в памяти процесса бота.

Бот ходит в Postgres и RabbitMQ напрямую через пакет tem, как ml_worker:
HTTP-слой здесь не нужен, бизнес-правила живут в crud и домене.
"""
import asyncio
import hashlib
import logging
import os
import uuid
from decimal import Decimal, InvalidOperation

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlmodel import Session

from tem.domain.enums import TaskStatus
from tem.infrastructure.db import crud
from tem.infrastructure.db.database import engine, init_db
from tem.infrastructure.mq import send_task

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

RESULT_POLL_SECONDS = 3
RESULT_TIMEOUT_SECONDS = 90

# Выбранный язык по telegram id. Живёт в памяти процесса: после перезапуска
# бота пользователь просто выбирает язык ещё раз через /start.
LANGS: dict[int, str] = {}

STR = {
    "ru": {
        "choose_lang": "Выберите язык / Choose your language",
        "welcome": (
            "Добро пожаловать в Talent Evidence Mapper!\n\n"
            "Я классифицирую профессиональные достижения по категориям "
            "с помощью ML-модели. Команды:\n"
            "/balance - баланс кредитов\n"
            "/topup 10 - пополнить баланс\n"
            "/predict - отправить достижение на классификацию\n"
            "/history - история операций\n"
            "/lang - сменить язык"
        ),
        "balance": "Баланс: {balance} кредитов",
        "topup_usage": "Формат: /topup 10 (положительная сумма)",
        "topup_ok": "Баланс пополнен: {balance} кредитов",
        "predict_ask_title": "Название достижения?",
        "predict_ask_description": "Описание (минимум 40 символов)?",
        "predict_queued": "Задача {task_id} в очереди, сообщу результат.",
        "predict_result": "Результат по «{title}»: {category} ({confidence}%), статус {status}",
        "predict_missing": "Не хватает: {items}",
        "predict_rejected": "Отклонено: {messages}",
        "predict_failed": "Задача не выполнена: недостаточно кредитов. Пополните: /topup 10",
        "predict_timeout": "Задача обрабатывается дольше обычного, результат смотрите в /history",
        "predict_cancel": "Отменено.",
        "history_empty": "Операций пока не было.",
        "history_tasks": "Последние задачи:",
        "history_tx": "Последние транзакции:",
        "task_line": "{date} | {status} | списано {charged}",
        "tx_line": "{date} | {tx_type} | {amount}",
        "unknown": "Не понимаю. Команды: /balance, /topup, /predict, /history",
        "credit": "пополнение",
        "debit": "списание",
        "cancel": "отмена",
    },
    "en": {
        "choose_lang": "Выберите язык / Choose your language",
        "welcome": (
            "Welcome to Talent Evidence Mapper!\n\n"
            "I classify professional achievements into categories with an "
            "ML model. Commands:\n"
            "/balance - credit balance\n"
            "/topup 10 - top up balance\n"
            "/predict - submit an achievement for classification\n"
            "/history - activity history\n"
            "/lang - change language"
        ),
        "balance": "Balance: {balance} credits",
        "topup_usage": "Format: /topup 10 (positive amount)",
        "topup_ok": "Balance topped up: {balance} credits",
        "predict_ask_title": "Achievement title?",
        "predict_ask_description": "Description (at least 40 characters)?",
        "predict_queued": "Task {task_id} queued, I will report the result.",
        "predict_result": "Result for «{title}»: {category} ({confidence}%), status {status}",
        "predict_missing": "Missing: {items}",
        "predict_rejected": "Rejected: {messages}",
        "predict_failed": "Task failed: not enough credits. Top up: /topup 10",
        "predict_timeout": "Processing takes longer than usual, see /history for the result",
        "predict_cancel": "Cancelled.",
        "history_empty": "No activity yet.",
        "history_tasks": "Recent tasks:",
        "history_tx": "Recent transactions:",
        "task_line": "{date} | {status} | charged {charged}",
        "tx_line": "{date} | {tx_type} | {amount}",
        "unknown": "Unknown command. Try /balance, /topup, /predict, /history",
        "credit": "top up",
        "debit": "charge",
        "cancel": "cancel",
    },
}

CATEGORIES = {
    "ru": {
        "innovation": "Инновации",
        "recognition_leader": "Признание лидерства",
        "significant_contribution": "Значимый вклад",
        "academic_contribution": "Академический вклад",
        "outside_work": "Активность вне работы",
        "irrelevant": "Нерелевантно",
        "insufficiaent": "Недостаточно данных",
        "insufficient": "Недостаточно данных",
    },
    "en": {
        "innovation": "Innovation",
        "recognition_leader": "Leadership recognition",
        "significant_contribution": "Significant contribution",
        "academic_contribution": "Academic contribution",
        "outside_work": "Outside work activity",
        "irrelevant": "Irrelevant",
        "insufficiaent": "Insufficient data",
        "insufficient": "Insufficient data",
    },
}

DOMAIN_MSGS = {
    "en": {
        "не предъявлено измеримых метрик": "no measurable metrics provided",
        "не предъявлен URL": "no source URL provided",
        "title is required": "title is required",
        "описание должно иметь минимум 40 символов": "description must be at least 40 characters",
    },
}


def s(tg_id: int) -> dict:
    return STR[LANGS.get(tg_id, "ru")]


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
        InlineKeyboardButton(text="English", callback_data="lang:en"),
    ]])


def get_or_create_user(tg_id: int) -> str:
    """Аккаунт привязан к telegram id: синтетический email, случайный пароль.
    Возвращает user.id."""
    email = f"tg_{tg_id}@telegram.local"
    with Session(engine) as session:
        user = crud.get_user_by_email(session, email)
        if user is None:
            password_hash = hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()
            user = crud.create_user(session, email, password_hash)
            session.commit()
        return user.id


def read_task_bundle(task_id: str):
    """Задача + записи + ошибки одним чтением (для to_thread)."""
    with Session(engine) as session:
        task = crud.get_task(session, task_id)
        if task is None:
            return None
        return (
            task.status,
            task.credits_charged,
            [
                (r.title, r.primary_category, r.confidence, r.missing_information)
                for r in crud.list_records_for_task(session, task_id)
            ],
            [e.messages for e in crud.list_item_errors_for_task(session, task_id)],
        )


dp = Dispatcher(storage=MemoryStorage())


class PredictForm(StatesGroup):
    title = State()
    description = State()


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    tg_id = message.from_user.id
    if tg_id in LANGS:
        await message.answer(s(tg_id)["welcome"])
    else:
        await message.answer(STR["ru"]["choose_lang"], reply_markup=lang_keyboard())


@dp.callback_query(lambda call: call.data.startswith("lang:"))
async def on_lang_chosen(call: CallbackQuery) -> None:
    lang = call.data.split(":", 1)[1]
    LANGS[call.from_user.id] = lang
    await asyncio.to_thread(get_or_create_user, call.from_user.id)
    await call.message.edit_text(s(call.from_user.id)["welcome"])
    await call.answer()


@dp.message(Command("lang"))
async def cmd_lang(message: Message) -> None:
    await message.answer(STR["ru"]["choose_lang"], reply_markup=lang_keyboard())


@dp.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    def _balance():
        with Session(engine) as session:
            return crud.get_user_by_id(session, user_id).balance

    user_id = await asyncio.to_thread(get_or_create_user, message.from_user.id)
    balance = await asyncio.to_thread(_balance)
    await message.answer(s(message.from_user.id)["balance"].format(balance=balance))


@dp.message(Command("topup"))
async def cmd_topup(message: Message, command: CommandObject) -> None:
    strings = s(message.from_user.id)
    try:
        amount = Decimal(command.args.strip())
    except (AttributeError, InvalidOperation):
        await message.answer(strings["topup_usage"])
        return

    user_id = await asyncio.to_thread(get_or_create_user, message.from_user.id)

    def _topup():
        with Session(engine) as session:
            crud.top_up(session, user_id, amount)
            session.commit()
            return crud.get_user_by_id(session, user_id).balance

    try:
        balance = await asyncio.to_thread(_topup)
    except Exception:
        await message.answer(strings["topup_usage"])
        return
    await message.answer(strings["topup_ok"].format(balance=balance))


@dp.message(Command("predict"))
async def cmd_predict(message: Message, state: FSMContext) -> None:
    await state.set_state(PredictForm.title)
    await message.answer(s(message.from_user.id)["predict_ask_title"])


@dp.message(PredictForm.title)
async def predict_title(message: Message, state: FSMContext) -> None:
    if message.text == s(message.from_user.id)["cancel"]:
        await state.clear()
        await message.answer(s(message.from_user.id)["predict_cancel"])
        return
    await state.update_data(title=message.text.strip())
    await state.set_state(PredictForm.description)
    await message.answer(s(message.from_user.id)["predict_ask_description"])


@dp.message(PredictForm.description)
async def predict_description(message: Message, state: FSMContext) -> None:
    strings = s(message.from_user.id)
    tg_id = message.from_user.id
    data = await state.get_data()
    await state.clear()

    user_id = await asyncio.to_thread(get_or_create_user, tg_id)

    def _enqueue() -> str:
        with Session(engine) as session:
            model_orm = crud.get_default_model(session)
            task = crud.create_task(session, user_id, model_orm.id)
            session.commit()
            send_task({
                "task_id": task.id,
                "user_id": user_id,
                "model_id": model_orm.id,
                "items": [{
                    "title": data["title"],
                    "description": message.text.strip(),
                    "evidence_type": None,
                    "source_url": None,
                    "metrics": {},
                }],
            })
            return task.id

    task_id = await asyncio.to_thread(_enqueue)
    await message.answer(strings["predict_queued"].format(task_id=task_id[:8]))

    # Ждём обработки воркером и присылаем результат отдельным сообщением.
    deadline = RESULT_TIMEOUT_SECONDS // RESULT_POLL_SECONDS
    for _ in range(deadline):
        await asyncio.sleep(RESULT_POLL_SECONDS)
        bundle = await asyncio.to_thread(read_task_bundle, task_id)
        if bundle is None or bundle[0] == TaskStatus.CREATED:
            continue
        status, _charged, records, errors = bundle
        if status == TaskStatus.FAILED:
            await message.answer(strings["predict_failed"])
            return
        for title, category, confidence, missing in records:
            text = strings["predict_result"].format(
                title=title,
                category=CATEGORIES[LANGS.get(tg_id, "ru")].get(category, category),
                confidence=round(confidence * 100),
                status=status.value,
            )
            if missing:
                localized = [
                    DOMAIN_MSGS.get(LANGS.get(tg_id, "ru"), {}).get(m, m) for m in missing
                ]
                text += "\n" + strings["predict_missing"].format(items=", ".join(localized))
            await message.answer(text)
        for messages in errors:
            localized = DOMAIN_MSGS.get(LANGS.get(tg_id, "ru"), {}).get(messages, messages)
            await message.answer(strings["predict_rejected"].format(messages=localized))
        return
    await message.answer(strings["predict_timeout"])


@dp.message(Command("history"))
async def cmd_history(message: Message) -> None:
    strings = s(message.from_user.id)
    user_id = await asyncio.to_thread(get_or_create_user, message.from_user.id)

    def _history():
        with Session(engine) as session:
            return (
                crud.list_tasks_for_user(session, user_id)[:5],
                crud.list_transactions_for_user(session, user_id)[:5],
            )

    tasks, transactions = await asyncio.to_thread(_history)
    if not tasks and not transactions:
        await message.answer(strings["history_empty"])
        return
    lines = []
    if tasks:
        lines.append(strings["history_tasks"])
        lines += [
            strings["task_line"].format(
                date=t.created_at.strftime("%Y-%m-%d %H:%M"),
                status=t.status.value,
                charged=t.credits_charged,
            )
            for t in tasks
        ]
    if transactions:
        lines.append(strings["history_tx"])
        lines += [
            strings["tx_line"].format(
                date=tx.created_at.strftime("%Y-%m-%d %H:%M"),
                tx_type=strings[tx.type.value],
                amount=tx.amount,
            )
            for tx in transactions
        ]
    await message.answer("\n".join(lines))


@dp.message()
async def fallback(message: Message) -> None:
    await message.answer(s(message.from_user.id)["unknown"])


def main() -> None:
    # БД может стартовать чуть дольше контейнера - терпеливо дожидаемся.
    import time

    while True:
        try:
            init_db()
            break
        except Exception:
            logger.info("Database is not ready yet, retrying in 3s...")
            time.sleep(3)

    bot = Bot(token=BOT_TOKEN)
    logger.info("Telegram bot is starting (long polling)...")
    asyncio.run(dp.start_polling(bot))


if __name__ == "__main__":
    main()
