import asyncio
import aiohttp
import fake_useragent
import websockets
import hashlib
import json
import logging
from typing import Coroutine, Awaitable
from datetime import datetime
from datetime import timedelta
from log import logger
from envparse import Env


env = Env()
env.read_envfile('.env')

email = env.str("EMAIL")
token = env.str("TOKEN")
url = env.str("URL")
key = env.str("KEY")
server = env.str("SERVER")
password = env.str("PASSWORD")


class ConnectorNTTM:
    """
    Класс для работы клиента с системой NTTM и взаимодействия с сервером:
    1. Клиент использует УЗ пользователя NTTM
    2. Клиент создаёт и обновляет сессию в пределах которой совершает запросы
    3. Получая задание от сервера, клиент помещает его в очередь и создаёт запрос в систему
    4. Получая ответ от системы, клиент помещает результат в очередь на отправку клиенту
    """

    def __init__(self, loop: asyncio.get_event_loop) -> None:
        self._email = email
        self._password = password
        self._url = url
        self._user_agent = fake_useragent.UserAgent().random
        self.tasks = asyncio.Queue()
        self.results = asyncio.Queue()
        self._timer = 0
        self._active_session = 0
        self._session = []
        self._loop = loop

        loop.create_task(self._core())

    async def _create_session(self) -> Coroutine:
        while True:
            session = aiohttp.ClientSession()
            payload = json.dumps(dict(username=self._email, password=self._password, force=True))
            headers = {
                'Accept': 'application/json, text/plain, */*',
                'User-Agent': self._user_agent,
                'Content-Type': 'application/json'
            }
            method = "/nttm-task-handler/api/authenticate"
            response = await session.post(self._url + method, data=payload, headers=headers)

            if response.status == 200:
                headers = {
                    'User-Agent': self._user_agent,
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer ' + (await response.json())['id_token']
                }
                self._session = [session, headers]
                break
            else:
                logger.error(await response.text())
                await asyncio.sleep(5)

    async def _get_session(self) -> list[aiohttp.ClientSession, dict]:
        if self._active_session == 0:
            self._active_session += 1
            await self._create_session()
            self._timer = datetime.now() + timedelta(hours=6)

        elif datetime.now() > self._timer:
            await self._logout()
            await self._create_session()
            self._timer = datetime.now() + timedelta(hours=6)
        return self._session

    async def _logout(self) -> Coroutine:
        session, headers = self._session
        try:
            await session.get(self._url + "/nttm-task-handler/api/logout", headers=headers, timeout=10)
        except Exception as err:
            logger.error(f"Не удалось выйти из NTTM: {err}")

        await session.close()
        self._session.clear()

    async def _close_session(self, code: int) -> Coroutine:
        if code != 200 and self._active_session == 1:
            if self._session:
                self._active_session -= 1
                await self._session[0].close()
                await self._logout()

    async def _draft(self, method: str, url: str, timeout=10, params=None, data=None, json_=None) -> Coroutine:
        code, result = None, None
        request_data = {'method': method, 'url': url, 'timeout': timeout,
                        'params': params, 'data': data, 'json': json_}

        for _ in range(3):
            try:
                session, headers = await self._get_session()
                response = await session.request(**request_data, headers=headers)
                code = response.status

                if code == 200:
                    try:
                        result = await response.json()
                    except json.JSONDecodeError as err:
                        logger.warning(err)
                        result = await response.text()
                    await self._close_session(code)
                    break

                elif code == 400:
                    result = await response.text()
                    await self._close_session(code)
                    break

                else:
                    result = await response.text()
                    await self._close_session(code)
                    logger.error(result)
                    await asyncio.sleep(1)

            except Exception as err:
                code, result = 400, err
                logger.error(err, exc_info=True)
                await self._close_session(code)
                await asyncio.sleep(1)

        return code, result

    async def _get_tasks(self, task_id: int, filter_key: str) -> Coroutine:
        def modify_filter(data: str) -> str:
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            db_yesterday = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')

            filter_json = data[:-1]
            filter_field = filter_json + ',{"field":"status","searchOperation":"IN","values":[0]}]'
            modify_date = str(filter_field).replace('2023-01-24', f'{db_yesterday}')
            modify_date = str(modify_date).replace('2023-01-25', f'{yesterday}')
            result_filter = modify_date.encode('utf-8')
            
            return result_filter

        try:
            url_filter = f"{self._url}/nttm-user-profile/api/user-filters/{filter_key}"
            code, result = await self._draft(method='GET', url=url_filter)

            if code == 200:
                if not result:
                    code = 400
                    tasks = 'Custom error: filter is none!'

                else:
                    if not filter_key == "5481e1e0-0ff7-4dec-a183-96ee95a61c29":
                        filter_ = modify_filter(result['result'])
                        size, request = 100, "ticket"
                    else:
                        filter_ = result['filter'].encode('utf-8')
                        size, request = 500, "task"

                    url_tasks = f"{self._url}/nttm-web-gateway/api/{request}/page"
                    params = {"page": "0",
                              "size": f"{size}",
                              "sort": "id,desc"}

                    tasks = []
                    code, result = await self._draft(method='POST', url=url_tasks, timeout=90,
                                                     params=params, data=filter_)
                    if code == 200:
                        tasks.extend(result['content'])
                        if result['totalPages'] > 1:
                            for page in range(1, result['totalPages']):
                                params['page'] = str(int(params['page']) + 1)
                                code, result = await self._draft(method='POST', url=url_tasks, timeout=90,
                                                                 params=params, data=filter_)
                                if code == 200:
                                    tasks.extend(result['content'])
                                else:
                                    tasks = result
                                    break
                    else:
                        tasks = result
            else:
                tasks = result
            self.results.put_nowait({'task_id': task_id, 'status_code': code, 'result': tasks})

        except Exception as err:
            logger.error(err, exc_info=True)
            self.results.put_nowait({'task_id': task_id, 'status_code': 400, 'result': f'fatal error: {err}'})

    async def _get_incident(self, task_id: int, inc: int) -> Coroutine:
        try:
            url = f"{self._url}/nttm-web-gateway/api/ticket/{inc}"
            code, result = await self._draft('GET', url)
            self.results.put_nowait({'task_id': task_id, 'status_code': code, 'result': result})

        except Exception as err:
            logger.error(err, exc_info=True)
            self.results.put_nowait({'task_id': task_id, 'status_code': 400, 'result': f'fatal error: {err}'})

    async def _core(self) -> Awaitable:
        task = {'task_id': None}

        while True:
            try:
                task = self.tasks.get_nowait()

                if task.get('type') == 'get_tasks':
                    self._loop.create_task(self._get_tasks(task['task_id'], task['filter']))
                elif task.get('type') == 'get_inc':
                    self._loop.create_task(self._get_incident(task['task_id'], task['inc']))
                else:
                    result = {'type': 'event', 'message': f'task type ({task.get("type")}) not found',
                              'task_id': task['task_id'], 'status_code': None}
                    self.results.put_nowait(result)

            except asyncio.QueueEmpty:
                await asyncio.sleep(0.01)
            except Exception as err:
                logging.error(err, exc_info=True)
                self.results.put_nowait({'type': 'event', 'message': err, 'task_id': task['task_id']})


