
import asyncio
import json
import os
import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove, LabeledPrice, PreCheckoutQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

API_TOKEN = "8138182283:AAHSnvgi5j4ksM2--jr1b31SsVpI2qGF-YM"
PAYMENT_TOKEN = "YOUR_PAYMENT_TOKEN"  # <-- замените на свой токен

ADMINS = [1295147526, ]  # список ID админов

def is_admin(user_id):
    return user_id in ADMINS

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

FLOWERS_FILE = "flowers.json"
USERS_FILE = "users.json"
flowers = []
users = set()

def save_flowers():
    with open(FLOWERS_FILE, "w", encoding="utf-8") as f:
        json.dump(flowers, f, ensure_ascii=False, indent=2)

def load_flowers():
    global flowers
    if os.path.exists(FLOWERS_FILE):
        try:
            with open(FLOWERS_FILE, "r", encoding="utf-8") as f:
                flowers = json.load(f)
        except Exception:
            flowers = []
            save_flowers()
    else:
        flowers = []

def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f)

def load_users():
    global users
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users.update(json.load(f))
        except Exception:
            users.clear()
            save_users()
    else:
        users.clear()

load_flowers()
load_users()

carts = {}

CATEGORIES = ["Букеты", "Цветы в розницу", "Опт"]
category_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=cat)] for cat in CATEGORIES],
    resize_keyboard=True,
    one_time_keyboard=True
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Каталог")],
        [KeyboardButton(text="О нас"), KeyboardButton(text="Контакты")]
    ],
    resize_keyboard=True
)

pickup_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Доставка 🚚"), KeyboardButton(text="Самовывоз 🏪")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

payment_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Оплата при получении"), KeyboardButton(text="Онлайн оплата")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

DELIVERY_REGIONS = [
    "г. Тосно",
    "Тосненский район",
    "Ленинградская область",
    "г. Санкт-Петербург"
]
region_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=region)] for region in DELIVERY_REGIONS],
    resize_keyboard=True,
    one_time_keyboard=True
)

# --- Вспомогательная функция для добавления кнопки "Назад" ---
def with_back_kb(keyboard):
    kb = keyboard.keyboard.copy()
    kb.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

category_kb_with_back = with_back_kb(category_kb)
pickup_kb_with_back = with_back_kb(pickup_kb)
region_kb_with_back = with_back_kb(region_kb)
payment_kb_with_back = with_back_kb(payment_kb)

# Диапазоны цен по категориям
PRICE_RANGES = {
    "Букеты": [
        ("До 1000₽", 0, 1000),
        ("1000₽ — 3000₽", 1000, 3000),
        ("3000₽ — 5000₽", 3000, 5000),
        ("Свыше 5000₽", 5000, float("inf")),
    ],
    "Цветы в розницу": [
        ("До 100₽", 0, 100),
        ("100₽ — 200₽", 100, 200),
        ("200₽ — 300₽", 200, 300),
        ("300₽ — 500₽", 300, 500),
    ],
    "Опт": [
        ("До 100₽", 0, 100),
        ("100₽ — 200₽", 100, 200),
        ("200₽ — 300₽", 200, 300),
        ("300₽ — 500₽", 300, 500),
    ],
}

class AddFlower(StatesGroup):
    waiting_for_photo = State()
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_emoji = State()
    waiting_for_category = State()

class EditFlowerFSM(StatesGroup):
    waiting_for_action = State()
    waiting_for_new_name = State()
    waiting_for_new_price = State()
    waiting_for_new_emoji = State()
    waiting_for_new_category = State()

class OrderFSM(StatesGroup):
    choosing_delivery = State()
    choosing_region = State()
    entering_address = State()
    choosing_date = State()
    choosing_time = State()
    choosing_payment = State()
    waiting_for_order_confirm = State()
    waiting_payment = State()

class BroadcastFSM(StatesGroup):
    waiting_for_text = State()

