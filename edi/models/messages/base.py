"""
Абстрактный базовый класс для всех EDI-сообщений.

Почему ООП:
- ABC — единый контракт: наследники ОБЯЗАНЫ реализовать
  _build_document_body, _parse_document_body и _make_line_item.
- Общие поля и логика подсчёта итогов — здесь, чтобы не дублировать
  их в 5 наследниках.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from uuid import uuid4
import xml.etree.ElementTree as ET

from edi.models.organization import Organization
from edi.models.line_item import LineItem


class BaseEDIMessage(ABC):
    DOCUMENT_TYPE: str = ""

    def __init__(self):
        self.message_id = str(uuid4())
        self.sender_gln = ""
        self.recipient_gln = ""
        self.creation_dt = datetime.now()

        # Контрагенты
        self.seller = Organization()
        self.buyer = Organization()
        self.invoicee = Organization()
        self.ship_from = Organization()
        self.ship_to = Organization()

        # Ссылки на документы-основания
        self.origin_order_number = ""
        self.origin_order_date = ""
        self.contract_number = ""
        self.contract_date = ""

        # Табличная часть
        self.line_items: List[LineItem] = []

        # Даты
        self.requested_delivery_dt = ""
        self.estimated_delivery_dt = ""
        self.shipping_dt = ""
        self.actual_delivery_dt = ""
        self.reception_dt = ""

        # Номер / дата документа
        self.document_number = ""
        self.document_date = ""

    # ---------- ИТОГИ ----------
    def calculate_totals(self) -> dict:
        total_no_vat = 0.0
        total_vat = 0.0
        for li in self.line_items:
            qty = li.quantity
            total_no_vat += li.net_price * qty
            total_vat += li.calc_vat_amount(qty)
        return {
            "totalSumExcludingTaxes": round(total_no_vat, 2),
            "totalVATAmount": round(total_vat, 2),
            "totalAmount": round(total_no_vat + total_vat, 2),
        }

    # ---------- ОБЩИЕ БЛОКИ XML (для генерации) ----------
    def _build_interchange_header(self, root: ET.Element) -> None:
        hdr = ET.SubElement(root, "interchangeHeader")
        ET.SubElement(hdr, "sender").text = self.sender_gln
        ET.SubElement(hdr, "recipient").text = self.recipient_gln
        ET.SubElement(hdr, "documentType").text = self.DOCUMENT_TYPE
        ET.SubElement(hdr, "creationDateTime").text = self.creation_dt.isoformat()

    def _build_parties(self, doc: ET.Element) -> None:
        doc.append(self.seller.to_xml("seller"))
        doc.append(self.buyer.to_xml("buyer"))
        if self.invoicee.gln:
            doc.append(self.invoicee.to_xml("invoicee"))

    def _build_origin_order(self, doc: ET.Element) -> None:
        if self.origin_order_number:
            ET.SubElement(doc, "originOrder", {
                "number": self.origin_order_number,
                "date": self.origin_order_date,
            })

    def _build_contract(self, doc: ET.Element) -> None:
        if self.contract_number:
            ET.SubElement(doc, "contractIdentificator", {
                "number": self.contract_number,
                "date": self.contract_date,
            })

    def _build_line_items(self, doc: ET.Element) -> None:
        li_root = ET.SubElement(doc, "lineItems")
        ET.SubElement(li_root, "currencyISOCode").text = "RUB"
        for li in self.line_items:
            li_root.append(li.to_xml())
        for tag, val in self.calculate_totals().items():
            ET.SubElement(li_root, tag).text = f"{val:.2f}"

    # ---------- АБСТРАКТНЫЕ МЕТОДЫ ----------
    @abstractmethod
    def _build_document_body(self, root: ET.Element) -> None:
        """Собирает специфичный корень (order/orderResponse/...)."""
        ...

    @abstractmethod
    def _parse_document_body(self, root: ET.Element) -> None:
        """Читает специфичный корень из XML."""
        ...

    @abstractmethod
    def _make_line_item(self) -> LineItem:
        """Фабричный метод: создаёт строку нужного типа."""
        ...

    # ---------- ПУБЛИЧНЫЙ API ----------
    def to_xml_string(self) -> str:
        root = ET.Element("eDIMessage", {"id": self.message_id})
        self._build_interchange_header(root)
        self._build_document_body(root)
        ET.indent(root, space="  ")
        return ('<?xml version="1.0" encoding="utf-8"?>\n'
                + ET.tostring(root, encoding="unicode"))

    @classmethod
    def from_xml_string(cls, xml_str: str) -> "BaseEDIMessage":
        root = ET.fromstring(xml_str.lstrip("\ufeff"))
        msg = cls()
        msg.message_id = root.get("id", msg.message_id)

        hdr = root.find("interchangeHeader")
        if hdr is not None:
            msg.sender_gln = hdr.findtext("sender", "")
            msg.recipient_gln = hdr.findtext("recipient", "")
            dt_txt = hdr.findtext("creationDateTime", "")
            if dt_txt:
                try:
                    msg.creation_dt = datetime.fromisoformat(dt_txt.replace("Z", ""))
                except ValueError:
                    pass
        msg._parse_document_body(root)
        return msg

    # ---------- УТИЛИТЫ ПАРСИНГА (для наследников) ----------
    @staticmethod
    def _parse_parties(doc: ET.Element) -> dict:
        """
        Извлекает seller / buyer / invoicee из XML-узла документа.
        Возвращает словарь с тремя Organization.
        """
        return {
            "seller":   Organization.from_xml(doc.find("seller")),
            "buyer":    Organization.from_xml(doc.find("buyer")),
            "invoicee": Organization.from_xml(doc.find("invoicee")),
        }

    @staticmethod
    def _parse_delivery_info(doc: ET.Element) -> dict:
        """
        Извлекает блок deliveryInfo: даты и shipFrom/shipTo.
        Возвращает словарь со всеми возможными ключами.
        """
        di = doc.find("deliveryInfo")
        if di is None:
            return {
                "requested_delivery_dt": "",
                "estimated_delivery_dt": "",
                "shipping_dt": "",
                "actual_delivery_dt": "",
                "reception_dt": "",
                "ship_from": Organization(),
                "ship_to": Organization(),
            }
        return {
            "requested_delivery_dt": di.findtext("requestedDeliveryDateTime", ""),
            "estimated_delivery_dt": di.findtext("estimatedDeliveryDateTime", ""),
            "shipping_dt": di.findtext("shippingDateTime", ""),
            "actual_delivery_dt": di.findtext("actualDeliveryDateTime", ""),
            "reception_dt": di.findtext("receptionDateTime", ""),
            "ship_from": Organization.from_xml(di.find("shipFrom")),
            "ship_to": Organization.from_xml(di.find("shipTo")),
        }