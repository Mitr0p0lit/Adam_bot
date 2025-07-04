import json
import re
from datetime import datetime
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    filters
)

# Состояния диалога
GET_NAME, GET_ORDER, CONFIRM_ORDER = range(3)

# Файл для сохранения данных
DATA_FILE = "orders.json"
ADMIN_ID = None  # Замените на ваш ID для получения уведомлений

# Клавиатура для отмены
CANCEL_KEYBOARD = ReplyKeyboardMarkup([["/cancel"]], resize_keyboard=True)

def load_orders():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"orders": []}

def save_order(order_data):
    data = load_orders()
    order_data["timestamp"] = datetime.now().isoformat()
    data["orders"].append(order_data)
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.message.from_user
    await update.message.reply_text(
        f"Привет, {user.first_name}!\n"
        "Я помогу оформить ваш заказ.\n"
        "Пожалуйста, введите ваше полное имя:",
        reply_markup=CANCEL_KEYBOARD
    )
    return GET_NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    
    # Проверка формата имени
    if not re.match(r"^[а-яА-ЯёЁa-zA-Z\s-]{2,50}$", name):
        await update.message.reply_text(
            "❌ Имя должно содержать только буквы и быть от 2 до 50 символов.\n"
            "Пожалуйста, введите ваше имя правильно:",
            reply_markup=CANCEL_KEYBOARD
        )
        return GET_NAME
    
    context.user_data['name'] = name
    
    # Примеры популярных товаров
    reply_keyboard = [
        ["Введи сколько и чего"]
    ]
    
    await update.message.reply_text(
        f"Отлично, {name}!\n"
        "Теперь введите товары для заказа (через запятую):\n"
        "Вы можете использовать кнопки ниже или ввести свой список.",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard, 
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Например: Молоко, Хлеб, Яблоки"
        )
    )
    return GET_ORDER

async def get_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    order_text = update.message.text
    
    # Обработка выбора "Свой вариант"
    if order_text == "Свой вариант":
        await update.message.reply_text(
            "Введите ваш список товаров через запятую:",
            reply_markup=ReplyKeyboardRemove()
        )
        return GET_ORDER
    
    # Очистка и валидация товаров
    order_items = [item.strip() for item in order_text.split(",")]
    valid_items = []
    
    for item in order_items:
        if item:
            if len(item) < 2 or len(item) > 50:
                await update.message.reply_text(
                    f"❌ Название товара '{item[:20]}...' слишком короткое или длинное. "
                    "Допустимая длина: 2-50 символов.\n"
                    "Пожалуйста, введите товары еще раз:",
                    reply_markup=CANCEL_KEYBOARD
                )
                return GET_ORDER
            valid_items.append(item)
    
    if not valid_items:
        await update.message.reply_text(
            "❌ Вы не ввели ни одного товара.\n"
            "Пожалуйста, введите товары для заказа:",
            reply_markup=CANCEL_KEYBOARD
        )
        return GET_ORDER
    
    context.user_data['order'] = valid_items
    
    # Клавиатура подтверждения
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm"),
            InlineKeyboardButton("✏️ Изменить", callback_data="edit")
        ]
    ]
    
    order_list = "\n".join(f"• {item}" for item in valid_items)
    
    await update.message.reply_text(
        f"📋 Ваш заказ:\n"
        f"👤 Имя: {context.user_data['name']}\n"
        f"🛒 Товары:\n{order_list}\n\n"
        "Подтверждаете заказ?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return CONFIRM_ORDER

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm":
        # Сохранение заказа
        save_order({
            "user_id": query.from_user.id,
            "name": context.user_data['name'],
            "order": context.user_data['order'],
            "username": query.from_user.username
        })
        
        await query.edit_message_text(
            "✅ Ваш заказ успешно сохранен!\n"
            "Спасибо за использование нашего сервиса.\n\n"
            "Для нового заказа введите /start"
        )
        
        # Уведомление администратору
        if ADMIN_ID:
            order_list = "\n".join(f"• {item}" for item in context.user_data['order'])
            await context.bot.send_message(
                ADMIN_ID,
                f"📦 Новый заказ!\n"
                f"👤: {context.user_data['name']} (@{query.from_user.username or 'N/A'})\n"
                f"🛒 Товары:\n{order_list}"
            )
        
        return ConversationHandler.END
    
    elif query.data == "edit":
        await query.edit_message_text(
            "Введите новый список товаров через запятую:",
            reply_markup=ReplyKeyboardRemove()
        )
        return GET_ORDER

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "❌ Заказ отменен.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id != ADMIN_ID:
        await update.message.reply_text("Эта команда доступна только администратору.")
        return
    
    orders = load_orders()
    if not orders["orders"]:
        await update.message.reply_text("Заказов пока нет.")
        return
    
    response = "📋 Все заказы:\n\n"
    for idx, order in enumerate(orders["orders"], 1):
        order_list = ", ".join(order["order"])
        date = datetime.fromisoformat(order["timestamp"]).strftime("%d.%m.%Y %H:%M")
        response += (
            f"🔹 Заказ #{idx}\n"
            f"👤: {order['name']} (@{order.get('username', 'N/A')})\n"
            f"🛒: {order_list}\n"
            f"⏰: {date}\n\n"
        )
    
    await update.message.reply_text(response)

def main() -> None:
    application = Application.builder().token("7776130295:AAHUQiXUIXEZfpXxuGVeW89ekQIf17wqhCU").build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            GET_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)
            ],
            GET_ORDER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_order)
            ],
            CONFIRM_ORDER: [
                CallbackQueryHandler(confirm_order)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("orders", view_orders))
    
    application.run_polling()

if __name__ == "__main__":
    main()