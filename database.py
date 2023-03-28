import psycopg2


def sql_request(sql, data_python=()):
    connect = psycopg2.connect(
        dbname='DB_NAME',
        user='DB_USER',
        password='DB_PASSWORD',
        host='DB_HOST',
        port='DB_PORT'
    )
    cursor = connect.cursor()

    if data_python:
        cursor.execute(sql, data_python)
    else:
        cursor.execute(sql)

    if sql[:6] == 'SELECT':
        result = cursor.fetchall()
        connect.close()
        return result

    elif sql[:6] in ('UPDATE', 'DELETE', 'INSERT', 'CREATE'):
        connect.commit()
        connect.close()
        return True


class ExpiresTickets:
    """
    Класс для создания и описания методов для запросов к БД (по просроченным тикетам)
    1. Создаёт таблицу в БД если она еще не создана
    2. Позволяет добавлять и получать информацию по тикету
    """

    sql_request("""CREATE TABLE if not exists nttm_bi.expires_tickets 
                    (ticket_number INTEGER, 
                     responsible TEXT, 
                     comment TEXT, 
                     add_date TEXT)""")

    @staticmethod
    def add_ticket(ticket, responsible, comment, date):
        sql = f"INSERT INTO nttm_bi.expires_tickets VALUES ('{ticket}', '{responsible}', '{comment}', '{date}')"
        return sql_request(sql)

    @staticmethod
    def get_from_day_tickets(date):
        sql = f"SELECT * FROM nttm_bi.expires_tickets WHERE add_date = '{date}'"
        return sql_request(sql)

    @staticmethod
    def get_ticket(ticket):
        sql = f"SELECT * FROM nttm_bi.expires_tickets WHERE ticket_number = '{ticket}'"
        return sql_request(sql)


class StoppedTickets:
    """
    Класс для создания и описания методов для запросов к БД (по приостановленным тикетам)
    1. Создаёт таблицу в БД если она еще не создана
    2. Позволяет добавлять, обновлять, получать и удалять информацию по тикету
    """

    sql_request("""CREATE TABLE if not exists nttm_bi.stopped_tickets 
                    (task_number TEXT PRIMARY KEY, 
                     begin_pause TIMESTAMP WITHOUT TIME ZONE, 
                     end_pause TIMESTAMP WITHOUT TIME ZONE, 
                     who_paused TEXT, 
                     last_comment TEXT, 
                     who_ask_pause TEXT, 
                     sla TIMESTAMP WITHOUT TIME ZONE)""")

    @staticmethod
    def add_ticket(data):
        sql = f"""INSERT INTO nttm_bi.stopped_tickets VALUES {*data,}"""
        return sql_request(sql)

    @staticmethod
    def update_ticket(data):
        sql = f"""UPDATE nttm_bi.stopped_tickets SET 
                    (task_number, begin_pause, end_pause, who_paused, last_comment, who_ask_pause, sla) = {*data,} 
                    WHERE task_number = '{data[0][:6]}'"""
        return sql_request(sql)

    @staticmethod
    def get_all_tickets_id():
        sql = "SELECT task_number FROM nttm_bi.stopped_tickets"
        return sql_request(sql)

    @staticmethod
    def get_ticket(ticket):
        sql = f"SELECT * FROM nttm_bi.stopped_tickets WHERE task_number = '{ticket}'"
        return sql_request(sql)

    @staticmethod
    def delete_ticket(ticket):
        sql = f"""DELETE * FROM nttm_bi.stopped_tickets WHERE task_number = '{ticket}'"""
        return sql_request(sql)
