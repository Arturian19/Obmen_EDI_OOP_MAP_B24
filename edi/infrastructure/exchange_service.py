"""
Сервис-фасад: связывает FileExchange, OneCConnector и MessageRepository.
"""
from datetime import datetime

from edi.infrastructure.file_exchange import FileExchange
from edi.infrastructure.onec_connector import OneCConnector
from edi.repository.db import MessageRepository


class ExchangeService:
    def __init__(self, exchange: FileExchange, onec: OneCConnector, repo: MessageRepository):
        self.exchange = exchange
        self.onec = onec
        self.repo = repo

    def send_message(self, message, document_1c: str) -> str:
        if self.repo.exists(message.DOCUMENT_TYPE, document_1c):
            raise ValueError(f"{message.DOCUMENT_TYPE} по {document_1c} уже отправлено")
        path = self.exchange.send(message)
        self.repo.save(message, direction="OUT", document_1c=document_1c, status="SENT")
        return path

    def receive_all(self) -> int:
        processed = 0
        for filename, content in self.exchange.receive():
            try:
                msg = self.exchange.parse_message(content)
                doc_1c = msg.origin_order_number or msg.document_number
                self.repo.save(msg, direction="IN", document_1c=doc_1c, status="RECEIVED")
                self.exchange.mark_processed(filename)
                processed += 1
            except Exception as e:
                self.exchange.mark_failed(filename, str(e))
                print(f"[ExchangeService] {filename}: {e}")
        return processed

    def do_exchange(self) -> dict:
        received = self.receive_all()
        return {"received": received, "timestamp": datetime.now().isoformat()}