import asyncio
import re
import os
from datetime import datetime, timezone, timedelta
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from aiogram import Bot
from aiogram.enums import ParseMode
from .config import CONFIG, get_current_mode, modes
from .utils import format_hashrate, format_timestamp, get_worker_short_name

logger = logging.getLogger(__name__)
LOG_FILE_PATH = "/home/simple1/bot/mcpool.log"

class LogParser(FileSystemEventHandler):
    def __init__(self, loop):
        self.last_position = 0
        self.active_workers = set()
        self.loop = loop
        # logger.info(f"LogParser initialized with LOG_FILE_PATH: {LOG_FILE_PATH}")

    def on_modified(self, event):
        # logger.info(f"Watchdog event triggered: {event.src_path}, event_type: {event.event_type}")
        if event.src_path != LOG_FILE_PATH:
            # logger.info(f"Ignoring event for {event.src_path}, expected {LOG_FILE_PATH}")
            return
        asyncio.run_coroutine_threadsafe(self.parse_log(), self.loop)

    async def parse_log(self):
        from .bot import bot, authorized_chats, build_mode_keyboard, delete_message_later, worker_stats, worker_id_to_name
        if not os.path.exists(LOG_FILE_PATH):
            logger.error(f"Log file {LOG_FILE_PATH} does not exist.")
            return
        try:
            file_stat = os.stat(LOG_FILE_PATH)
            mtime = datetime.fromtimestamp(file_stat.st_mtime, tz=timezone.utc)
            # logger.info(f"Parsing log file {LOG_FILE_PATH} from position {self.last_position}, last modified: {mtime}")
            current_mode = get_current_mode()
            current_pool_id = modes.get(current_mode, {"pool_id": f"{current_mode}-sha256-1"})["pool_id"]
            # logger.info(f"Current mode: {current_mode}, pool_id: {current_pool_id}")
            with open(LOG_FILE_PATH, "r", encoding="utf-8") as f:
                f.seek(self.last_position)
                lines = f.readlines()
                # logger.info(f"Read {len(lines)} new lines")
                self.last_position = f.tell()
                if not lines:
                    # logger.info("No new lines to parse")
                    return
                for line in lines:
                    # logger.debug(f"Processing line: {line.strip()}")
                    if f"[{current_pool_id}]" not in line:
                        # logger.info(f"Skipping line due to pool_id mismatch: {line.strip()}")
                        continue
                    if "[StatsRecorder]" in line and not re.search(r"Worker \S+: [\d.]+ [TPG]H/s", line):
                        # logger.warning(f"StatsRecorder line not matched by hashrate regex: {line.strip()}")
                        pass
                    worker_connect = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{1,6})\] \[I\] \[(\S+?)\] \[([A-Z0-9]+)\] Authorized worker (\S+)", line)
                    if worker_connect:
                        timestamp, pool_id, worker_id, worker_name = worker_connect.groups()
                        if pool_id != current_pool_id:
                            # logger.info(f"Skipping worker_connect due to pool_id mismatch: pool_id={pool_id}, expected={current_pool_id}")
                            continue
                        if worker_id.startswith("0HNCEBF7"):
                            # logger.info(f"Skipping worker_connect: worker_id={worker_id} starts with 0HNCEBF7")
                            continue
                        worker_id_to_name[worker_id] = worker_name
                        # logger.info(f"Mapped worker_id {worker_id} to worker_name {worker_name}")
                        self.active_workers.add(worker_name)
                        short_name = get_worker_short_name(worker_name)
                        if worker_name not in worker_stats or (worker_stats[worker_name]["last_seen"] < datetime.now(timezone.utc) - timedelta(seconds=600)):
                            worker_stats[worker_name] = {
                                "hashrate": 0,
                                "last_seen": datetime.now(timezone.utc),
                                "shares": 0,
                                "pool_id": pool_id
                            }
                            # logger.info(f"Worker connected: {short_name}, pool: {pool_id}")
                            for chat_id in authorized_chats:
                                message = await bot.send_message(
                                    chat_id,
                                    f"✅ *Майнер подключился!*\n"
                                    f"ID: `{short_name}`\n"
                                    f"Хэшрейт: `{format_hashrate(worker_stats[worker_name]['hashrate'])}`\n"
                                    f"Шары приняты: `{worker_stats[worker_name]['shares']}`\n"
                                    f"Время: `{format_timestamp(datetime.now(timezone.utc), chat_id)}`",
                                    parse_mode=ParseMode.MARKDOWN,
                                    reply_markup=build_mode_keyboard()
                                )
                                asyncio.create_task(delete_message_later(chat_id, message.message_id))
                        continue
                    worker_stats_match = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{1,6})\] \[I\] \[StatsRecorder\] \[(\S+?)\] Worker (\S+): ([\d.]+) ([TPG])H/s, ([\d.]+) shares/sec", line)
                    if worker_stats_match:
                        timestamp, pool_id, worker_name, hashrate, unit, shares = worker_stats_match.groups()
                        if pool_id != current_pool_id:
                            # logger.info(f"Skipping worker_stats due to pool_id mismatch: pool_id={pool_id}, expected={current_pool_id}")
                            continue
                        if worker_name.startswith("0HNCEBF7"):
                            # logger.info(f"Skipping worker_stats: worker_name={worker_name} starts with 0HNCEBF7")
                            continue
                        hashrate = float(hashrate) * {"T": 1e12, "P": 1e15, "G": 1e9}.get(unit, 1)
                        if hashrate > 500_000_000_000_000:
                            # logger.warning(f"Unrealistic hashrate {hashrate} for worker {worker_name}, ignoring")
                            continue
                        worker_stats[worker_name] = {
                            "hashrate": hashrate,
                            "last_seen": datetime.now(timezone.utc),
                            "shares": worker_stats.get(worker_name, {}).get("shares", 0),
                            "pool_id": pool_id
                        }
                        self.active_workers.add(worker_name)
                        # logger.info(f"Updated worker stats for {worker_name}: hashrate {format_hashrate(hashrate)}, shares {shares}")
                        continue
                    share_accepted = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{1,6})\] \[I\] \[(\S+?)\] \[([A-Z0-9]+)\] Share accepted: D=([\d.]+)", line)
                    if share_accepted:
                        timestamp, pool_id, worker_id, difficulty = share_accepted.groups()
                        if pool_id != current_pool_id:
                            # logger.info(f"Skipping share_accepted due to pool_id mismatch: pool_id={pool_id}, expected={current_pool_id}")
                            continue
                        if worker_id.startswith("0HNCEBF7"):
                            # logger.info(f"Skipping share_accepted: worker_id={worker_id} starts with 0HNCEBF7")
                            continue
                        worker_name = worker_id_to_name.get(worker_id, worker_id)
                        self.active_workers.add(worker_name)
                        shares = worker_stats.get(worker_name, {}).get("shares", 0) + 1
                        worker_stats[worker_name] = {
                            "hashrate": worker_stats.get(worker_name, {}).get("hashrate", 0),
                            "last_seen": datetime.now(timezone.utc),
                            "shares": shares,
                            "pool_id": pool_id
                        }
                        # logger.info(f"Share accepted for worker {worker_name}, total shares: {shares}")
                        continue
                    block_found = re.search(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{1,6})\] \[I\] \[(\S+?)\] Daemon accepted block (\d+) \[([0-9a-f]+)\] submitted by (\S+)", line)
                    if block_found:
                        timestamp_str, pool_id, block_height, block_hash, miner = block_found.groups()
                        if pool_id != current_pool_id:
                            # logger.info(f"Skipping block_found due to pool_id mismatch: pool_id={pool_id}, expected={current_pool_id}")
                            continue
                        try:
                            timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
                        except ValueError as e:
                            logger.error(f"Error parsing block timestamp '{timestamp_str}': {e}")
                            continue
                        if pool_id not in block_timestamps:
                            block_timestamps[pool_id] = []
                        block_timestamps[pool_id].append(timestamp)
                        block_timestamps[pool_id] = [ts for ts in block_timestamps[pool_id] if (datetime.now(timezone.utc) - ts).total_seconds() <= 24 * 3600]
                        for chat_id in authorized_chats:
                            report = f"🎉 *Блок найден!*\n" \
                                     f"Сеть: `{pool_id}`\n" \
                                     f"Высота: `{block_height}`\n" \
                                     f"Хэш: `{block_hash[:8]}...`\n" \
                                     f"Майнер: `{miner}`\n" \
                                     f"Время: `{format_timestamp(timestamp, chat_id)}`"
                            message = await bot.send_message(
                                chat_id,
                                report,
                                parse_mode=ParseMode.MARKDOWN,
                                reply_markup=build_mode_keyboard()
                            )
                            asyncio.create_task(delete_message_later(chat_id, message.message_id))
                        continue
                    # logger.info(f"Line not matched by any pattern: {line.strip()}")
        except Exception as e:
            logger.error(f"Error parsing log: {e}")