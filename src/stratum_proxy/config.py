import json
import logging
import os

logger = logging.getLogger(__name__)
CONFIG_PATH = "/home/simple1/bot/config/config.json"
CURRENT_MODE_PATH = "/home/simple1/bot/data/current_mode.txt"

def validate_config(config):
    required_fields = ["modes"]
    for field in required_fields:
        if field not in config:
            raise ValueError(f"Отсутствует обязательное поле '{field}' в конфиге")
    for mode, info in config["modes"].items():
        if "port" not in info or "alias" not in info:
            raise ValueError(f"Режим '{mode}' должен содержать 'port' и 'alias'")

def load_config():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
        validate_config(config)
        logger.info(f"Конфигурация загружена: {json.dumps(config, indent=2)}")
        return config
    except FileNotFoundError:
        logger.error(f"Файл конфигурации {CONFIG_PATH} не найден")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка синтаксиса в {CONFIG_PATH}: {e}")
        raise
    except ValueError as e:
        logger.error(f"Ошибка валидации конфигурации: {e}")
        raise

def get_current_mode():
    if not os.path.exists(CURRENT_MODE_PATH):
        with open(CURRENT_MODE_PATH, 'w', encoding='utf-8') as f:
            f.write("сон")
        return "сон"
    with open(CURRENT_MODE_PATH, 'r', encoding='utf-8') as f:
        return f.read().strip()