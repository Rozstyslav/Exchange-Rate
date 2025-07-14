import telebot
from telebot import types
import requests
import locale
from datetime import datetime, timedelta

token = ''

bot = telebot.TeleBot(token)

user_states = {}

today = datetime.now().strftime("%Y%m%d")
yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

url_today = f'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?date={today}&json'
url_yesterday = f'https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?date={yesterday}&json'

BUTTON_ONLY_STATES = {
    'send_welcome',
    'menu',
    'exchange_rate',
    'calculate',
    'choose_currency',
    'choose_way',
    'convert',
}

@bot.message_handler(
    func=lambda message: (
            message.chat.id in user_states
            and isinstance(user_states[message.chat.id], dict)
            and user_states[message.chat.id].get('step') in BUTTON_ONLY_STATES
            and not (message.text and message.text.startswith('/'))
    )
)
def handle_invalid_button_input(message):
    bot.send_message(
        message.chat.id,
        "❌ Sorry, that option isn’t available right now.\n"
        "To view the menu, type /menu.\n"
        "To cancel, type /cancel."
    )

@bot.message_handler(commands=['start'])
def send_welcome(message):
    chat_id = message.chat.id
    user_states[chat_id] = {'step': 'send_welcome'}
    bot.send_message(chat_id, "👋 Welcome! Type /menu to begin.")

@bot.message_handler(commands=['menu'])
def menu(message):
    chat_id = message.chat.id
    user_states[chat_id] = {'step': 'menu'}

    markup = types.InlineKeyboardMarkup()
    but1 = types.InlineKeyboardButton("📊 Exchange Rate", callback_data="exchange_rate")
    but2 = types.InlineKeyboardButton("💱 Calculate", callback_data="calculate")
    markup.add(but1, but2)

    bot.send_message(message.chat.id, "Choose your option: ", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "exchange_rate")
def exchange_rate(call):
    chat_id = call.message.chat.id
    user_states[chat_id] = {'step': 'exchange_rate'}

    markup = types.InlineKeyboardMarkup()
    back_btn = types.InlineKeyboardButton("🔙 Back to Menu",callback_data="back_to_menu")
    markup.add(back_btn)

    r_today = requests.get(url_today)
    r_yesterday = requests.get(url_yesterday)

    if r_today.status_code == 200 and r_yesterday.status_code == 200:
        data_today = r_today.json()
        data_yesterday = r_yesterday.json()

        filtered = [c for c in data_today if float(c['rate']) > 0]
        exchangedate = filtered[0]['exchangedate'] if filtered else 'Unknown'

        try:
            locale.setlocale(locale.LC_COLLATE, 'uk_UA.UTF-8')
            filtered.sort(key=lambda c: locale.strxfrm(c['txt']))
        except locale.Error:
            filtered.sort(key=lambda c: c['cc'])

        result = f"💱 *NBU Exchange Rates: {exchangedate}*\n"

        for c in filtered:
            code = c['cc']
            name = f"{c['txt']} ({code}):"
            rate_float = float(c['rate'])

            y_c = next((y for y in data_yesterday if y['cc'] == code), None)
            if y_c:
                rate_yesterday = float(y_c['rate'])
                diff = rate_float - rate_yesterday
                if diff > 0:
                    trend = f" 📈 +{diff:.2f}"
                elif diff < 0:
                    trend = f" 📉 {diff:.2f}"
                else:
                    trend = f" ➖ 0.00"
            else:
                trend = " ❓"

            result += f"{name}\n{rate_float:.4f} UAH{trend}\n\n"

        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, result.strip(), parse_mode="Markdown",reply_markup=markup)

    else:
        bot.send_message(call.message.chat.id, "❌ Couldn't fetch the exchange rates.")


