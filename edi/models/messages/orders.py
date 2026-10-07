"""
ORDERS — заказ от торговой сети поставщику.
"""
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from edi.models.messages.base import BaseEDIMessage
from edi.models.line_item import LineItem
from edi.models.organization import Organization


@dataclass
class LineItemOrders(LineItem):
    requested_quantity: float = 0.0

    @property
    def quantity(self) -> float:
        return self.requested_quantity

    def to_xml(self) -> ET.Element:
        li = self._base_xml()
        ET.SubElement(li, "requestedQuantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.requested_quantity:.3f}"
        ET.SubElement(li, "netPrice").text = f"{self.net_price:.4f}"
        ET.SubElement(li, "vATRate").text = self.vat_rate
        return li

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "LineItemOrders":
        base = cls()._base_from_xml(elem)
        q = elem.find("requestedQuantity")
        return cls(
            **base,
            unit=q.get("unitOfMeasure", "PCE") if q is not None else "PCE",
            requested_quantity=float(elem.findtext("requestedQuantity", "0") or 0),
        )


class OrdersMessage(BaseEDIMessage):
    DOCUMENT_TYPE = "ORDERS"

    def _make_line_item(self) -> LineItem:
        return LineItemOrders()

    def _build_document_body(self, root: ET.Element) -> None:
        order = ET.SubElement(root, "order", {
            "number": self.document_number,
            "date": self.document_date,
        })
        self._build_contract(order)
        self._build_parties(order)

        di = ET.SubElement(order, "deliveryInfo")
        if self.requested_delivery_dt:
            ET.SubElement(di, "requestedDeliveryDateTime").text = self.requested_delivery_dt
        di.append(self.ship_from.to_xml("shipFrom"))
        di.append(self.ship_to.to_xml("shipTo"))

        self._build_line_items(order)

    def _parse_document_body(self, root: ET.Element) -> None:
        order = root.find("order")
        if order is None:
            return
        self.document_number = order.get("number", "")
        self.document_date = order.get("date", "")

        c = order.find("contractIdentificator")
        if c is not None:
            self.contract_number = c.get("number", "")
            self.contract_date = c.get("date", "")

        parties = self._parse_parties(order)
        self.seller, self.buyer, self.invoicee = parties["seller"], parties["buyer"], parties["invoicee"]

        di = self._parse_delivery_info(order)
        self.requested_delivery_dt = di.get("requested_delivery_dt", "")
        self.ship_from = di.get("ship_from", Organization())
        self.ship_to = di.get("ship_to", Organization())

        li_root = order.find("lineItems")
        if li_root is not None:
            self.line_items = [LineItemOrders.from_xml(li) for li in li_root.findall("lineItem")]