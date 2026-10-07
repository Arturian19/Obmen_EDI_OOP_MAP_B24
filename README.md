# Obmen EDI OOP — курсовая работа по ООП

Клиент для обмена EDI-сообщениями между торговой сетью и поставщиком.
Форматы сообщений: **ORDERS / ORDRSP / DESADV / RECADV / INVOIC**.

## Стек

- Python 3.13
- PySide6 — графический интерфейс
- SQLite — хранение истории сообщений, защита от дублей
- requests — интеграция с HTTP-сервисом 1С УТ 11.5
- PyInstaller — сборка в исполняемый файл

## Применение ООП

| Приём | Где в проекте |
|---|---|
| **Инкапсуляция** | `LineItem` прячет расчёты НДС и сумм; `FileExchange` — работу с файлами; `MessageRepository` — SQL-запросы |
| **Наследование** | 5 классов сообщений (`OrdersMessage`, `OrdrspMessage`, `DesadvMessage`, `RecadvMessage`, `InvoiceMessage`) от `BaseEDIMessage`; 5 классов строк от `LineItem` |
| **Полиморфизм** | Единый `to_xml_string()` работает по-разному для каждого типа; `calculate_totals()` считает итоги по разным полям количества через свойство `quantity` |
| **Абстракция** | `ABC` + `@abstractmethod` в базовом классе; `OneCConnector` скрывает детали связи с 1С |
| **Паттерн Фабрика** | `FileExchange.parse_message()` создаёт нужный класс сообщения по тегу `<documentType>` |

## Структура проекта

    edi/
    ├── models/            # доменные модели (Organization, LineItem, 5 сообщений)
    ├── repository/        # хранение в SQLite + защита от дублей
    ├── infrastructure/    # обмен (FileExchange, OneCConnector, ExchangeService)
    └── ui/                # интерфейс PySide6
    samples/               # примеры XML-сообщений
    exchange/              # папки обмена inbox / outbox / processed
    docs/screenshots/      # скриншоты для отчёта

## Установка и запуск

    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt
    python main.py

## Демонстрация обмена

1. Положите XML-файл в `exchange/inbox/`.
2. Нажмите **«Обмен с сервером»** — сообщение распарсится, попадёт в таблицу,
   файл переедет в `exchange/processed/`.
3. Кнопка **«Сформировать ORDERS из 1С»** формирует исходящее сообщение
   и кладёт его в `exchange/outbox/`.
4. Повторная отправка того же документа блокируется — защита от дублей.

## Сборка исполняемого файла

    pip install pyinstaller
    pyinstaller --noconsole --onefile --name="EDI_Client" main.py

Готовый `dist\EDI_Client.exe` работает на любом Windows без установки Python.

## Ограничения

- Интеграция с 1С реализована через `OneCConnector` с заглушкой (`use_mock=True`).
  Замена на реальный HTTP-сервис — смена одного параметра на `use_mock=False`.
- Обмен с EDI-сервером эмулируется файловой папкой (inbox/outbox/processed).

## Автор

Макс Артур Петрович, группа Б24-191-1зу, 07.10.2026 г.