#!/bin/bash
# Скрипт для установки зависимостей для Stratum-прокси и Telegram-бота с использованием виртуального окружения

# Базовая директория проекта — родительская директория папки scripts/
SCRIPT_DIR=$(dirname "$(realpath "$0")")
BASE_DIR=$(dirname "$SCRIPT_DIR")
VENV_DIR="$BASE_DIR/venv"

# Обновление системы
echo "Обновление системы..."
sudo apt update
sudo apt install -y python3 python3-pip python3-venv libzmq3-dev postgresql postgresql-contrib

# Создание виртуального окружения
echo "Создание виртуального окружения в $VENV_DIR..."
python3 -m venv "$VENV_DIR"

# Активация виртуального окружения
echo "Активация виртуального окружения..."
source "$VENV_DIR/bin/activate"

# Установка Python-зависимостей в виртуальное окружение
echo "Установка Python-зависимостей..."
pip install aiogram==3.3.0 aiohttp==3.9.5 watchdog==2.1.9 pandas==1.5.3 pytz

# Деактивация виртуального окружения (на случай, если скрипт используется интерактивно)
deactivate

# Установка прав
echo "Установка прав на $BASE_DIR..."
sudo chown -R simple1:simple1 "$BASE_DIR"
sudo chmod -R 755 "$BASE_DIR"

# Инструкции для запуска
echo "Зависимости установлены. Для запуска Stratum-прокси и Telegram-бота используйте виртуальное окружение:"
echo "1. Активируйте виртуальное окружение:"
echo "   source $VENV_DIR/bin/activate"
echo "2. Запустите Stratum-прокси:"
echo "   python3 $BASE_DIR/src/stratum_proxy/proxy.py"
echo "3. Запустите Telegram-бот:"
echo "   python3 $BASE_DIR/src/telegram_bot/bot.py"
echo "4. Для выхода из виртуального окружения:"
echo "   deactivate"