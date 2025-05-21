import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
CONFIG_PATH = "/home/simple1/bot/config/config.json"
USER_SETTINGS_PATH = "/home/simple1/bot/config/user_settings.json"
CURRENT_MODE_PATH = "/home/simple1/bot/data/current_mode.txt"
LAST_MODE_CHANGE_PATH = "/home/simple1/bot/data/last_mode_change.json"

def validate_config(config):
    required_fields = ["modes", "users", "nodes", "hashrate_log_path", "current_mode_path"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Отсутствует обязательное поле '{field}' в конфиге")
    for node, info in config["nodes"].items():
        if not all(k in info for k in ["user", "password", "host", "port"]):
            raise ValueError(f"Узел '{node}' должен содержать 'user', 'password', 'host', 'port'")
    for mode, info in config["modes"].items():
        if not all(k in info for k in ["coin", "algorithm"]):
            raise ValueError(f"Режим '{mode}' должен содержать 'coin' и 'algorithm'")
        if "pool_id" not in info:
            info["pool_id"] = f"{mode}-sha256-1"
            logger.info(f"Установлен дефолтный pool_id для режима '{mode}': {info['pool_id']}")

def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        validate_config(config)
        logger.info(f"Конфигурация загружена: {json.dumps(config, indent=2)}")
        return config
    except FileNotFoundError:
        logger.error("Файл конфигурации config.json не найден")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка синтаксиса в config.json: {e}")
        raise

def load_user_settings():
    default_timezone = "Europe/Moscow"
    try:
        if os.path.exists(USER_SETTINGS_PATH):
            with open(USER_SETTINGS_PATH, "r", encoding="utf-8") as f:
                user_settings = json.load(f)
                user_settings = {str(k): v for k, v in user_settings.items()}
                for chat_id, settings in user_settings.items():
                    if "timezone" not in settings or settings["timezone"] not in TIMEZONES:
                        user_settings[chat_id] = {"timezone": default_timezone}
                        logger.warning(f"Некорректный часовой пояс для chat_id {chat_id}. Установлен {default_timezone}.")
            logger.debug(f"Загружены настройки пользователей: {user_settings}")
        else:
            user_settings = {str(chat_id): {"timezone": default_timezone} for chat_id in CONFIG["users"].values()}
            with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(user_settings, f, ensure_ascii=False, indent=2)
            logger.debug(f"Создан {USER_SETTINGS_PATH} с настройками: {user_settings}")
        for chat_id in CONFIG["users"].values():
            chat_id_str = str(chat_id)
            if chat_id_str not in user_settings:
                user_settings[chat_id_str] = {"timezone": default_timezone}
                logger.info(f"Добавлены настройки для нового пользователя chat_id {chat_id_str}: {default_timezone}")
        save_user_settings(user_settings)
        return user_settings
    except Exception as e:
        logger.error(f"Ошибка при загрузке {USER_SETTINGS_PATH}: {e}")
        user_settings = {str(chat_id): {"timezone": default_timezone} for chat_id in CONFIG["users"].values()}
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(user_settings, f, ensure_ascii=False, indent=2)
        return user_settings

def save_user_settings(user_settings):
    try:
        with open(USER_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(user_settings, f, ensure_ascii=False, indent=2)
        logger.debug(f"Сохранены настройки пользователей в {USER_SETTINGS_PATH}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении {USER_SETTINGS_PATH}: {e}")

def get_user_timezone(chat_id: int) -> str:
    """
    Returns the timezone for the given chat_id, or 'Europe/Moscow' if not set.
    """
    try:
        user_settings = load_user_settings()
        chat_id_str = str(chat_id)
        return user_settings.get(chat_id_str, {}).get("timezone", "Europe/Moscow")
    except Exception as e:
        logger.error(f"Ошибка при получении часового пояса пользователя {chat_id}: {e}")
        return "Europe/Moscow"

def get_current_mode():
    try:
        with open(CURRENT_MODE_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "digi"

def set_current_mode(mode):
    with open(CURRENT_MODE_PATH, "w", encoding="utf-8") as f:
        f.write(mode)
    set_last_mode_change_time(mode)

def get_last_mode_change_time():
    default_time = datetime.now(timezone.utc)
    default_mode = "digi"
    default_data = {"timestamp": default_time.isoformat(), "mode": default_mode}
    try:
        if not os.path.exists(LAST_MODE_CHANGE_PATH):
            with open(LAST_MODE_CHANGE_PATH, "w", encoding="utf-8") as f:
                json.dump(default_data, f, ensure_ascii=False, indent=2)
            return default_data
        with open(LAST_MODE_CHANGE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        timestamp = datetime.fromisoformat(data["timestamp"]).replace(tzinfo=timezone.utc)
        mode = data["mode"]
        if mode not in CONFIG["modes"]:
            raise ValueError(f"Некорректный режим '{mode}'")
        return {"timestamp": timestamp, "mode": mode}
    except Exception as e:
        logger.error(f"Ошибка при чтении {LAST_MODE_CHANGE_PATH}: {e}")
        with open(LAST_MODE_CHANGE_PATH, "w", encoding="utf-8") as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        return default_data

def set_last_mode_change_time(mode):
    try:
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode
        }
        with open(LAST_MODE_CHANGE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка при записи в {LAST_MODE_CHANGE_PATH}: {e}")

CONFIG = load_config()
TIMEZONES = {
    "Europe/Moscow": "Москва (+03:00)",
    "Europe/Samara": "Санкт-Петербург (+03:00)",
    "Asia/Novosibirsk": "Новосибирск (+07:00)",
    "Asia/Irkutsk": "Иркутск (+08:00)"
}