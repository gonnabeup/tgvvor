import asyncio
import csv
import logging
from datetime import datetime, timezone, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
import aiohttp
from .config import CONFIG, load_user_settings, save_user_settings, get_current_mode, set_current_mode, get_last_mode_change_time, TIMEZONES
from .utils import format_hashrate, format_timestamp, get_worker_short_name, format_uptime
from .log_parser import LogParser

logger = logging.getLogger(__name__)
bot = Bot(token="Ytokeeeen")  
dp = Dispatcher()
modes = CONFIG["modes"]
users = CONFIG["users"]
nodes = CONFIG["nodes"]
hashrate_log_path = CONFIG["hashrate_log_path"]
authorized_chats = set()
last_message_ids = {}
last_worker_stats_message_ids = {}
last_summary_message_ids = {}
last_detailed_stats_message_ids = {}
last_hashrates = {}
worker_stats = {}
worker_id_to_name = {}
last_hashrate_reports = {}
last_worker_stats_reports = {}
last_summary_reports = {}
last_detailed_stats_reports = {}
block_timestamps = {}
user_settings = load_user_settings()

async def delete_message_later(chat_id: int, message_id: int, delay: int = 600):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Удалено сообщение {message_id} в чате {chat_id}")
    except Exception as e:
        logger.warning(f"Не удалось удалить сообщение {message_id} в чате {chat_id}: {e}")

async def clear_previous_worker_stats(chat_id: int):
    if chat_id in last_worker_stats_message_ids:
        for message_id in last_worker_stats_message_ids[chat_id]:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение воркеров {message_id}: {e}")
        last_worker_stats_message_ids[chat_id] = []

async def clear_previous_summary(chat_id: int):
    if chat_id in last_summary_message_ids:
        for message_id in last_summary_message_ids[chat_id]:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение сводного отчета {message_id}: {e}")
        last_summary_message_ids[chat_id] = []

async def clear_previous_detailed_stats(chat_id: int):
    if chat_id in last_detailed_stats_message_ids:
        for message_id in last_detailed_stats_message_ids[chat_id]:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception as e:
                logger.warning(f"Не удалось удалить сообщение детализированной статистики {message_id}: {e}")
        last_detailed_stats_message_ids[chat_id] = []

