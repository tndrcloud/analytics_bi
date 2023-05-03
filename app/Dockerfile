FROM python:3.11-slim

RUN mkdir ./analytics_bi
COPY . ./analytics_bi
WORKDIR /analytics_bi

RUN python3 -m venv venv
RUN python3 -m pip install -r requirements.txt

EXPOSE 8080

CMD ["python3", "main.py"]
