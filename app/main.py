import asyncio
import time
import re
from datetime import datetime
from datetime import timedelta
from database import engine_db
from database import StoppedTickets, ExpiresTickets
from envparse import Env
from log import logger
from typing import Coroutine, Awaitable
from ws_server import ServerServices
from sqlalchemy import select, update, insert


env = Env()
env.read_envfile('.env')

port = env("PORT")
interval = env.int("INTERVAL")
stopped_filter = env.str("FILTER_STOPPED")
arrears_filter = env.str("FILTER_ARREARS")


class Analytics:
    """
    Класс для анализа тикетов из системы NTTM (просроченные, приостановленные):
    1. Класс обращается к методам класса ServerServices для создания заданий
    2. Получая информацию по тикету, вызывается нужный метод класс
    3. После анализа тикета результат проверки добавляется в БД
    """

    def __init__(self, stopped: str, arrears: str) -> None:
        self._arrears_tickets = []
        self._stopped_tickets = []
        self._stopped_filter = stopped
        self._arrears_filter = arrears
        self._database = engine_db
        
    @staticmethod
    def analise(ticket: dict) -> str:
        def expires(task: dict, counter_sla: int, sla: int) -> int | str:
            group = 'SLA не превышен'
            time_create = datetime.strptime(task['createTs'][0:19], format_date)
            time_close = datetime.strptime(task['completionDate'][0:19], format_date)

            time_work_on_request = (time_close - time_create).total_seconds() / 60
            counting_sla = counter_sla + time_work_on_request

            if counting_sla >= sla:
                if not task.get('assignmentDate'):
                    time_assign = time_create
                else:
                    time_assign = datetime.strptime(task['assignmentDate'][0:19], format_date)

                group = task['taskExecutorDTO']['execUnitName']

                if task.get('taskComments') and len(task['taskComments'][-1]['comment']) > 0:
                    end_comment = task['taskComments'][-1]['comment']
                    parasitic_data = ("<p>", "</p>", "&nbsp;", "<br>", "<strong>",
                                      "</strong>", "&gt;", "&lt;", "'")

                    for old in parasitic_data:
                        end_comment = end_comment.replace(old, ' ')
                else:
                    end_comment = "Комментарий отсутствует"

                analise_info.update({'Результат': f"SLA превышен",
                                     'Просрочено на группе': group,
                                     'Номер запроса': task['taskNumber'],
                                     'Время создания запроса': time_create.strftime(format_date),
                                     'Время принятия в работу': time_assign.strftime(format_date),
                                     'Время закрытия запроса': time_close.strftime(format_date),
                                     'Время реакции': time_assign - time_create,
                                     'Время решения': time_close - time_assign,
                                     'Время всё': time_close - time_create,
                                     'Последний комментарий (task)': end_comment})

                if group == 'Вендор (ДЭФИР)' and task.get('foreignTicketId'):
                    group = f"{task['providerName']}"
                elif group == 'Провайдер' and task.get('foreignTicketId'):
                    group = f"Провайдер ({task['providerName']})"

            return counting_sla, group

        if ticket.get('closeDate'):
            close_date = str(ticket['closeDate']).split("T")[0]
        else:
            close_date = 'Не удалось определить'

        analise_info = {}
        format_date = "%Y-%m-%dT%H:%M:%S"
        ticket_sla = int(ticket['ola']['ksSla'])
        count_sla = 0

        if ticket['status'] == 'В работе':
            if ticket['tasks'][-1]['typeName'] == 'Ожидание':
                analise_info['Результат'] = 'ТТ в приостановке'
            else:
                analise_info['Результат'] = 'ТТ в работе'

        elif ticket['status'] == 'Закрыт':
            for ticket_task in ticket['tasks']:
                if ticket_task['typeName'] not in ('Ожидание', 'Запрос клиента'):
                    count_sla, expire_group = expires(ticket_task, count_sla, ticket_sla)
                    if expire_group:
                        break

                if ticket_task['typeName'] == 'Ожидание':
                    execution = ticket_task['taskExecutorDTO']['execUnitName']
                    if execution in ('Решение сетевого ТТ', 'Решение базового ТТ'):
                        count_sla, expire_group = expires(ticket_task, count_sla, ticket_sla)
                        if expire_group:
                            break
            else:
                analise_info['Результат'] = 'SLA не превышен'
        else:
            logger.info(f"В анализе найден неизвестный статус ТТ {ticket['id']} {ticket['status']}")

        text = '\n'.join(map(lambda x: f"{x[0]}: {x[1]}", analise_info.items()))
        return text, expire_group, close_date

    def stopped_report(self, stopped_tickets: list) -> list[dict]:
        def time_format(date: datetime) -> str:
            return str(datetime.strptime(date[0:19], "%Y-%m-%dT%H:%M:%S"))

        try:
            result = []
            for ticket in stopped_tickets:
                logger.warning(f"Проверяю TT {ticket['id']}")
                ticket_sla = time_format(ticket['ola']['kdSLA'])
                ticket_dump = ticket['tasks']

                for task in reversed(ticket_dump):
                    if task['typeName'] == 'Ожидание':
                        index = ticket_dump.index(task)

                        author = ticket_dump[index - 1]['taskExecutorDTO']['executorName']
                        subdivision_requirement = ticket_dump[index - 2]['targetUnitName']
                        comment = re.sub(r'\<[^>]*\>', '', ticket_dump[index - 1]['closeComment'])

                        ticket_info = {
                            "Номер запроса": task['taskNumber'],
                            "Дата согласования приостановки": time_format(ticket_dump[index - 1]['createTs']),
                            "Дата начала приостановки": time_format(task['createTs']),
                            "Дата конца приостановки": time_format(task['suspendDate']),
                            "Кто приостановил": author,
                            "Последний коммент": comment,
                            "Кто запросил приостановку": subdivision_requirement,
                            "SLA (до которого)": ticket_sla
                        }
                        result.append(ticket_info)
                        break

            with self._database.connect() as session:
                request = select(StoppedTickets.task_number)
                tickets_task = session.execute(request)
                session.commit()
                
            tickets_id = [task[0] for task in tickets_task]

            for ticket_data in result:
                data = list(ticket_data.values())
                ticket_id_num = data[0]
                task_id = str(data[0]).split("-")[0]

                if ticket_id_num in tickets_id:
                    with self._database.connect() as session:
                        request = update(StoppedTickets).where(StoppedTickets.task_number == task_id).values((*data,))
                        session.execute(request)
                        session.commit()

                    logger.warning(f"Обновлён ТТ {ticket_id_num}")
                else:
                    with self._database.connect() as session:
                        request = insert(StoppedTickets).values((*data,))
                        session.execute(request)
                        session.commit()

                    logger.warning(f"Добавлен ТТ {ticket_id_num}")
            return result

        except Exception as err:
            logger.error(f"Ошибка в отчёте приостановок: {err}", exc_info=True)

    def arrears_report(self, arrears_tickets: list) -> list[dict]:
        def time_formats(ticket_data: dict) -> datetime:
            formate = '%Y-%m-%d'
            now = datetime.now()

            date_y = datetime.strptime((now - timedelta(days=1)).strftime(formate), formate)
            date_dby = datetime.strptime((now - timedelta(days=2)).strftime(formate), formate)

            time_str = str(ticket_data['tasks'][-1]['completionDate']).split('T')[0]
            date_close = datetime.strptime(time_str, formate)
            return date_y, date_dby, date_close

        try:
            result = []
            for ticket in arrears_tickets:
                ticket_number = ticket['id']
                logger.warning(f"Проверяю TT {ticket_number}")

                yesterday, db_yesterday, close = time_formats(ticket)

                if yesterday >= close > db_yesterday:
                    text, group, close_date = self.analise(ticket)
    
                    with self._database.connect() as session:
                        request = insert(ExpiresTickets).values((ticket_number, group, text, close_date))
                        session.execute(request)
                        session.commit()

                    result.append(
                        {
                        "ticket": ticket,
                        "resp": group,
                        "comment": text,
                        "date": close_date
                        }
                    )
                else:
                    result.append({"ticket": ticket, "comment": "eliminated"})
            return result

        except Exception as err:
            logger.error(f"Ошибка в отчёте просрочек: {err}", exc_info=True)

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
    analyst = Analytics(stopped_filter, arrears_filter)
    service = ServerServices(port)

    successfully = False
    date_event = datetime.now() - timedelta(seconds=1)
    
    while True:
        try:
            now = datetime.now()
            
            if now.hour < 3 and not successfully:
                if service.nttm.check_client():
                    tickets = await analyst.get_dashboard(service, arrears_filter)
                    if tickets:
                        result = await analyst.task_creator(service, tickets, arrears_filter)
                        expires = analyst.arrears_report(result)
                        if expires and len(tickets) == len(expires):
                            successfully = True
            if now.hour > 3:
                successfully = False

            if now > date_event:
                if service.nttm.check_client():
                    tickets = await analyst.get_dashboard(service, stopped_filter)
                    if tickets:
                        result = await analyst.task_creator(service, tickets, stopped_filter)
                        analyst.stopped_report(result)
                        date_event = now + timedelta(seconds=interval)

        except Exception as error:
            logger.error(f'Ошибка в core: {error}', exc_info=True)
        await asyncio.sleep(1)


if __name__ == '__main__':
    asyncio.run(core())
