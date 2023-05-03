<h2>Analytics NTTM-BI</h2>

- Микросервис с клиент-серверной архитектурой для BI-аналитики представляющий собой интеграцию с TTM-системой для анализа причин превышения показателей SLA с подробным анализом и информацией о работе подразделений, задействованных в решении проблемы, задачей которого является мониторинг состояния тикетов всего направления в реальном времени для своевременного обнаружения причин превышения показателей SLA, актуальный список тикетов в приостановке и отображения этого на дашборде BI-аналитики.

<h2>Требования</h2>

- python 3.11
- asyncio
- aiohttp
- websockets
- threading
- sqlalchemy
- docker

<h2>Процесс развёртывания (деплоя)</h2>

1. На стороне сервера:

  Сервер должен иметь сетевую связанность: 
  - с сетью где находится BI-аналитика
  - с сетью клиента

  1. Установить (для Ubuntu):

    Docker:
      - sudo apt update
      - sudo apt install apt-transport-https ca-certificates curl software-properties-common
      - curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
      - sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu focal stable"
      - sudo apt update
      - apt-cache policy docker-ce
      - sudo apt install docker-ce
      - sudo systemctl status docker

    Docker-compose:
      - sudo curl -L "https://github.com/docker/compose/releases/download/1.26.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
      - sudo chmod +x /usr/local/bin/docker-compose

  2. Создать файл .env в директории ./app и заполнить переменные окружения, где: 

    DB_USER={логин пользователя PostgreSQL}
    DB_PASSWORD={пароль от пользователя PostgreSQL}
    DB_NAME={название БД в PostgreSQL}
    DB_PATH={путь для доступа к БД - postgresql://login:password@ip:port/dbname}
    TOKEN={токен авторизации}
    KEY={ключ авторизации}
    PORT={порт на котором развернуть сервер}
    INTERVAL={интервал запросов к тикет-системе в секундах}
    FILTER_ARREARS={ключ фильтра просроченных тикетов по SLA}
    FILTER_STOPPED={ключ фильтра приостановленных тикетов}

  3. Запустить команду: docker-compose -f docker-compose-app.yaml up -d из директории ./app

2. На стороне клиента:

  Клиент должен имень сетевую связанность с:
  - сетью сервера
  - сетью тикет-системы

  1. Установить (для Ubuntu):

    Docker: подробнее в пункте 1.1

  2. Создать файл .env в директории ./connector и заполнить переменные окружения, где:

    EMAIL={почта пользователя тикет-системы}
    PASSWORD={пароль пользователя тикет-системы}
    URL={адрес тикет-системы в сети}
    TOKEN={токен авторизации, должен быть такой же как в пункте 1.2}
    KEY={ключ авторизации, должен быть такой же как в пункте 1.2}
    SERVER={адрес вебсокет сервера - ws://ip:port}

  3. Запустить команду: docker build -t {имя образа} - < Dockerfile из директории ./connector

  4. Запустить команду: docker run {имя образа} 