def get_quantity_kb(idx, quantity=1):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data=f"decrease_{idx}_{quantity}"),
                InlineKeyboardButton(text=f"{quantity}", callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data=f"increase_{idx}_{quantity}")
            ],
            [
                InlineKeyboardButton(text="🛒 В корзину", callback_data=f"addcart_{idx}_{quantity}")
            ]
        ]
    )

def get_delivery_price(region, address, date, time):
    hour = int(time.split(":")[0]) if time else 12
    if region == "г. Тосно":
        if 22 <= hour or hour < 9:
            return 500
        return 250
    elif region == "Тосненский район":
        return 400
    elif region == "Ленинградская область":
        return 600
    elif region == "г. Санкт-Петербург":
        return 800
    return 0

@dp.message(Command("start"))
async def start(msg: Message):
    if msg.from_user.id not in users:
        users.add(msg.from_user.id)
        save_users()
    await msg.answer(
        "Добро пожаловать в магазин цветов! Мы рады видеть Вас здесь.\nВыберите действие:",
        reply_markup=main_menu
    )

@dp.message(lambda m: m.text == "Каталог")
async def menu_catalog(msg: Message, state: FSMContext):
    await msg.answer("Выберите категорию:", reply_markup=category_kb_with_back)
    await state.set_state("waiting_for_catalog_category")

@dp.message(lambda m: m.text == "О нас")
async def about(msg: Message):
    await msg.answer('- Круглосуточная доставка цветов по г. Тосно, Тосненскому району и Санкт-Петербургу \n-Сотрудничаем напрямую с плантациями Ленинградской области и Краснодарского края\n-Осуществляем корпоративные заказы (возможно заключение договора)\n-Полностью дистанционное оформление заказа\n-Мини опт для всех (условия уточняйте у менеджера)\n\nОплата\nПосле согласования всех нюансов заказа, необходимо произвести оплату.  Если заказан товар из наличия с экспресс доставкой, оплата возможна при получении наличными или переводом.\nДоставка\nДОСТАВКА осуществляется 24 часа! Доставка по г. Тосно от 250₽ Доставка по Тосненскому району, Ленинградской области, г. Санкт-Петербургу согласна тарифам Яндекса или другой службы доставки.  Временной интервал для доставки по Тосно - 30 минут По Ленинградской области и г. Санкт-Петербургу - 2-3 часа Экспресс доставка (только по г. Тосно) - доставка товара из наличия в течение часа с момента заказа - от 250₽ руб. Ночной тариф (с 22-9:00) по Тосно - от 500₽\nВозврат\n❗️Проверяйте качество цветов при получении Цветы являются живым товаром.  В соответствии с Законом Российской Федерации «О защите прав потребителей» от 07.02.1992 № 2300-1 и Постановлением Правительства Российской Федерации от 19.01.1998 № 55 срезанные цветы и горшечные растения обмену и возврату не подлежат (указаны в Перечне непродовольственных товаров надлежащего качества, не подлежащих возврату или обмену). Покупатель имеет право отказаться от получения товара в момент доставки, если доставлен товар ненадлежащего качества (на основании п.3 ст. 497 ГК РФ, статья 21 Закона "О защите прав потребителей").')

@dp.message(lambda m: m.text == "Контакты")
async def contacts(msg: Message):
    await msg.answer("Телефон: +79201860779\nVK: https://vk.com/bar_flower\nWhatsApp:https://clck.ru/3Nh8rH")

