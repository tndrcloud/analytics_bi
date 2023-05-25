import asyncio
from datetime import datetime
from datetime import timedelta
from envparse import Env
from log import logger
from typing import Awaitable
from ws_server import ServerServices
from analytics import Analytics


env = Env()
env.read_envfile('.env')

port = env("PORT")
interval = env.int("INTERVAL")
stopped_filter = env.str("FILTER_STOPPED")
arrears_filter = env.str("FILTER_ARREARS")


class TaskManager:
    """
    Класс для менеджмента клиент-серверных задач (получение дашборда/тикета):
    1. Класс обращается к методам класса ServerServices для создания заданий
    2. Класс ServerServices создаёт задания для подключенных клиентов и отправляет их
    3. Получая в ответе информацию по тикету, вызывается нужный метод из класса Analytics
    """

    def __init__(self, stopped: str, arrears: str) -> None:
        self._arrears_tickets = []
        self._stopped_tickets = []
        self._stopped_filter = stopped
        self._arrears_filter = arrears

    async def get_dashboard(self, services: ServerServices, key_filter: str) -> list[int]:
        incidents = []
        logger.warning(f"Запрос дашборда по фильтру")
        response = await services.nttm.get_tasks(key_filter)

        if key_filter == self._stopped_filter:
            identify = "ticketId"
            self._stopped_tickets.clear()
        else:
            identify = "id"
            self._arrears_tickets.clear()

        if response['status_code'] == 200:
            result = response['result']
            for ticket in result:
                incidents.append(ticket[identify])
            return incidents
        else:
            logger.error(f'Не удалось получить дашборд: {response}', exc_info=True)

    async def get_ticket(self, services: ServerServices, ticket: int, key: str) -> dict[str, dict]:
        logger.warning(f"Запрос данных по TT {ticket}")
        response = await services.nttm.get_inc(ticket)

        if response['status_code'] == 200:
            result = response['result']
            if key == self._stopped_filter:
                self._stopped_tickets.append(result)
                return result
            else:
                self._arrears_tickets.append(result)
                return result

    async def task_creator(self, service: ServerServices, tickets: list, key: str) -> list[dict]:
        tasks = []
        for ticket in tickets:
            task = asyncio.create_task(self.get_ticket(service, ticket, key))
            tasks.append(task)
        await asyncio.gather(*tasks)

        if key == self._stopped_filter:
            if self._stopped_tickets:
                return self._stopped_tickets
            logger.error(f"Ошибка с приостановками", exc_info=True)
        else:
            if self._arrears_tickets:
                return self._arrears_tickets
            logger.error(f"Ошибка с просрочками", exc_info=True)


async def core() -> Awaitable:
    manager = TaskManager(stopped_filter, arrears_filter)
    service = ServerServices(port)
    analyst = Analytics()

    successfully = False
    date_event = datetime.now() - timedelta(seconds=1)
    
    while True:
        try:
            now = datetime.now()
            
            if now.hour < 3 and not successfully:
                if service.nttm.check_client():
                    tickets = await manager.get_dashboard(service, arrears_filter)
                    if tickets:
                        result = await manager.task_creator(service, tickets, arrears_filter)
                        expires = analyst.arrears_report(result)
                        if expires and len(tickets) == len(expires):
                            successfully = True
            if now.hour > 3:
                successfully = False

            if now > date_event:
                if service.nttm.check_client():
                    tickets = await manager.get_dashboard(service, stopped_filter)
                    if tickets:
                        result = await manager.task_creator(service, tickets, stopped_filter)
                        analyst.stopped_report(result)
                        date_event = now + timedelta(seconds=interval)

        except Exception as error:
            logger.error(f'Ошибка в core: {error}', exc_info=True)
        await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(core())