@bot.callback_query_handler(func=lambda call: call.data == "calculate")
def calculate(call):
    chat_id = call.message.chat.id
    user_states[chat_id] = {'step': 'calculate'}

    response = requests.get(url_today)

    if response.status_code == 200:
        data = response.json()

        filtered = [c for c in data if float(c['rate']) > 0.00]

        try:
            locale.setlocale(locale.LC_COLLATE, 'uk_UA.UTF-8')
            filtered.sort(key=lambda c: locale.strxfrm(c['txt']))
        except locale.Error:
            filtered.sort(key=lambda c: c['cc'])

        markup = types.InlineKeyboardMarkup()

        for c in filtered:
            btn = types.InlineKeyboardButton(f"{c['txt']} - {c['cc']}", callback_data=f"currency_{c['cc']}")
            markup.add(btn)

        back_btn = types.InlineKeyboardButton("🔙 Back to Menu",callback_data="back_to_menu")
        markup.add(back_btn)

        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "💱 Choose a currency to convert:", reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, "❌ Couldn't fetch currency list.")


@bot.callback_query_handler(func=lambda call: call.data.startswith("currency_"))
def choose_currency(call):
    chat_id = call.message.chat.id
    user_states[chat_id] = {'step': 'choose_currency'}

    currency_code = call.data.split("_")[1]

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(f"UAH ➡ {currency_code}", callback_data=f"to_{currency_code}"),
        types.InlineKeyboardButton(f"{currency_code} ➡ UAH", callback_data=f"from_{currency_code}"),
    )
    markup.add(types.InlineKeyboardButton("🔙 Back to Currency", callback_data="calculate"))

    bot.answer_callback_query(call.id)
    bot.send_message(chat_id, f"💰 Chosen currency: {currency_code}\n💱 Choose how to convert:", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data.startswith(("to_", "from_")))
def choose_way(call):
    chat_id = call.message.chat.id
    way, currency = call.data.split("_")

    user_states[chat_id] = {
        'currency': currency,
        'way': way,
        'step': 'await_amount'
    }

    bot.answer_callback_query(call.id)
    if way == "to":
        prompt = f"💵 Enter amount in UAH to convert to {currency}:"
    else:
        prompt = f"💵 Enter amount in {currency} to convert to UAH:"

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("/cancel"))

    bot.send_message(chat_id, prompt, reply_markup=markup)


@bot.message_handler(func=lambda message: (
        message.chat.id in user_states
        and user_states[message.chat.id].get('step') == 'await_amount'))
def convert(message):
    chat_id = message.chat.id
    state = user_states[chat_id]
    currency = state.get('currency')
    way = state.get('way')

    if message.text == "/cancel":
        return cancel(message)


    try:
        amount = float(message.text.replace(",", "."))
    except ValueError:
        return bot.send_message(chat_id, "❌ Please enter a valid number (e.g., 100.50)")


    response = requests.get(url_today)
    if response.status_code != 200:
        return bot.send_message(chat_id, "❌ Couldn't fetch exchange rate.")
    rates = response.json()
    cur = next((c for c in rates if c['cc'] == currency), None)
    if not cur:
        return bot.send_message(chat_id, "❌ Currency not found.")


    rate = cur['rate']
    if way == "to":
        result = amount / rate
        text = f"✅ {amount:.2f} UAH = {result:.2f} {currency}"

    else:
        result = amount * rate
        text = f"✅ {amount:.2f} {currency} = {result:.2f} UAH"

    bot.send_message(chat_id, text)

    prompt = (
        f"💵 Enter another amount in UAH to convert to {currency}:"
        if way == "to"
        else f"💵 Enter another amount in {currency} to convert to UAH:"
    )
    bot.send_message(chat_id, prompt)


@bot.message_handler(commands=['cancel'])
def cancel(message):
    chat_id = message.chat.id
    user_states.pop(chat_id, None)
    markup = types.ReplyKeyboardRemove()
    bot.send_message(chat_id, "❌ Operation canceled. Use /menu to start again.", reply_markup=markup)


@bot.callback_query_handler(func=lambda call: call.data == "back_to_menu")
def back_to_menu(call):
    bot.answer_callback_query(call.id)
    menu(call.message)


@bot.callback_query_handler(func=lambda call: call.data == "another_amount")
def another_amount(call):
    choose_way(call)

bot.polling(non_stop=True)