def build_mode_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for mode in modes.keys():
        builder.add(InlineKeyboardButton(text=mode, callback_data=f"set_mode:{mode}"))
    builder.add(InlineKeyboardButton(text="🔄 Обновить хэшрейт", callback_data="update_hashrate"))
    builder.add(InlineKeyboardButton(text="📈 Статистика воркеров", callback_data="worker_stats"))
    builder.add(InlineKeyboardButton(text="📊 Общий отчет", callback_data="summary_report"))
    builder.add(InlineKeyboardButton(text="📉 Детализированная статистика", callback_data="detailed_stats"))
    builder.add(InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings"))
    builder.adjust(2)
    return builder.as_markup()

def build_settings_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for tz, label in TIMEZONES.items():
        builder.add(InlineKeyboardButton(text=label, callback_data=f"set_timezone:{tz}"))
    builder.add(InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main"))
    builder.adjust(2)
    return builder.as_markup()

def calculate_block_stats(pool_id: str):
    current_time = datetime.now(timezone.utc)
    start_of_day = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    blocks_today = sum(1 for ts in block_timestamps.get(pool_id, []) if ts >= start_of_day)
    hours_elapsed = (current_time - start_of_day).total_seconds() / 3600
    blocks_per_hour = blocks_today / hours_elapsed if hours_elapsed > 0 and blocks_today > 0 else 0
    return blocks_today, blocks_per_hour

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Используйте: /start <alias>")
        return
    alias = parts[1]
    chat_id = message.chat.id
    if alias in users and users[alias] == chat_id:
        authorized_chats.add(chat_id)
        await clear_previous_worker_stats(chat_id)
        await clear_previous_summary(chat_id)
        await clear_previous_detailed_stats(chat_id)
        await message.answer(
            f"✅ Добро пожаловать, {alias}!\nТекущий режим: *{get_current_mode()}*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_mode_keyboard()
        )
        await send_summary_report(chat_id)
    else:
        await message.answer("❌ Доступ запрещён.")
        logger.warning(f"Неавторизованная попытка: alias={alias}, chat_id={chat_id}")

@dp.callback_query(lambda c: c.data.startswith("set_mode:"))
async def mode_switch_callback(callback: types.CallbackQuery):
    mode = callback.data.split(":", 1)[1]
    if mode not in modes:
        await callback.answer("Неизвестный режим.")
        return
    current_mode = get_current_mode()
    if mode == current_mode:
        await callback.answer("Этот режим уже активен.")
        return
    set_current_mode(mode)
    global worker_stats, worker_id_to_name
    worker_stats = {}
    worker_id_to_name = {}
    await callback.message.edit_text(
        f"✅ Режим переключён на *{mode}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_mode_keyboard()
    )
    await callback.answer()
    logger.info(f"Режим переключён на {mode} для чата {callback.message.chat.id}")

@dp.callback_query(lambda c: c.data == "update_hashrate")
async def update_hashrate_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in authorized_chats:
        await callback.answer("❌ Доступ запрещён.")
        return
    await send_hashrate_report(chat_id)
    await callback.answer("Хэшрейт обновлён.")

@dp.callback_query(lambda c: c.data == "worker_stats")
async def worker_stats_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in authorized_chats:
        await callback.answer("❌ Доступ запрещён.")
        return
    await send_worker_stats_report(chat_id)
    await callback.answer("Статистика воркеров обновлена.")

@dp.callback_query(lambda c: c.data == "summary_report")
async def summary_report_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in authorized_chats:
        await callback.answer("❌ Доступ запрещён.")
        return
    await send_summary_report(chat_id)
    await callback.answer("Общий отчет обновлён.")

@dp.callback_query(lambda c: c.data == "detailed_stats")
async def detailed_stats_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in authorized_chats:
        await callback.answer("❌ Доступ запрещён.")
        return
    await send_detailed_stats_report(chat_id)
    await callback.answer("Детализированная статистика обновлена.")

@dp.callback_query(lambda c: c.data == "settings")
async def settings_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in authorized_chats:
        await callback.answer("❌ Доступ запрещён.")
        return
    await callback.message.edit_text(
        "⚙️ *Настройки*\nВыберите часовой пояс:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("set_timezone:"))
async def set_timezone_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    timezone = callback.data.split(":", 1)[1]
    user_settings = load_user_settings()  # Load current settings
    user_settings[str(chat_id)] = {"timezone": timezone}
    save_user_settings(user_settings)     # Pass as argument!
    await callback.answer(f"Часовой пояс установлен: {timezone}")
    await callback.message.edit_text(
        "✅ Часовой пояс обновлён.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_settings_keyboard()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main_callback(callback: types.CallbackQuery):
    chat_id = callback.message.chat.id
    if chat_id not in authorized_chats:
        await callback.answer("❌ Доступ запрещён.")
        return
    await callback.message.edit_text(
        f"Текущий режим: *{get_current_mode()}*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_mode_keyboard()
    )
    await callback.answer()

async def get_hashrate(node, session: aiohttp.ClientSession, algorithm: str):
    url = f"http://{node['host']}:{node['port']}"
    headers = {"content-type": "application/json"}
    params = [120, -1]
    if algorithm == "sha256d":
        params.append("sha256d")
    payload = {
        "method": "getnetworkhashps",
        "params": params,
        "id": 1,
        "jsonrpc": "2.0"
    }
    auth = aiohttp.BasicAuth(node["user"], node["password"])
    try:
        async with session.post(url, headers=headers, json=payload, auth=auth) as resp:
            if resp.status != 200:
                logger.error(f"Ошибка RPC у {url}: статус {resp.status}")
                return None
            result = await resp.json()
            if "result" in result:
                return result["result"]
            logger.error(f"Ошибка RPC у {url}: {result}")
            return None
    except Exception as e:
        logger.error(f"Ошибка RPC у {url}: {e}")
        return None

async def send_hashrate_report(chat_id: int):
    async with aiohttp.ClientSession() as session:
        timestamp = datetime.now(timezone.utc).isoformat()
        report_lines = []
        csv_line = [timestamp]
        hashrates = {}
        for node_name, node in nodes.items():
            current_mode = get_current_mode()
            algorithm = modes[current_mode]["algorithm"]
            hashrate = await get_hashrate(node, session, algorithm)
            if hashrate is not None:
                formatted_hashrate = format_hashrate(hashrate)
                report_lines.append(f"*{node_name}*: `{formatted_hashrate}`")
                csv_line.append(f"{hashrate}")
                hashrates[node_name] = hashrate
            else:
                report_lines.append(f"*{node_name}*: ❌ ошибка")
                csv_line.append("error")
                hashrates[node_name] = None
        with open(hashrate_log_path, "a", encoding="utf-8", newline='') as f:
            writer = csv.writer(f)
            writer.writerow(csv_line)
        for name, hashrate in hashrates.items():
            if hashrate is None:
                continue
            last_hashrate = last_hashrates.get(name)
            if last_hashrate and hashrate < last_hashrate * 0.7:
                message = await bot.send_message(
                    chat_id,
                    f"⚠️ *Внимание!* Хэшрейт сети *{name}* упал на {((last_hashrate - hashrate) / last_hashrate * 100):.2f}%!\n"
                    f"Текущий: `{format_hashrate(hashrate)}` | Предыдущий: `{format_hashrate(last_hashrate)}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=build_mode_keyboard()
                )
                asyncio.create_task(delete_message_later(chat_id, message.message_id))
        last_hashrates.update(hashrates)
        report = f"📊 *Хэшрейт всех сетей:*\n" + "\n".join(report_lines)
        if chat_id in last_hashrate_reports and last_hashrate_reports[chat_id] == report:
            return
        last_hashrate_reports[chat_id] = report
        if chat_id in last_message_ids:
            try:
                await bot.edit_message_text(
                    report,
                    chat_id=chat_id,
                    message_id=last_message_ids[chat_id],
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=build_mode_keyboard()
                )
            except Exception as e:
                if "message is not modified" not in str(e):
                    message = await bot.send_message(
                        chat_id,
                        report,
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=build_mode_keyboard()
                    )
                    last_message_ids[chat_id] = message.message_id
        else:
            message = await bot.send_message(
                chat_id,
                report,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=build_mode_keyboard()
            )
            last_message_ids[chat_id] = message.message_id

async def send_summary_report(chat_id: int):
    await clear_previous_summary(chat_id)
    current_mode = get_current_mode()
    pool_id = modes.get(current_mode, {"pool_id": f"{current_mode}-sha256-1"})["pool_id"]
    real_workers = {
        worker_name: stats for worker_name, stats in worker_stats.items()
        if not worker_name.startswith("0HNCEBF7") and stats["hashrate"] > 0 and stats["pool_id"] == pool_id
    }
    coin = modes.get(current_mode, {"coin": "Unknown"})["coin"]
    algorithm = modes.get(current_mode, {"algorithm": "Unknown"})["algorithm"]
    total_hashrate = sum(stats["hashrate"] for stats in real_workers.values()) if real_workers else 0
    worker_count = len(real_workers)
    blocks_today, blocks_per_hour = calculate_block_stats(pool_id)
    last_block_time = format_timestamp(block_timestamps[pool_id][-1], chat_id) if pool_id in block_timestamps and block_timestamps[pool_id] else "Блоков не найдено"
    report = (
        f"📊 *Сводная статистика:*\n"
        f"Общий хэшрейт: `{format_hashrate(total_hashrate)}`\n"
        f"Подключено машин: `{worker_count}`\n"
        f"Копаем: `{coin}, алгоритм {algorithm}`\n"
        f"Аптайм: `{format_uptime(chat_id, get_last_mode_change_time())}`\n"
        f"Блоков за сутки: `{blocks_today}`\n"
        f"Блоков в час: `{blocks_per_hour:.2f}`\n"
        f"Время последнего блока: `{last_block_time}`"
    )
    try:
        message = await bot.send_message(
            chat_id,
            report,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_mode_keyboard()
        )
        last_summary_message_ids[chat_id] = [message.message_id]
        last_summary_reports[chat_id] = report
    except Exception as e:
        logger.error(f"Ошибка при отправке сводного отчета: {e}")

async def send_detailed_stats_report(chat_id: int):
    await clear_previous_detailed_stats(chat_id)
    report_lines = []
    for mode, info in modes.items():
        pool_id = info.get("pool_id", f"{mode}-sha256-1")
        coin = info["coin"]
        blocks_today, blocks_per_hour = calculate_block_stats(pool_id)
        last_block_time = format_timestamp(block_timestamps[pool_id][-1], chat_id) if pool_id in block_timestamps and block_timestamps[pool_id] else "Блоков не найдено"
        report_lines.append(
            f"*{coin}*:\n"
            f"  Блоков за сутки: `{blocks_today}`\n"
            f"  Блоков в час: `{blocks_per_hour:.2f}`\n"
            f"  Последний блок: `{last_block_time}`"
        )
    report = f"📉 *Детализированная статистика блоков:*\n" + "\n".join(report_lines)
    if chat_id in last_detailed_stats_reports and last_detailed_stats_reports[chat_id] == report:
        return
    last_detailed_stats_reports[chat_id] = report
    try:
        message = await bot.send_message(
            chat_id,
            report,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_mode_keyboard()
        )
        last_detailed_stats_message_ids[chat_id] = [message.message_id]
    except Exception as e:
        logger.error(f"Ошибка при отправке детализированной статистики: {e}")

async def send_worker_stats_report(chat_id: int):
    await clear_previous_worker_stats(chat_id)
    current_mode = get_current_mode()
    pool_id = modes.get(current_mode, {"pool_id": f"{current_mode}-sha256-1"})["pool_id"]
    real_workers = {}
    for worker_name, stats in worker_stats.items():
        if (not worker_name.startswith("0HNCEBF7") and
            stats["hashrate"] > 0 and
            stats["hashrate"] <= 500_000_000_000_000 and  # Максимум 500 TH/s
            stats["pool_id"] == pool_id):
            short_name = get_worker_short_name(worker_name)
            if short_name not in real_workers or stats["last_seen"] > real_workers[short_name]["last_seen"]:
                real_workers[short_name] = stats
                logger.info(f"Добавлен воркер {short_name} с хэшрейтом {format_hashrate(stats['hashrate'])}")
    if not real_workers:
        report = f"📈 *Статистика воркеров ({pool_id}):*\nНет активных воркеров."
        message = await bot.send_message(
            chat_id,
            report,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_mode_keyboard()
        )
        last_worker_stats_message_ids[chat_id] = [message.message_id]
        last_worker_stats_reports[chat_id] = report
        return
    report_lines = []
    current_time = datetime.now(timezone.utc)
    for worker_name, stats in sorted(real_workers.items()):
        hashrate = stats["hashrate"]
        last_seen = stats["last_seen"]
        shares = stats["shares"]
        time_diff = (current_time - last_seen).total_seconds()
        status = "✅ Активен" if time_diff < 600 else "⚠️ Неактивен"
        worker_report = (
            f"*{worker_name}* `{status} {format_timestamp(last_seen, chat_id)}`:\n"
            f"  Хэшрейт: `{format_hashrate(hashrate)}`, Шары приняты: `{shares}`"
        )
        report_lines.append(worker_report)
    max_message_length = 4096
    messages = []
    current_lines = []
    current_length = len(f"📈 *Статистика воркеров ({pool_id}):*\n")
    part_number = 1
    for line in report_lines:
        line_length = len(line)
        if current_length + line_length + len("\n") > max_message_length - 10:
            header = f"📈 *Статистика воркеров ({pool_id}, часть {part_number}):*\n"
            messages.append(header + "\n".join(current_lines))
            current_lines = [line]
            current_length = len(f"📈 *Статистика воркеров ({pool_id}, часть {part_number + 1}):*\n") + line_length
            part_number += 1
        else:
            current_lines.append(line)
            current_length += line_length + len("\n")
    if current_lines:
        header = f"📈 *Статистика воркеров ({pool_id}, часть {part_number}):*\n" if part_number > 1 else f"📈 *Статистика воркеров ({pool_id}):*\n"
        messages.append(header + "\n".join(current_lines))
    full_report = "\n".join(messages)
    new_message_ids = []
    for i, message_text in enumerate(messages):
        message = await bot.send_message(
            chat_id,
            message_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=build_mode_keyboard() if i == len(messages) - 1 else None
        )
        new_message_ids.append(message.message_id)
    last_worker_stats_message_ids[chat_id] = new_message_ids
    last_worker_stats_reports[chat_id] = full_report
    logger.info(f"Отправлена статистика воркеров для пула {pool_id}: {len(real_workers)} воркеров")

async def monitor_workers():
    while True:
        current_time = datetime.now(timezone.utc)
        current_mode = get_current_mode()
        current_pool_id = modes.get(current_mode, {"pool_id": f"{current_mode}-sha256-1"})["pool_id"]
        workers_to_remove = []
        for worker_name, stats in list(worker_stats.items()):
            last_seen = stats["last_seen"]
            hashrate = stats["hashrate"]
            pool_id = stats.get("pool_id", "unknown")
            if pool_id != current_pool_id:
                workers_to_remove.append(worker_name)
                logger.info(f"Удален воркер {worker_name} из-за несовпадения пула: {pool_id} != {current_pool_id}")
                continue
            if (current_time - last_seen).total_seconds() > 600:
                workers_to_remove.append(worker_name)
                if not worker_name.startswith("0HNCEBF7"):
                    short_name = get_worker_short_name(worker_name)
                    for chat_id in authorized_chats:
                        message = await bot.send_message(
                            chat_id,
                            f"⚠️ *Майнер отключился!*\n"
                            f"ID: `{short_name}`\n"
                            f"Последний хэшрейт: `{format_hashrate(hashrate)}`\n"
                            f"Последнее количество шар: `{stats['shares']}`\n"
                            f"Время: `{format_timestamp(current_time, chat_id)}`",
                            parse_mode=ParseMode.MARKDOWN,
                            reply_markup=build_mode_keyboard()
                        )
                        asyncio.create_task(delete_message_later(chat_id, message.message_id))
                continue
            if hashrate > 500_000_000_000_000:  # Максимум 500 TH/s
                workers_to_remove.append(worker_name)
                logger.warning(f"Воркер {worker_name} удален из-за нереалистичного хэшрейта: {hashrate}")
                continue
        for worker_name in workers_to_remove:
            if worker_name in worker_stats:
                del worker_stats[worker_name]
        unique_workers = {}
        for worker_name, stats in list(worker_stats.items()):
            short_name = get_worker_short_name(worker_name)
            if short_name not in unique_workers or stats["last_seen"] > unique_workers[short_name]["last_seen"]:
                unique_workers[short_name] = (worker_name, stats)
                if short_name in unique_workers and unique_workers[short_name][0] != worker_name:
                    logger.info(f"Удален дубликат воркера {unique_workers[short_name][0]} в пользу {worker_name}")
                    del worker_stats[unique_workers[short_name][0]]
        worker_stats.clear()
        for worker_name, stats in unique_workers.values():
            worker_stats[worker_name] = stats
        await asyncio.sleep(60)

async def start_log_monitoring():
    from .log_parser import LogParser
    from watchdog.observers import Observer
    loop = asyncio.get_running_loop()  # <-- Add this line
    event_handler = LogParser(loop)    # <-- Pass loop here
    observer = Observer()
    observer.schedule(event_handler, path=CONFIG["log_file_path"], recursive=False)
    observer.start()
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        observer.stop()
        raise
    finally:
        observer.join()

async def shutdown():
    logger.info("Остановка бота...")
    tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    try:
        await asyncio.gather(*tasks, return_exceptions=True)
    except asyncio.CancelledError:
        pass
    await bot.session.close()
    logger.info("Сессия бота закрыта")
    loop = asyncio.get_running_loop()
    await loop.shutdown_asyncgens()
    logger.info("Асинхронные генераторы завершены")

async def main():
    from .utils import setup_logging
    setup_logging()
    logger.info("Запуск Telegram-бота...")
    bot_task = asyncio.create_task(dp.start_polling(bot))
    log_task = asyncio.create_task(start_log_monitoring())
    worker_task = asyncio.create_task(monitor_workers())
    try:
        await asyncio.gather(bot_task, log_task, worker_task)
    except asyncio.CancelledError:
        await shutdown()
        raise

if __name__ == "__main__":
    asyncio.run(main())