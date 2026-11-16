# FunPay Telegram Bot

Бот для FunPay: уведомления о сообщениях, заказах и смене статусов прямо в Telegram. Можно отвечать покупателям не заходя на сайт.

## Возможности

- Уведомления о новых сообщениях (с указанием товара)
- Уведомления о новых заказах
- Уведомления о смене статуса заказа (оплачен, подтверждён, возврат)
- Ответы покупателям через Telegram (/reply или ответ на сообщение бота)
- Фильтрация: свои сообщения и автоответы не показываются

## Настройка

Открой файл `bot.py` и заполни 3 строки в самом начале:

```python
GOLDEN_KEY = ""          # Твой Golden Key с FunPay ( Настройки → Безопасность → API)
TELEGRAM_TOKEN = ""      # Токен твоего Telegram бота (от @BotFather)
ALLOWED_USER_IDS = [ , ] # Telegram ID пользователей, которым доступен бот
```

### Где взять:

**Golden Key:**
1. скачай editthiscookie
2. нажми на печеньку справа сверху
3. Скопируй golden_key

**Telegram Token:**
1. Открой @BotFather в Telegram
2. Напиши `/newbot`
3. Скопируй токен

**Telegram ID:**
1. Открой @userinfobot в Telegram
2. Нажми Start — он покажет твой ID
3. Сделай то же для каждого пользователя, которому нужен доступ

## Установка и запуск

```bash
# Клонировать
git clone https://github.com/Melkis111/funpaybot.git
cd funpaybot

# Установить зависимости
pip install -r requirements.txt

# Запустить
python bot.py
```

## Команды бота в Telegram

| Команда | Описание |
|---------|----------|
| `/start` | Приветствие и список команд |
| `/chats` | Список активных чатов с ID |
| `/reply ID текст` | Ответить в чат на FunPay |

Также можно просто ответить на сообщение бота в Telegram — ответ уйдёт в FunPay.

## Автозапуск (VPS)

```bash
cat > /etc/systemd/system/funpaybot.service << 'EOF'
[Unit]
Description=FunPay Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/funpaybot
ExecStart=/root/funpaybot/venv/bin/python3 bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable funpaybot
systemctl start funpaybot
```
