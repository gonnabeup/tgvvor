import asyncio
import logging
import signal
from src.stratum_proxy.proxy import main as proxy_main
from src.telegram_bot.bot import main as bot_main

async def shutdown(proxy_task, bot_task):
    logging.info("Остановка всех компонентов...")
    # Отменяем задачи
    proxy_task.cancel()
    bot_task.cancel()
    try:
        await asyncio.gather(proxy_task, bot_task, return_exceptions=True)
    except asyncio.CancelledError:
        logging.info("Задачи proxy и bot отменены")
    # Завершаем асинхронные генераторы
    loop = asyncio.get_running_loop()
    await loop.shutdown_asyncgens()
    logging.info("Асинхронные генераторы завершены")

async def main():
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/main.log'),
            logging.StreamHandler()
        ]
    )
    logging.info("Запуск MiningCore: Stratum-прокси и Telegram-бот")

    # Запускаем прокси и бота как задачи
    proxy_task = asyncio.create_task(proxy_main())
    bot_task = asyncio.create_task(bot_main())

    # Настройка обработки сигналов
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(proxy_task, bot_task)))

    # Ждём завершения задач
    try:
        await asyncio.gather(proxy_task, bot_task)
    except asyncio.CancelledError:
        pass

if __name__ == '__main__':
    asyncio.run(main())
