"""
Главное окно приложения EDI Client.

Почему ООП:
- Наследование от QMainWindow: переиспользуем всю инфраструктуру Qt
  (меню, статусбар, системные события) вместо написания с нуля.
- Модель (MessageTableModel) отделена от представления (QTableView) —
  паттерн MVC. Модель можно заменить на другую, не трогая визуал.
- Зависимости (repo, service, config) внедряются через конструктор
  (Dependency Injection) — класс не создаёт их сам, значит его легко
  тестировать и переиспользовать.
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QComboBox, QTableView, QLabel, QMessageBox, QDialog,
    QTextEdit, QDateEdit, QInputDialog, QAbstractItemView,
)
from PySide6.QtCore import QAbstractTableModel, Qt, QModelIndex, QDate
from PySide6.QtGui import QColor

from edi.repository.db import MessageRepository
from edi.infrastructure.exchange_service import ExchangeService
from edi.infrastructure.config import AppConfig


# ======================================================================
# СТИЛИ: белый интерфейс + синяя кнопка «Обмен с сервером»
# (применяются ко всему приложению через app.setStyleSheet)
# ======================================================================
APP_STYLES = """
QMainWindow, QWidget {
    background-color: #ffffff;
    color: #1f2937;
    font-size: 13px;
    font-family: 'Segoe UI', Arial, sans-serif;
}
QLabel { background: transparent; }

