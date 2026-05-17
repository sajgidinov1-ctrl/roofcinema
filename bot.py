"""
RoofCinema — Бот для бронирования билетов
Кинотеатр на крыше
"""

import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
import os
from movies import (
    SCHEDULE, CINEMA_NAME, CINEMA_EMOJI,
    CINEMA_ADDRESS, CINEMA_INFO,
    CARD_NUMBER, CARD_PHONE, CARD_HOLDER, BANK_NAME
)

# ============================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8654990077:AAGPyr-iNsnhKeff43RIeBwheXr1SzaiZgA")
ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "8235415794"))
# ============================================================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


class BookingStates(StatesGroup):
    choosing_date = State()
    choosing_session = State()
    choosing_tickets = State()
    entering_name = State()
    entering_phone = State()
    choosing_payment = State()
    waiting_receipt = State()


# --- Keyboards ---

def dates_keyboard():
    """Показывает только даты у которых есть сеансы"""
    buttons = []
    today = datetime.now()
    row = []
    for i in range(7):
        day = today + timedelta(days=i)
        date_str = day.strftime("%Y-%m-%d")
        if date_str not in SCHEDULE:
            continue
        label = "Сегодня" if i == 0 else ("Завтра" if i == 1 else day.strftime("%d.%m"))
        row.append(InlineKeyboardButton(
            text=label, callback_data=f"date:{date_str}"
        ))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def sessions_keyboard(date_str):
    """Показывает сеансы выбранного дня"""
    buttons = []
    sessions = SCHEDULE.get(date_str, [])
    for i, s in enumerate(sessions):
        buttons.append([InlineKeyboardButton(
            text=f"🎥 {s['film']} | {s['time']} | {s['price']} руб/билет",
            callback_data=f"session:{i}"
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def tickets_keyboard():
    buttons = []
    row = []
    for i in range(1, 11):
        row.append(InlineKeyboardButton(
            text=str(i), callback_data=f"tickets:{i}"
        ))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def payment_keyboard(has_card):
    buttons = [
        [InlineKeyboardButton(text="💵 Наличными при входе", callback_data="pay:cash")]
    ]
    if has_card:
        buttons.append(
            [InlineKeyboardButton(text="💳 Переводом на карту", callback_data="pay:card")]
        )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def receipt_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил — отправить чек", callback_data="paid")],
        [InlineKeyboardButton(text="❌ Отменить бронь", callback_data="cancel")],
    ])


def phone_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Отправить мой номер", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


# --- Handlers ---

@dp.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()

    kb = dates_keyboard()
    if not kb.inline_keyboard:
        await message.answer(
            f"{CINEMA_EMOJI} *{CINEMA_NAME}*\n\n"
            "К сожалению, на ближайшие 7 дней сеансов нет.\n"
            "Следите за обновлениями!",
            parse_mode="Markdown"
        )
        return

    await message.answer(
        f"{CINEMA_EMOJI} *{CINEMA_NAME}*\n\n"
        f"📍 {CINEMA_ADDRESS}\n"
        f"ℹ️ {CINEMA_INFO}\n\n"
        "Выбери дату 👇",
        parse_mode="Markdown",
        reply_markup=kb
    )
    await state.set_state(BookingStates.choosing_date)


@dp.callback_query(F.data.startswith("date:"))
async def choose_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.split(":")[1]
    date_display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d.%m.%Y")
    await state.update_data(date=date_str, date_display=date_display)

    await callback.message.edit_text(
        f"📅 Дата: *{date_display}*\n\nВыбери сеанс 🎬",
        parse_mode="Markdown",
        reply_markup=sessions_keyboard(date_str)
    )
    await state.set_state(BookingStates.choosing_session)
    await callback.answer()


@dp.callback_query(F.data.startswith("session:"))
async def choose_session(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = int(callback.data.split(":")[1])
    session = SCHEDULE[data["date"]][idx]

    await state.update_data(
        film=session["film"],
        time=session["time"],
        price=session["price"],
        session_idx=idx
    )

    await callback.message.edit_text(
        f"🎥 Фильм: *{session['film']}*\n"
        f"⏰ Время: *{session['time']}*\n"
        f"💰 Цена: *{session['price']} руб/билет*\n\n"
        "Сколько билетов? 👇",
        parse_mode="Markdown",
        reply_markup=tickets_keyboard()
    )
    await state.set_state(BookingStates.choosing_tickets)
    await callback.answer()


@dp.callback_query(F.data.startswith("tickets:"))
async def choose_tickets(callback: types.CallbackQuery, state: FSMContext):
    count = int(callback.data.split(":")[1])
    data = await state.get_data()
    total = count * data["price"]

    await state.update_data(tickets=count, total=total)
    await callback.message.edit_text(
        f"🎟 Билетов: *{count}*\n"
        f"💰 Итого: *{total} руб*\n\n"
        "Как тебя зовут? 👇",
        parse_mode="Markdown"
    )
    await state.set_state(BookingStates.entering_name)
    await callback.answer()


@dp.message(BookingStates.entering_name)
async def enter_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if len(name) < 2:
        await message.answer("Пожалуйста, введи настоящее имя 😊")
        return
    await state.update_data(name=name)
    await message.answer(
        f"Отлично, *{name}*! 👋\n\nПоделись номером телефона:",
        parse_mode="Markdown",
        reply_markup=phone_keyboard()
    )
    await state.set_state(BookingStates.entering_phone)


@dp.message(BookingStates.entering_phone, F.contact)
async def enter_phone_contact(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.contact.phone_number)
    await show_payment(message, state)


@dp.message(BookingStates.entering_phone, F.text)
async def enter_phone_text(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text.strip())
    await show_payment(message, state)


async def show_payment(message: types.Message, state: FSMContext):
    data = await state.get_data()
    has_card = bool(CARD_NUMBER)

    await message.answer(
        f"📋 *Детали брони:*\n\n"
        f"🎥 {data['film']}\n"
        f"📅 {data['date_display']} в {data['time']}\n"
        f"🎟 Билетов: {data['tickets']} шт\n"
        f"💰 Итого: {data['total']} руб\n"
        f"👤 {data['name']}\n"
        f"📱 {data['phone']}\n\n"
        "Выбери способ оплаты 👇",
        parse_mode="Markdown",
        reply_markup=payment_keyboard(has_card)
    )
    await state.set_state(BookingStates.choosing_payment)


@dp.callback_query(F.data == "pay:cash")
async def pay_cash(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.update_data(payment="Наличными при входе")

    await callback.message.edit_text(
        f"✅ *Бронь подтверждена!*\n\n"
        f"🎥 {data['film']}\n"
        f"📅 {data['date_display']} в {data['time']}\n"
        f"🎟 {data['tickets']} билет(а)\n"
        f"💰 {data['total']} руб — оплата наличными при входе\n"
        f"📍 {CINEMA_ADDRESS}\n\n"
        f"ℹ️ {CINEMA_INFO}\n\n"
        "Ждём вас! 🎬",
        parse_mode="Markdown",
        reply_markup=None
    )

    await notify_admin(state, callback.from_user, "Наличными при входе")
    await state.clear()
    await callback.answer()


@dp.callback_query(F.data == "pay:card")
async def pay_card(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    await callback.message.edit_text(
        f"💳 *Оплата переводом*\n\n"
        f"Сумма: *{data['total']} руб*\n\n"
        f"🏦 {BANK_NAME}\n"
        f"💳 Карта: `{CARD_NUMBER}`\n"
        f"📱 СБП: `{CARD_PHONE}`\n"
        f"👤 {CARD_HOLDER}\n\n"
        "После оплаты нажми кнопку 👇",
        parse_mode="Markdown",
        reply_markup=receipt_keyboard()
    )
    await state.set_state(BookingStates.waiting_receipt)
    await callback.answer()


@dp.callback_query(F.data == "paid")
async def paid_pressed(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "📸 Отправь скриншот чека — это подтвердит бронь!"
    )
    await callback.answer()


@dp.message(BookingStates.waiting_receipt, F.photo)
async def receive_receipt(message: types.Message, state: FSMContext):
    data = await state.get_data()

    await message.answer(
        f"🎉 *Бронь подтверждена!*\n\n"
        f"🎥 {data['film']}\n"
        f"📅 {data['date_display']} в {data['time']}\n"
        f"🎟 {data['tickets']} билет(а)\n"
        f"📍 {CINEMA_ADDRESS}\n\n"
        f"ℹ️ {CINEMA_INFO}\n\n"
        "До встречи! 🎬",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    await notify_admin(state, message.from_user, "Переводом на карту", message)
    await state.clear()


async def notify_admin(state, user, payment_method, message=None):
    data = await state.get_data()
    text = (
        f"🔔 *НОВАЯ БРОНЬ — {CINEMA_NAME}!*\n\n"
        f"🎥 {data['film']}\n"
        f"📅 {data['date_display']} в {data['time']}\n"
        f"🎟 {data['tickets']} билет(а)\n"
        f"💰 {data['total']} руб\n"
        f"💳 Оплата: {payment_method}\n"
        f"👤 {data['name']}\n"
        f"📱 {data['phone']}\n"
        f"🆔 @{user.username or 'нет'} (ID: {user.id})"
    )
    try:
        await bot.send_message(ADMIN_CHAT_ID, text, parse_mode="Markdown")
        if message:
            await bot.forward_message(ADMIN_CHAT_ID, message.chat.id, message.message_id)
    except Exception as e:
        logger.error(f"Ошибка уведомления: {e}")


@dp.callback_query(F.data == "cancel")
async def cancel(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Бронь отменена. Напиши /start чтобы начать заново.")
    await callback.answer()


async def main():
    logger.info("🎬 RoofCinema запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
