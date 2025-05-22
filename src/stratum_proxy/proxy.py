import asyncio
import json
import logging
import signal
from .config import load_config, get_current_mode
from .utils import setup_logging

logger = logging.getLogger(__name__)
CONFIG = load_config()
active_clients = set()
conport = 3310

async def handle_client(miner_reader, miner_writer, current_mode):
    addr = miner_writer.get_extra_info('peername')
    client_task = asyncio.current_task()
    active_clients.add(client_task)
    logger.info(f"Подключен майнер: {addr}, режим={current_mode}")

    modes = CONFIG.get("modes", {})
    mode_info = modes.get(current_mode)

    if not mode_info:
        logger.warning(f"Режим '{current_mode}' не найден в конфигурации. Закрываю.")
        miner_writer.close()
        await miner_writer.wait_closed()
        active_clients.discard(client_task)
        return
    if mode_info.get("port") is None:
        logger.warning(f"Режим '{current_mode}' не принимает подключения (port is None). Закрываю.")
        miner_writer.close()
        await miner_writer.wait_closed()
        active_clients.discard(client_task)
        return

    host = mode_info.get("host", "127.0.0.1")
    port = mode_info["port"]
    logger.info(f"Режим '{current_mode}' использует {host}:{port}")

    try:
        pool_reader, pool_writer = await asyncio.open_connection(host, port)
        logger.info(f"Подключился к пулу {host}:{port} для {addr}")
    except Exception as e:
        logger.error(f"Не удалось подключиться к пулу {host}:{port} для {addr}: {e}")
        miner_writer.close()
        await miner_writer.wait_closed()
        active_clients.discard(client_task)
        return

    async def forward_to_pool():
        try:
            while not miner_reader.at_eof():
                data = await miner_reader.readline()
                if not data:
                    break
                text = data.decode().strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError as e:
                    logger.warning(f"Неверный JSON от майнера {addr}: {e}")
                    pool_writer.write(data)
                    await pool_writer.drain()
                    continue

                if msg.get("method") == "mining.authorize":
                    params = msg.get("params", [])
                    if params:
                        user = params[0]
                        if "." in user:
                            alias, worker = user.split(".", 1)
                        else:
                            alias, worker = user, ""
                        wallet = mode_info["alias"].get(alias)
                        if wallet:
                            new_user = f"{wallet}.{worker}" if worker else wallet
                            msg["params"][0] = new_user
                            new_data = (json.dumps(msg) + "\n").encode()
                            pool_writer.write(new_data)
                            logger.info(f"Заменен alias '{alias}' на кошелек '{wallet}' (воркер '{worker}')")
                        else:
                            pool_writer.write(data)
                            logger.info(f"Alias '{alias}' не найден в конфиге; отправляем без изменений")
                        await pool_writer.drain()
                        continue
                pool_writer.write(data)
                await pool_writer.drain()
        except Exception as e:
            logger.error(f"Ошибка перенаправления к пулу для {addr}: {e}")
        finally:
            pool_writer.close()
            try:
                await pool_writer.wait_closed()
            except ConnectionResetError:
                logger.warning(f"Pool connection reset by peer for {addr} (safe to ignore)")
            except Exception as e:
                logger.error(f"Error while closing pool_writer for {addr}: {e}")

    async def forward_to_miner():
        try:
            while not pool_reader.at_eof():
                data = await pool_reader.readline()
                if not data:
                    break
                miner_writer.write(data)
                await miner_writer.drain()
        except Exception as e:
            logger.error(f"Ошибка перенаправления к майнеру для {addr}: {e}")
        finally:
            miner_writer.close()
            try:
                await miner_writer.wait_closed()
            except ConnectionResetError:
                logger.warning(f"Miner connection reset by peer for {addr} (safe to ignore)")
            except Exception as e:
                logger.error(f"Error while closing miner_writer for {addr}: {e}")

    try:
        await asyncio.gather(forward_to_pool(), forward_to_miner())
    finally:
        logger.info(f"Соединение закрыто для {addr}")
        active_clients.discard(client_task)

async def manage_server(current_mode, server_task):
    while True:
        try:
            new_mode = get_current_mode()
            if new_mode != current_mode[0]:
                logger.info(f"Режим изменен: {current_mode[0]} -> {new_mode}")
                current_mode[0] = new_mode

                if server_task:
                    logger.info("Закрываем текущий сервер и все клиентские соединения")
                    for client_task in active_clients.copy():
                        client_task.cancel()
                    server_task.cancel()
                    try:
                        await server_task
                    except asyncio.CancelledError:
                        pass
                    server_task = None
                    active_clients.clear()

                if new_mode != "сон":
                    server = await asyncio.start_server(
                        lambda r, w: handle_client(r, w, current_mode[0]), '0.0.0.0', conport
                    )
                    addr = server.sockets[0].getsockname()
                    logger.info(f"Слушаем на {addr} в режиме '{new_mode}'")
                    server_task = asyncio.create_task(server.serve_forever())
                else:
                    logger.info("Режим 'сон' - не принимаем новые подключения")

            await asyncio.sleep(5)
        except asyncio.CancelledError:
            logger.info("Задача manage_server отменена")
            if server_task:
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass
            raise
        except Exception as e:
            logger.error(f"Ошибка в manage_server: {e}")
            await asyncio.sleep(5)

async def shutdown(loop, server_task):
    logger.info("Остановка прокси...")
    tasks = [task for task in asyncio.all_tasks(loop) if task is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    if server_task:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass
    await asyncio.sleep(0.5)
    # Remove these lines:
    # loop.stop()
    # loop.run_until_complete(loop.shutdown_asyncgens())
    # loop.close()
    await loop.shutdown_asyncgens()  # <-- Just await this
    logger.info("Прокси успешно остановлен")

async def main():
    setup_logging()
    current_mode = [get_current_mode()]
    logger.info(f"Запуск Stratum-прокси в режиме '{current_mode[0]}'")

    loop = asyncio.get_running_loop()
    server_task = None

    if current_mode[0] != "сон":
        server = await asyncio.start_server(
            lambda r, w: handle_client(r, w, current_mode[0]), '0.0.0.0', conport
        )
        addr = server.sockets[0].getsockname()
        logger.info(f"Слушаем на {addr} в режиме '{current_mode[0]}'")
        server_task = asyncio.create_task(server.serve_forever())

    def handle_shutdown():
        asyncio.create_task(shutdown(loop, server_task))

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown)

    try:
        await manage_server(current_mode, server_task)
    except asyncio.CancelledError:
        logger.info("Основные задачи отменены")
    finally:
        await shutdown(loop, server_task)

if __name__ == "__main__":
    asyncio.run(main())