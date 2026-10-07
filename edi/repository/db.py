"""
Хранилище сообщений в SQLite. Защита от дублей.

Почему ООП:
- Инкапсуляция: весь SQL спрятан внутри методов класса. Вызывающий код
  (UI, ExchangeService) не знает ни одной таблицы и ни одного поля.
- Единая точка доступа: если завтра перейти на PostgreSQL — меняем
  только этот файл, остальной проект не трогаем.
- Роль пользователя (supplier/network) передаётся в конструктор и
  используется для расчёта «контрагента» — это data, спрятанный в объекте.
"""
import sqlite3
from datetime import datetime
from pathlib import Path


class MessageRepository:
    def __init__(self, db_path: str = "edi.db", my_role: str = "supplier"):
        self.db_path = Path(db_path)
        self.my_role = my_role          # 'supplier' или 'network'
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self.db_path) as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id               TEXT PRIMARY KEY,
                    message_type     TEXT NOT NULL,
                    direction        TEXT NOT NULL,   -- 'IN' | 'OUT'
                    order_number     TEXT,
                    document_number  TEXT,
                    document_1c      TEXT,
                    counterparty     TEXT,
                    delivery_date    TEXT,
                    total_amount     REAL,
                    status           TEXT,
                    created_at       TEXT,
                    xml_content      TEXT,
                    delivery_address TEXT
                )
            """)
            # Миграция старых баз: колонки delivery_address в них ещё нет
            try:
                con.execute("ALTER TABLE messages ADD COLUMN delivery_address TEXT")
            except sqlite3.OperationalError:
                pass
            con.execute("CREATE INDEX IF NOT EXISTS idx_order ON messages(order_number)")
            con.execute("CREATE INDEX IF NOT EXISTS idx_type  ON messages(message_type)")

    # ------------------------------------------------------------------
    # ПРОВЕРКА НА ДУБЛЬ (защита от повторной отправки)
    # ------------------------------------------------------------------
    def exists(self, message_type: str, document_1c: str) -> bool:
        with sqlite3.connect(self.db_path) as con:
            cur = con.execute(
                "SELECT 1 FROM messages WHERE message_type=? AND document_1c=? LIMIT 1",
                (message_type, document_1c),
            )
            return cur.fetchone() is not None

    # ------------------------------------------------------------------
    # СОХРАНЕНИЕ
    # ------------------------------------------------------------------
    def save(self, msg, direction: str, document_1c: str, status: str = "NEW") -> None:
        totals = msg.calculate_totals()

        # Контрагент = «тот, кто не мы».
        # Поставщику всегда интересна сеть (buyer), сети — поставщик (seller).
        other = msg.buyer if self.my_role == "supplier" else msg.seller

        # Дата поставки зависит от типа сообщения — перебираем все варианты,
        # иначе у RECADV (receptionDateTime) колонка была бы пустой.
        delivery_date = (msg.requested_delivery_dt or msg.estimated_delivery_dt
                         or msg.actual_delivery_dt or msg.reception_dt
                         or msg.shipping_dt)

        with sqlite3.connect(self.db_path) as con:
            con.execute("""
                INSERT OR REPLACE INTO messages
                (id, message_type, direction, order_number, document_number, document_1c,
                 counterparty, delivery_date, total_amount, status, created_at,
                 xml_content, delivery_address)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                msg.message_id,
                msg.DOCUMENT_TYPE,
                direction,
                msg.origin_order_number or msg.document_number,
                msg.document_number,
                document_1c,
                other.name,
                delivery_date,
                totals["totalAmount"],
                status,
                datetime.now().isoformat(),
                msg.to_xml_string(),
                msg.ship_to.address_line(),
            ))

    # ------------------------------------------------------------------
    # ВЫБОРКА ДЛЯ ТАБЛИЦЫ
    # ------------------------------------------------------------------
    def list_messages(self, message_type=None, order_number=None,
                      counterparty=None, date_from=None, date_to=None):
        # ПОРЯДОК ПОЛЕЙ ФИКСИРОВАН — его же использует MessageTableModel.COL_MAP.
        # 0 id | 1 message_type | 2 direction | 3 order_number | 4 document_number
        # 5 counterparty | 6 delivery_date | 7 total_amount | 8 status
        # 9 created_at | 10 delivery_address
        sql = ("SELECT id, message_type, direction, order_number, document_number, "
               "counterparty, delivery_date, total_amount, status, created_at, "
               "delivery_address "
               "FROM messages WHERE 1=1")
        params = []
        if message_type:
            sql += " AND message_type=?"
            params.append(message_type)
        if order_number:
            sql += " AND order_number LIKE ?"
            params.append(f"%{order_number}%")
        if counterparty:
            sql += " AND counterparty=?"
            params.append(counterparty)
        if date_from:                       # <-- фильтр периода стал работать
            sql += " AND created_at >= ?"
            params.append(date_from)
        if date_to:
            sql += " AND created_at <= ?"
            params.append(date_to)
        sql += " ORDER BY created_at DESC"
        with sqlite3.connect(self.db_path) as con:
            return con.execute(sql, params).fetchall()

    # ------------------------------------------------------------------
    # СПИСОК КОНТРАГЕНТОВ ДЛЯ ФИЛЬТРА
    # ------------------------------------------------------------------
    def list_counterparties(self):
        with sqlite3.connect(self.db_path) as con:
            return [r[0] for r in con.execute(
                "SELECT DISTINCT counterparty FROM messages "
                "WHERE counterparty IS NOT NULL AND counterparty != '' "
                "ORDER BY counterparty"
            )]

    def get_by_id(self, msg_id: str):
        with sqlite3.connect(self.db_path) as con:
            row = con.execute(
                "SELECT xml_content FROM messages WHERE id=?", (msg_id,)
            ).fetchone()
        return row[0] if row else None