/* --- строки фильтров --- */
QLineEdit, QComboBox, QDateEdit {
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 22px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus {
    border: 1px solid #2563eb;
}

/* --- таблица --- */
QTableView {
    background: #ffffff;
    alternate-background-color: #f9fafb;
    gridline-color: #e5e7eb;
    border: 1px solid #e5e7eb;
    selection-background-color: #dbeafe;
    selection-color: #111827;
}
QHeaderView::section {
    background-color: #f3f4f6;
    color: #374151;
    font-weight: bold;
    padding: 7px 8px;
    border: none;
    border-right: 1px solid #e5e7eb;
    border-bottom: 1px solid #e5e7eb;
}

/* --- обычные кнопки --- */
QPushButton {
    background: #ffffff;
    border: 1px solid #d1d5db;
    border-radius: 4px;
    padding: 6px 14px;
}
QPushButton:hover { background: #f3f4f6; }

/* --- ГЛАВНАЯ кнопка: «Обмен с сервером» --- */
QPushButton#btnExchange {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
    padding: 7px 20px;
    font-weight: bold;
}
QPushButton#btnExchange:hover  { background-color: #1d4ed8; }
QPushButton#btnExchange:pressed { background-color: #1e40af; }
"""


# ======================================================================
# МОДЕЛЬ ТАБЛИЦЫ (MVC: модель, а не сама таблица)
# ======================================================================
class MessageTableModel(QAbstractTableModel):
    # Порядок соответствует SELECT в MessageRepository.list_messages():
    #  0 id | 1 message_type | 2 direction | 3 order_number | 4 document_number
    #  5 counterparty | 6 delivery_date | 7 total_amount | 8 status
    #  9 created_at | 10 delivery_address
    COLUMNS = ["Требуемое действие", "Номер заказа", "Номер сообщения", "Тип",
               "Дата поставки", "Адрес доставки", "Контрагент",
               "Сумма, ₽", "Статус", "Направление"]

    # Какое поле SELECT показывать в каждой колонке (None = вычисляется кодом).
    # Явный маппинг — именно из-за его отсутствия колонки «поехали».
    COL_MAP = [None,   # 0 Требуемое действие  -> вычисляется
               3,      # 1 Номер заказа        -> order_number
               4,      # 2 Номер сообщения     -> document_number
               1,      # 3 Тип                 -> message_type
               6,      # 4 Дата поставки       -> delivery_date
               10,     # 5 Адрес доставки      -> delivery_address
               5,      # 6 Контрагент          -> counterparty
               7,      # 7 Сумма               -> total_amount
               8,      # 8 Статус              -> status
               2]      # 9 Направление         -> direction

    def __init__(self, rows):
        super().__init__()
        self._rows = rows

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    @staticmethod
    def _action(row) -> str:
        """Что пользователю нужно сделать с сообщением (колонка из ТЗ)."""
        direction, mtype = row[2], row[1]
        if direction == "IN" and mtype == "ORDERS":
            return "Сформировать ORDRSP"
        if direction == "IN" and mtype == "DESADV":
            return "Сформировать RECADV"
        if direction == "IN" and mtype == "RECADV":
            return "Сформировать INVOIC"
        return "Просмотр"

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        col = index.column()
        row = self._rows[index.row()]

        if role == Qt.ForegroundRole and col == 0:
            return QColor("#2563eb")          # действие — синим, «кликабельным»

        if role == Qt.DisplayRole:
            if col == 0:
                return self._action(row)
            value = row[self.COL_MAP[col]]
            if value is None:
                return ""
            if col == 7:                        # формат суммы: 13 000,04
                try:
                    return f"{float(value):,.2f}".replace(",", " ").replace(".", ",")
                except (TypeError, ValueError):
                    return str(value)
            return str(value)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def get_id(self, row: int) -> str:
        return self._rows[row][0]


# ======================================================================
# ДИАЛОГ ПРОСМОТРА XML
# ======================================================================
class MessageDialog(QDialog):
    def __init__(self, xml_content: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Просмотр сообщения")
        self.resize(900, 600)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("XML-содержимое сообщения:"))
        editor = QTextEdit()
        editor.setPlainText(xml_content or "")
        editor.setReadOnly(True)
        editor.setFontFamily("Consolas")
        layout.addWidget(editor)


# ======================================================================
# ГЛАВНОЕ ОКНО
# ======================================================================
class MainWindow(QMainWindow):
    def __init__(self, repo: MessageRepository, service: ExchangeService,
                 config: AppConfig):
        super().__init__()
        self.repo = repo
        self.service = service
        self.config = config
        self.setWindowTitle("EDI Client — Курсовая работа")
        self.resize(1280, 720)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # ---------- 1. КНОПКИ (СВЕРХУ, как в ТЗ) ----------
        buttons = QHBoxLayout()
        buttons.setSpacing(8)

        self.btn_exchange = QPushButton("Обмен с сервером")
        self.btn_exchange.setObjectName("btnExchange")   # <- синий стиль из APP_STYLES
        self.btn_refresh = QPushButton("Обновить список")
        self.btn_create = QPushButton("Сформировать ORDERS из 1С")

        self.btn_exchange.clicked.connect(self.on_exchange)
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_create.clicked.connect(self.on_create_orders)

        buttons.addWidget(self.btn_exchange)
        buttons.addWidget(self.btn_refresh)
        buttons.addWidget(self.btn_create)
        buttons.addStretch(1)
        layout.addLayout(buttons)

        # ---------- 2. ФИЛЬТРЫ ----------
        filters = QHBoxLayout()
        filters.setSpacing(6)

        self.search_order = QLineEdit()
        self.search_order.setPlaceholderText("Быстрый отбор: номер заказа")

        self.msg_type = QComboBox()
        self.msg_type.addItems(["Все", "ORDERS", "ORDRSP", "DESADV", "RECADV", "INVOIC"])

        self.supplier_box = QComboBox()
        self.supplier_box.addItem("Все контрагенты")

        self.date_from = QDateEdit(calendarPopup=True)
        self.date_from.setDisplayFormat("dd.MM.yyyy")
        self.date_from.setDate(QDate.currentDate().addMonths(-1))

        self.date_to = QDateEdit(calendarPopup=True)
        self.date_to.setDisplayFormat("dd.MM.yyyy")
        self.date_to.setDate(QDate.currentDate())

        filters.addWidget(QLabel("Заказ:"))
        filters.addWidget(self.search_order, 2)
        filters.addWidget(QLabel("Тип:"))
        filters.addWidget(self.msg_type)
        filters.addWidget(QLabel("Контрагент:"))
        filters.addWidget(self.supplier_box, 2)
        filters.addWidget(QLabel("Период с:"))
        filters.addWidget(self.date_from)
        filters.addWidget(QLabel("по:"))
        filters.addWidget(self.date_to)
        layout.addLayout(filters)

        # ---------- 3. ТАБЛИЦА ----------
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(False)
        self.table.doubleClicked.connect(self.open_message)
        self.table.clicked.connect(self.on_cell_click)
        layout.addWidget(self.table, 1)          # растягивается на всё окно

        self.setCentralWidget(central)

        # ---------- 4. ФИЛЬТРЫ ОБНОВЛЯЮТ СПИСОК АВТОМАТИЧЕСКИ ----------
        self.search_order.textChanged.connect(self.refresh)
        self.msg_type.currentIndexChanged.connect(self.refresh)
        self.supplier_box.currentIndexChanged.connect(self.refresh)
        self.date_from.dateChanged.connect(self.refresh)
        self.date_to.dateChanged.connect(self.refresh)

    # ------------------------------------------------------------------
    def refresh(self):
        t = self.msg_type.currentText()
        supplier = self.supplier_box.currentText()

        # Период отбора наконец передаётся в запрос (исправление Б3)
        d_from = self.date_from.date().toString("yyyy-MM-dd") + "T00:00:00"
        d_to = self.date_to.date().toString("yyyy-MM-dd") + "T23:59:59"

        rows = self.repo.list_messages(
            message_type=None if t == "Все" else t,
            order_number=self.search_order.text().strip() or None,
            counterparty=None if supplier.startswith("Все") else supplier,
            date_from=d_from,
            date_to=d_to,
        )
        self.table.setModel(MessageTableModel(rows))

        # Обновить список контрагентов, не сбрасывая выбранный фильтр
        current = self.supplier_box.currentText()
        self.supplier_box.blockSignals(True)
        self.supplier_box.clear()
        self.supplier_box.addItem("Все контрагенты")
        self.supplier_box.addItems(self.repo.list_counterparties())
        idx = self.supplier_box.findText(current)
        self.supplier_box.setCurrentIndex(idx if idx >= 0 else 0)
        self.supplier_box.blockSignals(False)

    # ------------------------------------------------------------------
    def on_cell_click(self, index):
        """Клик по колонке «Требуемое действие» открывает форму сообщения."""
        if index.column() == 0:
            self.open_message(index)

    def open_message(self, index):
        model = self.table.model()
        if model is None:
            return
        xml = self.repo.get_by_id(model.get_id(index.row()))
        if xml is None:
            QMessageBox.warning(self, "Ошибка", "Сообщение не найдено в базе.")
            return
        dialog = MessageDialog(xml, self)   # ссылка сохраняется (исправление Б11)
        dialog.exec()

    # ------------------------------------------------------------------
    def on_exchange(self):
        try:
            result = self.service.do_exchange()
            QMessageBox.information(
                self, "Обмен",
                f"Получено сообщений: {result['received']}"
            )
            self.refresh()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка обмена", str(e))

    # ------------------------------------------------------------------
    def on_create_orders(self):
        """Формирует ORDERS из данных 1С и отправляет его в outbox."""
        from edi.models.messages.orders import OrdersMessage, LineItemOrders
        try:
            orders = self.service.onec.get_orders()
            if not orders:
                QMessageBox.information(self, "1С", "Заказов не найдено.")
                return

            # Выбор заказа (исправление Б6: раньше всегда брался orders[0]
            # и кнопка срабатывала только один раз)
            labels = [f"{o.number}  от {o.date}" for o in orders]
            pick, ok = QInputDialog.getItem(
                self, "Заказ из 1С", "Выберите заказ поставщику:", labels, 0, False
            )
            if not ok:
                return
            o = orders[labels.index(pick)]

            msg = OrdersMessage()
            msg.sender_gln = self.config.my_gln       # отправитель — мы
            msg.recipient_gln = o.buyer.gln           # <-- ИСПРАВЛЕНО (Б5): получатель — сеть
            msg.document_number = o.number
            msg.document_date = o.date
            msg.contract_number = "1"
            msg.contract_date = o.date
            msg.seller = o.supplier
            msg.buyer = o.buyer
            msg.invoicee = o.consignee
            msg.ship_from = o.supplier
            msg.ship_to = o.consignee
            msg.requested_delivery_dt = o.date + "T00:00:00.000Z"

            for line in o.lines:
                msg.line_items.append(LineItemOrders(
                    gtin=line.gtin,
                    description=line.name,
                    net_price=line.price,
                    vat_rate=line.vat_rate,
                    supplier_code=line.supplier_code,
                    buyer_code=line.buyer_code,
                    requested_quantity=line.quantity,
                ))

            path = self.service.send_message(msg, document_1c=o.number)
            QMessageBox.information(self, "Отправлено", f"Файл:\n{path}")
            self.refresh()
        except ValueError as e:          # защита от дублей — это не поломка
            QMessageBox.warning(self, "Уже отправлено", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))