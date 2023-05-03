import datetime
import random
import hashlib
import threading
import json
import time
import asyncio
import websockets
from typing import Coroutine, Awaitable
from log import logger
from envparse import Env


env = Env()
env.read_envfile('.env')

key = env.str("KEY")
token = env.str("TOKEN")


class ConnectorNTTM:
    """
    Класс для взаимодействия клиента (система NTTM) с сервером:
    1. Сервер проверяет наличие подключенных клиентов
    2. Сервер создаёт задачу, присваивает ей ID и помещает в очередь на отправку клиенту
    3. Клиент получает запрос, обрабатывает его и оправляет результат серверу
    4. Сервер получая ответ от клиента отдаёт результат работы запрашиваемому его методу
    5. Если задача не выполнена за период таймаута, сервер получает соответствующее сообщение
    """

    def __init__(self) -> None:
        self.clients = []
        self._queue_tasks = asyncio.Queue()
        self._complete_tasks = {}
        self._max_id = 100
        self._end_id = 0
        self._lock = threading.RLock()

    async def _send(self) -> Awaitable:
        ws = None
        while True:
            try:
                if self.clients:
                    task = self._queue_tasks.get_nowait()
                    ws = self.clients[0]
                    logger.debug(f"{ws.remote_address} send: {task}")
                    await ws.send(json.dumps(task))
                await asyncio.sleep(0.01)

            except asyncio.QueueEmpty:
                await asyncio.sleep(0.01)
            except Exception as error:
                logger.error(error, exc_info=True)
                await self._disconnect(ws)

    async def _recv(self) -> Awaitable:
        ws = None
        while True:
            try:
                for ws in self.clients:
                    message = await asyncio.wait_for(ws.recv(), timeout=0.01)
                    if message:
                        message = json.loads(message)
                        self._complete_tasks[message.pop('task_id')] = message
                        logger.debug(f"{ws.remote_address} recv: {str(message)[:400]}...")

                await asyncio.sleep(0.01)

            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)
            except Exception as error:
                logger.error(error, exc_info=True)
                await self._disconnect(ws)

    async def _disconnect(self, ws: websockets.connect) -> Coroutine:
        if ws in self.clients:
            if ws.open:
                await ws.close()
            self.clients.remove(ws)
            logger.warning(f"client {ws.service} {ws.remote_address} disconnect")

    def run(self) -> None:
        asyncio.create_task(self._send())
        asyncio.create_task(self._recv())

    def check_client(self) -> bool:
        if len(self.clients) > 0:
            return True
        return False

    async def create_task(self, task: dict) -> dict[str, dict]:
        if len(self.clients) == 0:
            return {'status_code': 501, 'result': 'module not connect'}

        with self._lock:
            if self._end_id < self._max_id:
                task_id = self._end_id + 1
                self._end_id = task_id
            else:
                task_id = 1
                self._end_id = 1

            task.update(task_id=task_id)
            self._queue_tasks.put_nowait(task)

        timeout = 300
        limit_time = timeout + time.time()

        while True:
            with self._lock:
                if task_id in self._complete_tasks:
                    return self._complete_tasks.pop(task_id)

            if limit_time < time.time():
                text = f'Задание ({task}) не выполнено: timeout error'
                logger.error(text)
                return {'status_code': 500, 'result': text}
            await asyncio.sleep(0.1)

    async def get_tasks(self, key_filter: str) -> dict[str, dict]:
        task = {'type': 'get_tasks', 'filter': key_filter}
        completed_task = await self.create_task(task)
        return completed_task

    async def get_inc(self, inc: int) -> dict[str, dict]:
        task = {'type': 'get_inc', 'inc': str(inc)}
        completed_task = await self.create_task(task)
        return completed_task


class ServerServices:
    """
    Класс для создания сервера, аутентификации и подключения его клиент-сервисов:
    1. От сервиса ожидается ТОКЕН
    2. Сервису передается СОЛЬ
    3. От сервиса ожидается хеш (sha256: ТОКЕН + СОЛЬ + КЛЮЧ)
    4. От сервиса ожидается название модуля (такое же, как свойство класса, например, nttm)
    """

    def __init__(self, port: int) -> None:
        self._port = port
        self._TOKEN = token
        self._KEY = key
        self.nttm = ConnectorNTTM()

        threading.Thread(target=lambda: asyncio.run(self.create_server()), daemon=True).start()

    async def create_server(self) -> Awaitable:
        self.nttm.run()
        logger.info("webserver start")
        async with websockets.serve(self._authentication, port=self._port, max_size=10240000):
            await asyncio.Future()

    async def _authentication(self, ws: websockets.connect) -> Coroutine:
        try:
            message = await asyncio.wait_for(ws.recv(), timeout=2)

            if message == self._TOKEN:
                r_number = str(random.randint(1000, 1000000))
                await ws.send(r_number)

                hash_object = hashlib.sha256(bytes(self._TOKEN + r_number + self._KEY, encoding='utf-8'))
                hex_dig = hash_object.hexdigest()
                message = await asyncio.wait_for(ws.recv(), timeout=2)

                if hex_dig == message:
                    service_name = await asyncio.wait_for(ws.recv(), timeout=2)

                    if service_name in self.__dict__:
                        service = self.__getattribute__(service_name)
                        ws.service = service_name
                        logger.info(f"client {ws.service} {ws.remote_address} connect")
                        service.clients.append(ws)
                        await ws.wait_closed()

                        if ws in service.clients:
                            service.clients.remove(ws)
                            logger.warning(f"client {ws.service} {ws.remote_address} disconnect")
                    else:
                        await ws.close(code=4002, reason='Service is not supported')
                else:
                    await ws.close(code=4001, reason='Unauthorized')
            else:
                await ws.close(code=4001, reason='Unauthorized')

        except Exception as err:
            logger.info(f"client {ws.remote_address} not auth, err {err}")
