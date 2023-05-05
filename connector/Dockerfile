FROM python:3.11-slim

RUN mkdir ./connector_nttm
COPY . ./connector_nttm
WORKDIR /connector_nttm

RUN python3 -m pip install -r requirements.txt

EXPOSE 8088

CMD ["python3", "connector.py"]
