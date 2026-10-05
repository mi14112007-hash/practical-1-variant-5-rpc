# Практическое задание № 1, вариант 5

Прототип сервиса на Python: таблицы `Person`, `Query`, `Result` хранятся
в списках в оперативной памяти. Десять операций доступны напрямую через
`DataModel`, в локальном REPL и удалённо через TCP RPC. Данные исчезают при
остановке сервера. Файл `journal.log` содержит журнал ответов RPC, а не
снимок таблиц.

## Структура данных

| Сущность | Поля |
| --- | --- |
| Person | `identifier: int`, `time: int`, `locale: str`, `user_agent: str` |
| Query | `identifier: int`, `time: int`, `content: str`, `person: int` |
| Result | `identifier: int`, `time: int`, `output: str`, `state: str`, `failure: str`, `query: int`, `duration: int` |

`identifier` уникален в своей таблице и не редактируется. Внешние ключи
`Query.person` и `Result.query` должны указывать на существующие записи.
При создании нужны все поля; при редактировании передают только меняемые.
Тип `int` не принимает `bool`. Все временные метки заданы целыми секундами
Unix. При ошибке возвращается понятное сообщение, состояние не меняется.

Метод `recent_queries(now)` реализует соединение `Person` и отобранных
`Query`: берёт запросы с `Query.time > now - 9 * 60`, связывает их по
`Person.identifier = Query.person` и возвращает только пары `locale`,
`content`. Равенство нижней границе в выборку не входит. Если `now`
опущен, берётся текущее время сервера.

## Запуск

Нужен Python 3.10 или новее. Рабочая папка — корень репозитория.

```sh
./run.sh local
./run.sh server --host 127.0.0.1 --port 8765
./run.sh client --host 127.0.0.1 --port 8765
```

На macOS и Linux доступны также цели `make local`, `make server` и
`make client`. Адрес и порт для `make` задаются переменными `HOST` и
`PORT`, путь журнала — `JOURNAL`. Например:

```sh
make server PORT=9000
make client PORT=9000
```

В Windows те же режимы запускаются через `run.bat`:

```bat
run.bat local
run.bat server --host 127.0.0.1 --port 8765
run.bat client --host 127.0.0.1 --port 8765
```

Команды сервера и клиента запускают в разных терминалах. Опция
`--journal PATH` задаёт путь журнала сервера; по умолчанию `journal.log`.
Публичный сетевой интерфейс можно задать через `--host`, если это нужно.
В локальном режиме взаимодействие с сетью не требуется. `quit` завершает
любой REPL. Настройки клиента: адрес, порт и тайм-аут (по умолчанию 5 с;
в Python API параметр `timeout`).

## Операции и примеры

Имена десяти методов клиента и модели совпадают:

| Операция | Аргументы | Результат |
| --- | --- | --- |
| `create_person` | `record` | Созданная запись Person |
| `get_people` | нет | Список Person |
| `edit_person` | `identifier`, `changes` | Изменённая Person |
| `create_query` | `record` | Созданная Query |
| `get_queries` | нет | Список Query |
| `edit_query` | `identifier`, `changes` | Изменённая Query |
| `create_result` | `record` | Созданная Result |
| `get_results` | нет | Список Result |
| `edit_result` | `identifier`, `changes` | Изменённая Result |
| `recent_queries` | `now` (необязательно) | Список пар `locale`, `content` |

В REPL каждая строка — JSON-объект с полями `method` и `args`.
Следующий сеанс подходит и для `local`, и для `client` после запуска
сервера. Для воспроизводимой выборки используется `now=2000000`.

```json
{"method":"create_person","args":{"record":{"identifier":1,"time":1999000,"locale":"ru-RU","user_agent":"Firefox"}}}
{"method":"get_people","args":{}}
{"method":"edit_person","args":{"identifier":1,"changes":{"locale":"en-US"}}}
{"method":"create_query","args":{"record":{"identifier":10,"time":1999900,"content":"weather","person":1}}}
{"method":"get_queries","args":{}}
{"method":"edit_query","args":{"identifier":10,"changes":{"content":"forecast"}}}
{"method":"create_result","args":{"record":{"identifier":20,"time":1999901,"output":"sunny","state":"done","failure":"","query":10,"duration":3}}}
{"method":"get_results","args":{}}
{"method":"edit_result","args":{"identifier":20,"changes":{"output":"cloudy"}}}
{"method":"recent_queries","args":{"now":2000000}}
{"method":"create_query","args":{"record":{"identifier":11,"time":1999900,"content":"bad","person":999}}}
```

Последний вызов показывает обработку ошибки отсутствующего внешнего
ключа. Выборка возвращает `[{"locale":"en-US","content":"forecast"}]`.
Из Python доступен тот же интерфейс:

```python
from src.model import DataModel
from src.rpc import RpcClient

model = DataModel()
client = RpcClient("127.0.0.1", 8765)
print(client.get_people())
```

## Формат протокола

Все целые поля заголовков передаются в порядке от старшего байта к
младшему. Тело — UTF-8 JSON. TCP-соединение может содержать несколько
запросов; клиент открывает отдельное соединение на вызов.

| Направление | Смещение | Длина | Содержание |
| --- | ---: | ---: | --- |
| Запрос | 0 | 5 | Длина JSON-тела |
| Запрос | 5 | 2 | Код операции 1–10 |
| Запрос | 7 | переменная | JSON-объект аргументов |
| Ответ | 0 | 1 | Код операции; 0 при ошибке |
| Ответ | 1 | 4 | Длина JSON-тела |
| Ответ | 5 | переменная | JSON-объект результата |

Ответ успешного вызова: `{"ok":true,"result":...}`. Ответ ошибки:
`{"ok":false,"error":"..."}`. Размер тела запроса ограничен 1 МБ.
Каждый отправленный ответ журналируется как hex-представление полного
кадра с датой и временем.

## Проверка

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
coverage run -m pytest
coverage report -m
coverage html
ruff check src tests
ruff format --check src tests
```

Все тесты запускаются через Hypothesis. `tests/test_state_machine.py`
использует `RuleBasedStateMachine`: Hypothesis генерирует последовательности
создания и изменения записей, а независимая модель на словарях после
каждого шага проверяет все таблицы и выборку. Этот тест вызывает все десять
RPC-методов, в том числе ошибочные обращения. `tests/test_protocol.py`
проверяет повреждённые и неполные TCP-кадры, превышение размера и ответы
с неверным кодом операции. `tests/test_cli.py` проверяет REPL и все режимы
запуска. Покрытие измеряется по строкам и ветвям **всех** модулей `src`.
Команды `ruff` проверяют стиль и форматирование кода.

Проверенный результат:

```text
6 passed
Name              Stmts   Miss Branch BrPart  Cover
---------------------------------------------------
src/__init__.py       0      0      0      0   100%
src/cli.py           48      0     14      0   100%
src/model.py         78      0     24      0   100%
src/rpc.py          126      0     26      0   100%
---------------------------------------------------
TOTAL               252      0     64      0   100%
```

## Этапы работы

1. Модель данных и локальный REPL.
2. TCP RPC, клиент и журнал ответов.
3. Тестирование на основе модели и отчёт о покрытии ветвей.