@dp.message(StateFilter("waiting_for_catalog_category"))
async def show_category(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    if msg.text not in CATEGORIES:
        await msg.answer("Пожалуйста, выберите категорию кнопкой.")
        return
    await state.update_data(selected_category=msg.text)
    ranges = PRICE_RANGES[msg.text]
    price_range_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label, _, _ in ranges] + [[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await msg.answer("Выберите диапазон цен:", reply_markup=price_range_kb)
    await state.set_state("waiting_for_price_range")

# --- Обновлённый обработчик выбора диапазона цен ---
@dp.message(StateFilter("waiting_for_price_range"))
async def show_price_range(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Выберите категорию:", reply_markup=category_kb_with_back)
        await state.set_state("waiting_for_catalog_category")
        return
    data = await state.get_data()
    category = data.get("selected_category")
    ranges = PRICE_RANGES[category]
    selected = None
    for label, min_price, max_price in ranges:
        if msg.text == label:
            selected = (min_price, max_price)
            break
    if not selected:
        await msg.answer("Пожалуйста, выберите диапазон цен кнопкой.")
        return
    min_price, max_price = selected
    items = [
        (idx, f) for idx, f in enumerate(flowers)
        if f.get("category") == category and min_price <= int(f.get("price", 0)) < max_price
    ]
    if not items:
        await msg.answer("В этом диапазоне нет товаров.", reply_markup=main_menu)
        await state.clear()
    else:
        for idx, flower in items:
            caption = f"{flower['emoji']} <b>{flower['name']}</b>\nЦена: {flower['price']} руб."
            kb = get_quantity_kb(idx, 1)
            await msg.answer_photo(flower['photo'], caption=caption, reply_markup=kb, parse_mode="HTML")
        # Клавиатура только с кнопкой "Назад"
        back_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="⬅️ Назад")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await msg.answer("Вернуться к выбору диапазона цен:", reply_markup=back_kb)
        await state.set_state("waiting_for_price_range_back")

# --- Новый обработчик возврата к диапазонам цен ---
@dp.message(StateFilter("waiting_for_price_range_back"))
async def price_range_back(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        data = await state.get_data()
        category = data.get("selected_category")
        ranges = PRICE_RANGES[category]
        price_range_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=label)] for label, _, _ in ranges] + [[KeyboardButton(text="⬅️ Назад")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await msg.answer("Выберите диапазон цен:", reply_markup=price_range_kb)
        await state.set_state("waiting_for_price_range")
    else:
        await msg.answer("Пожалуйста, используйте кнопку '⬅️ Назад'.")

@dp.callback_query(F.data.startswith("increase_"))
async def increase_quantity(callback: CallbackQuery):
    _, idx, quantity = callback.data.split("_")
    idx = int(idx)
    quantity = int(quantity) + 1
    await callback.message.edit_reply_markup(reply_markup=get_quantity_kb(idx, quantity))
    await callback.answer()

@dp.callback_query(F.data.startswith("decrease_"))
async def decrease_quantity(callback: CallbackQuery):
    _, idx, quantity = callback.data.split("_")
    idx = int(idx)
    quantity = max(1, int(quantity) - 1)
    await callback.message.edit_reply_markup(reply_markup=get_quantity_kb(idx, quantity))
    await callback.answer()

@dp.callback_query(F.data.startswith("addcart_"))
async def add_to_cart(callback: CallbackQuery):
    _, idx, quantity = callback.data.split("_")
    idx = int(idx)
    quantity = int(quantity)
    user_id = callback.from_user.id
    carts.setdefault(user_id, [])
    for _ in range(quantity):
        carts[user_id].append(flowers[idx])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="add_more")],
            [InlineKeyboardButton(text="📝 Оформить заказ", callback_data="checkout")]
        ]
    )
    await callback.message.answer(
        f"Добавлено в корзину: {quantity} шт.\nВ корзине: {len(carts[user_id])} шт.",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(F.data == "add_more")
async def add_more(callback: CallbackQuery):
    await callback.message.answer("Выберите категорию:", reply_markup=category_kb_with_back)

@dp.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Выберите способ получения:", reply_markup=pickup_kb_with_back)
    await state.set_state(OrderFSM.choosing_delivery)

@dp.message(OrderFSM.choosing_delivery)
async def choose_delivery(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    if msg.text.startswith("Доставка"):
        await state.update_data(delivery="Доставка")
        await msg.answer("Выберите регион доставки:", reply_markup=region_kb_with_back)
        await state.set_state(OrderFSM.choosing_region)
    elif msg.text.startswith("Самовывоз"):
        await state.update_data(delivery="Самовывоз", address="Самовывоз", region="г. Тосно")
        await msg.answer("Введите дату (например, 2024-06-10, где ГГГГ-ММ-ДД):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_date)
    else:
        await msg.answer("Пожалуйста, выберите способ получения кнопкой.")

@dp.message(OrderFSM.choosing_region)
async def choose_region(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Выберите способ получения:", reply_markup=pickup_kb_with_back)
        await state.set_state(OrderFSM.choosing_delivery)
        return
    if msg.text not in DELIVERY_REGIONS:
        await msg.answer("Пожалуйста, выберите регион кнопкой.")
        return
    await state.update_data(region=msg.text)
    await msg.answer("Введите адрес доставки:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(OrderFSM.entering_address)

@dp.message(OrderFSM.entering_address)
async def enter_address(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Выберите регион доставки:", reply_markup=region_kb_with_back)
        await state.set_state(OrderFSM.choosing_region)
        return
    await state.update_data(address=msg.text)
    await msg.answer("Введите дату (например, 2024-06-10):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(OrderFSM.choosing_date)

@dp.message(OrderFSM.choosing_date)
async def choose_date(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        data = await state.get_data()
        if data.get("delivery") == "Доставка":
            await msg.answer("Введите адрес доставки:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
            await state.set_state(OrderFSM.entering_address)
        else:
            await msg.answer("Выберите способ получения:", reply_markup=pickup_kb_with_back)
            await state.set_state(OrderFSM.choosing_delivery)
        return
    try:
        datetime.datetime.strptime(msg.text, "%Y-%m-%d")
        await state.update_data(date=msg.text)
        await msg.answer("Введите время (например, 15:30):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_time)
    except ValueError:
        await msg.answer("Неверный формат даты. Введите в формате ГГГГ-ММ-ДД.")

@dp.message(OrderFSM.choosing_time)
async def choose_time(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите дату (например, 2024-06-10):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_date)
        return
    try:
        datetime.datetime.strptime(msg.text, "%H:%M")
        await state.update_data(time=msg.text)
        await msg.answer("Выберите способ оплаты:", reply_markup=payment_kb_with_back)
        await state.set_state(OrderFSM.choosing_payment)
    except ValueError:
        await msg.answer("Неверный формат времени. Введите в формате ЧЧ:ММ.")

@dp.message(OrderFSM.choosing_payment)
async def choose_payment(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите время (например, 15:30):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_time)
        return
    if msg.text not in ["Оплата при получении", "Онлайн оплата"]:
        await msg.answer("Пожалуйста, выберите способ оплаты кнопкой.")
        return
    await state.update_data(payment=msg.text)
    data = await state.get_data()
    user_id = msg.from_user.id
    cart = carts.get(user_id, [])
    total = sum(int(f["price"]) for f in cart)
    delivery_price = 0
    if data.get("delivery") == "Доставка":
        delivery_price = get_delivery_price(
            data.get("region", ""), data.get("address", ""), data.get("date", ""), data.get("time", "")
        )
        total += delivery_price

    order_text = (
        f"Ваш заказ:\n"
        f"{chr(10).join([f'{f['emoji']} {f['name']} — {f['price']} руб.' for f in cart])}"
        + (f"\nДоставка: {delivery_price} руб." if delivery_price else "") +
        f"\nИтого к оплате: {total} руб.\n\n"
        f"Подтвердите заказ?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_order")]
        ]
    )
    await msg.answer(order_text, reply_markup=kb)
    await state.update_data(total=total, delivery_price=delivery_price, cart=cart)
    await state.set_state(OrderFSM.waiting_for_order_confirm)

@dp.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg = callback.message
    user_id = callback.from_user.id
    if data.get("payment") == "Онлайн оплата":
        prices = [LabeledPrice(label=f"{f['emoji']} {f['name']}", amount=int(f["price"]) * 100) for f in data["cart"]]
        if data["delivery_price"] > 0:
            prices.append(LabeledPrice(label="Доставка", amount=data["delivery_price"] * 100))
        await bot.send_invoice(
            chat_id=msg.chat.id,
            title="Оплата заказа",
            description="Ваш заказ в магазине цветов",
            payload="flowershop-order",
            provider_token=PAYMENT_TOKEN,
            currency="RUB",
            prices=prices,
            need_name=True,
            need_phone_number=True
        )
        await state.set_state(OrderFSM.waiting_payment)
    else:
        order_text = (
            f"Новый заказ!\n"
            f"Пользователь: @{callback.from_user.username}\n"
            f"Товары:\n" +
            "\n".join([f"{f['emoji']} {f['name']} — {f['price']} руб." for f in data["cart"]]) +
            (f"\nДоставка: {data['delivery_price']} руб." if data['delivery_price'] else "") +
            f"\nРегион: {data.get('region', '-')}" +
            f"\nСпособ: {data.get('delivery', '-')}\n"
            f"Адрес: {data.get('address', '-')}\n"
            f"Дата: {data.get('date', '-')}\n"
            f"Время: {data.get('time', '-')}\n"
            f"Оплата: {data.get('payment', '-')}\n"
            f"Итого: {data['total']} руб."
        )
        for admin_id in ADMINS:
            await bot.send_message(admin_id, order_text)
        await msg.answer("Ваш заказ отправлен администратору! Спасибо!", reply_markup=main_menu)
        carts[user_id] = []
        await state.clear()

@dp.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Заказ отменён.", reply_markup=main_menu)
    await state.clear()

@dp.pre_checkout_query()
async def process_pre_checkout_query(pre_checkout_q: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_q.id, ok=True)

@dp.message(F.successful_payment)
async def process_successful_payment(msg: Message, state: FSMContext):
    user_id = msg.from_user.id
    data = await state.get_data()
    cart = data.get("cart", [])
    delivery_price = data.get("delivery_price", 0)
    order_text = (
        f"Новый онлайн-заказ!\n"
        f"Пользователь: @{msg.from_user.username}\n"
        f"Товары:\n" +
        "\n".join([f"{f['emoji']} {f['name']} — {f['price']} руб." for f in cart]) +
        (f"\nДоставка: {delivery_price} руб." if delivery_price else "") +
        f"\nРегион: {data.get('region', '-')}" +
        f"\nСпособ: {data.get('delivery', '-')}\n"
        f"Адрес: {data.get('address', '-')}\n"
        f"Дата: {data.get('date', '-')}\n"
        f"Время: {data.get('time', '-')}\n"
        f"Оплата: Онлайн"
    )
    for admin_id in ADMINS:
        await bot.send_message(admin_id, order_text)
    await msg.answer("Оплата прошла успешно! Ваш заказ отправлен администратору. Спасибо!", reply_markup=main_menu)
    carts[user_id] = []
    await state.clear()

# --- Добавление товара (админ) с кнопкой "Назад" ---
@dp.message(Command("add"))
async def add_flower(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    await msg.answer("Отправьте фото товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_photo)

@dp.message(AddFlower.waiting_for_photo)
async def add_flower_photo(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    if not msg.photo:
        await msg.answer("Пожалуйста, отправьте фото.")
        return
    await state.update_data(photo=msg.photo[-1].file_id)
    await msg.answer("Введите название товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_name)

@dp.message(AddFlower.waiting_for_name)
async def add_flower_name(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Отправьте фото товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_photo)
        return
    await state.update_data(name=msg.text)
    await msg.answer("Введите цену:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_price)

@dp.message(AddFlower.waiting_for_price)
async def add_flower_price(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите название товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_name)
        return
    await state.update_data(price=msg.text)
    await msg.answer("Добавьте смайлик для товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_emoji)

@dp.message(AddFlower.waiting_for_emoji)
async def add_flower_emoji(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите цену:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_price)
        return
    await state.update_data(emoji=msg.text)
    await msg.answer("Выберите категорию:", reply_markup=category_kb_with_back)
    await state.set_state(AddFlower.waiting_for_category)

@dp.message(AddFlower.waiting_for_category)
async def add_flower_category(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Добавьте смайлик для товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_emoji)
        return
    if msg.text not in CATEGORIES:
        await msg.answer("Пожалуйста, выберите категорию кнопкой.")
        return
    data = await state.get_data()
    flowers.append({
        'photo': data['photo'],
        'name': data['name'],
        'price': data['price'],
        'emoji': data['emoji'],
        'category': msg.text
    })
    save_flowers()
    await msg.answer("Товар добавлен в каталог!", reply_markup=main_menu)
    await state.clear()

@dp.message(Command("edit"))
async def edit_catalog(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    if not flowers:
        await msg.answer("Каталог пуст.")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{f['emoji']} {f['name']}", callback_data=f"edit_{i}")]
            for i, f in enumerate(flowers)
        ]
    )
    await msg.answer("Выберите товар для редактирования или удаления:", reply_markup=kb)

@dp.callback_query(F.data.startswith("edit_"))
async def choose_edit(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[1])
    await state.update_data(idx=idx)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить", callback_data="edit_change")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data="edit_delete")]
        ]
    )
    flower = flowers[idx]
    await callback.message.answer(
        f"Товар: {flower['emoji']} {flower['name']} — {flower['price']} руб.\nЧто сделать?",
        reply_markup=kb
    )
    await state.set_state(EditFlowerFSM.waiting_for_action)

@dp.callback_query(F.data == "edit_delete")
async def delete_flower(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data["idx"]
    flower = flowers.pop(idx)
    save_flowers()
    await callback.message.answer(f"Товар {flower['name']} удалён.", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.callback_query(F.data == "edit_change")
async def change_flower(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новое название (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(EditFlowerFSM.waiting_for_new_name)

@dp.message(EditFlowerFSM.waiting_for_new_name)
async def edit_name(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(new_name=msg.text)
    await msg.answer("Введите новую цену (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(EditFlowerFSM.waiting_for_new_price)

@dp.message(EditFlowerFSM.waiting_for_new_price)
async def edit_price(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите новое название (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(EditFlowerFSM.waiting_for_new_name)
        return
    await state.update_data(new_price=msg.text)
    await msg.answer("Введите новый смайлик (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(EditFlowerFSM.waiting_for_new_emoji)

@dp.message(EditFlowerFSM.waiting_for_new_emoji)
async def edit_emoji(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите новую цену (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(EditFlowerFSM.waiting_for_new_price)
        return
    await state.update_data(new_emoji=msg.text)
    await msg.answer("Выберите новую категорию (или '-' чтобы не менять):", reply_markup=category_kb_with_back)
    await state.set_state(EditFlowerFSM.waiting_for_new_category)

@dp.message(EditFlowerFSM.waiting_for_new_category)
async def edit_category(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите новый смайлик (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(EditFlowerFSM.waiting_for_new_emoji)
        return
    data = await state.get_data()
    idx = data["idx"]
    if data["new_name"] != "-":
        flowers[idx]["name"] = data["new_name"]
    if data["new_price"] != "-":
        flowers[idx]["price"] = data["new_price"]
    if data["new_emoji"] != "-":
        flowers[idx]["emoji"] = data["new_emoji"]
    if msg.text in CATEGORIES:
        flowers[idx]["category"] = msg.text
    save_flowers()
    await msg.answer("Товар обновлён!", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.message(Command("broadcast"))
async def start_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    await msg.answer("Введите текст рассылки:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(BroadcastFSM.waiting_for_text)

@dp.message(StateFilter(BroadcastFSM.waiting_for_text))
async def do_broadcast(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    text = msg.text
    count = 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            count += 1
        except Exception:
            pass
    await msg.answer(f"Рассылка завершена. Отправлено {count} пользователям.")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())