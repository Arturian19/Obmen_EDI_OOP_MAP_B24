"""
Точка входа. Создаёт зависимости и запускает окно.

Почему ООП: все объекты (репозиторий, обмен, коннектор 1С) создаются
здесь и ПЕРЕДАЮТСЯ в MainWindow через конструктор — Dependency Injection.
Окно само ничего не подключает, отсюда его легко тестировать.
"""
import sys
from PySide6.QtWidgets import QApplication

from edi.infrastructure.config import AppConfig
from edi.infrastructure.file_exchange import FileExchange
from edi.infrastructure.onec_connector import OneCConnector
from edi.infrastructure.exchange_service import ExchangeService
from edi.repository.db import MessageRepository
from edi.ui.main_window import MainWindow, APP_STYLES


def main():
    cfg = AppConfig()

    # зависимости
    repo = MessageRepository(cfg.db_path, my_role=cfg.my_role)
    exchange = FileExchange(cfg.inbox_dir, cfg.outbox_dir, cfg.processed_dir)
    onec = OneCConnector(cfg.onec_base_url, cfg.onec_user, cfg.onec_password,
                         use_mock=True)
    service = ExchangeService(exchange, onec, repo)

    # интерфейс
    app = QApplication(sys.argv)
    app.setStyle("Fusion")              # предсказуемый вид на любой Windows
    app.setStyleSheet(APP_STYLES)       # белый фон + синяя кнопка обмена

    window = MainWindow(repo=repo, service=service, config=cfg)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()