async def main() -> Awaitable:
    def sha256(data: str) -> hashlib.hash_object:
        hash_object = hashlib.sha256(bytes(token + data + key, encoding='utf-8'))
        hex_dig = hash_object.hexdigest()
        return hex_dig

    async def sender_analyst(websocket: websockets.connect, service: ConnectorNTTM) -> Coroutine:
        while websocket.open:
            try:
                result = json.dumps(service.results.get_nowait())
                await websocket.send(result)
                logger.debug(f"{websocket.remote_address} sending: {str(result)[:50]}")

            except asyncio.QueueEmpty:
                await asyncio.sleep(0.01)

    while True:
        try:
            async with websockets.connect(server) as ws:
                await ws.send(token)
                salt = await ws.recv()
                await ws.send(sha256(salt))
                await ws.send('nttm')

                logger.info('ws client connecting')
                loop = asyncio.get_event_loop()
                nttm = ConnectorNTTM(loop)
                loop.create_task(sender_analyst(ws, nttm))

                async for message in ws:
                    mes = json.loads(message)
                    logger.debug(f"{ws.remote_address} recv: {mes}")
                    nttm.tasks.put_nowait(mes)
                    await asyncio.sleep(0.01)

        except Exception as err:
            logging.error(err)
            await asyncio.sleep(5)


if __name__ == '__main__':
    asyncio.run(main())
