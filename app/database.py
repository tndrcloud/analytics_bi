from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, DateTime 
from sqlalchemy import create_engine
from datetime import datetime
from envparse import Env


env = Env()
env.read_envfile('.env')

db_path = env.str("DB_PATH")


Base = declarative_base()


class ExpiresTickets(Base):
    __tablename__ = "expires_tickets"

    ticket_number = Column(Integer, primary_key=True)
    responsible = Column(String(50))
    comment = Column(String)
    add_date = Column(DateTime, default=datetime.utcnow)

class StoppedTickets(Base):
    __tablename__ = "stopped_tickets"

    task_number = Column(String, primary_key=True)
    agreement_pause = Column(DateTime, default=datetime.utcnow)
    begin_pause = Column(DateTime, default=datetime.utcnow)
    end_pause = Column(DateTime, default=datetime.utcnow)
    who_paused = Column(String(50))
    last_comment = Column(String)
    who_ask_pause = Column(String(50))
    sla = Column(DateTime, default=datetime.utcnow)


engine_db = create_engine(db_path)
Base.metadata.create_all(engine_db)
