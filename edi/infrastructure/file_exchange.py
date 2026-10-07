"""
Файловый обмен XML-сообщениями (эмуляция EDI-сервера).
"""
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
from uuid import uuid4

from edi.models.messages.base import BaseEDIMessage


class FileExchange:
    def __init__(self, inbox: str, outbox: str, processed: str):
        self.inbox = Path(inbox)
        self.outbox = Path(outbox)
        self.processed = Path(processed)
        for p in (self.inbox, self.outbox, self.processed):
            p.mkdir(parents=True, exist_ok=True)

    def send(self, message: BaseEDIMessage) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{message.DOCUMENT_TYPE}_{ts}_{str(uuid4())[:8]}.xml"
        path = self.outbox / filename
        path.write_text(message.to_xml_string(), encoding="utf-8")
        return str(path)

    def receive(self) -> List[Tuple[str, str]]:
        result = []
        for f in sorted(self.inbox.glob("*.xml")):
            try:
                result.append((f.name, f.read_text(encoding="utf-8")))
            except Exception as e:
                print(f"[FileExchange] Ошибка чтения {f.name}: {e}")
        return result

    def mark_processed(self, filename: str) -> None:
        src = self.inbox / filename
        if src.exists():
            dst = self.processed / f"{datetime.now():%Y%m%d_%H%M%S}_{filename}"
            shutil.move(str(src), str(dst))

    def mark_failed(self, filename: str, reason: str = "") -> None:
        src = self.inbox / filename
        if src.exists():
            dst = self.inbox / f"{filename}.error"
            src.rename(dst)
            if reason:
                (self.inbox / f"{filename}.error.log").write_text(reason, encoding="utf-8")

    @staticmethod
    def detect_message_type(xml_content: str) -> str:
        for t in ("ORDERS", "ORDRSP", "DESADV", "RECADV", "INVOIC"):
            if f"<documentType>{t}</documentType>" in xml_content:
                return t
        return ""

    @staticmethod
    def parse_message(xml_content: str) -> BaseEDIMessage:
        from edi.models.messages.orders import OrdersMessage
        from edi.models.messages.ordrsp import OrdrspMessage
        from edi.models.messages.desadv import DesadvMessage
        from edi.models.messages.recadv import RecadvMessage
        from edi.models.messages.invoic import InvoiceMessage

        mapping = {
            "ORDERS": OrdersMessage, "ORDRSP": OrdrspMessage,
            "DESADV": DesadvMessage, "RECADV": RecadvMessage,
            "INVOIC": InvoiceMessage,
        }
        t = FileExchange.detect_message_type(xml_content)
        if t not in mapping:
            raise ValueError(f"Неизвестный тип: '{t}'")
        return mapping[t].from_xml_string(xml_content)