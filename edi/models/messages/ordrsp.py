"""
ORDRSP — подтверждение заказа от поставщика.
"""
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from edi.models.messages.base import BaseEDIMessage
from edi.models.line_item import LineItem


@dataclass
class LineItemOrdrsp(LineItem):
    ordered_quantity: float = 0.0
    confirmed_quantity: float = 0.0
    status: str = ""

    @property
    def quantity(self) -> float:
        return self.confirmed_quantity

    def to_xml(self) -> ET.Element:
        li = self._base_xml()
        if self.status:
            li.set("status", self.status)
        ET.SubElement(li, "orderedQuantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.ordered_quantity:.3f}"
        ET.SubElement(li, "confirmedQuantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.confirmed_quantity:.3f}"
        ET.SubElement(li, "netPrice").text = f"{self.net_price:.4f}"
        ET.SubElement(li, "netPriceWithVAT").text = f"{self.calc_price_with_vat():.4f}"
        ET.SubElement(li, "netAmount").text = f"{self.net_price * self.quantity:.4f}"
        ET.SubElement(li, "vATRate").text = self.vat_rate
        ET.SubElement(li, "vATAmount").text = f"{self.calc_vat_amount(self.quantity):.4f}"
        ET.SubElement(li, "amount").text = f"{self.calc_amount(self.quantity):.4f}"
        return li

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "LineItemOrdrsp":
        base = cls()._base_from_xml(elem)
        oq = elem.find("orderedQuantity")
        cq = elem.find("confirmedQuantity")
        return cls(
            **base,
            unit=(cq or oq).get("unitOfMeasure", "PCE") if (cq or oq) is not None else "PCE",
            ordered_quantity=float(elem.findtext("orderedQuantity", "0") or 0),
            confirmed_quantity=float(elem.findtext("confirmedQuantity", "0") or 0),
            status=elem.get("status", ""),
        )


class OrdrspMessage(BaseEDIMessage):
    DOCUMENT_TYPE = "ORDRSP"

    def __init__(self):
        super().__init__()
        self.status = ""  # Accepted / Changed / Rejected

    def _make_line_item(self) -> LineItem:
        return LineItemOrdrsp()

    def _build_document_body(self, root: ET.Element) -> None:
        attrs = {"number": self.document_number, "date": self.document_date}
        if self.status:
            attrs["status"] = self.status
        doc = ET.SubElement(root, "orderResponse", attrs)
        self._build_origin_order(doc)
        self._build_parties(doc)

        di = ET.SubElement(doc, "deliveryInfo")
        if self.requested_delivery_dt:
            ET.SubElement(di, "orderedDeliveryDateTime").text = self.requested_delivery_dt
        if self.estimated_delivery_dt:
            ET.SubElement(di, "estimatedDeliveryDateTime").text = self.estimated_delivery_dt
        di.append(self.ship_from.to_xml("shipFrom"))
        di.append(self.ship_to.to_xml("shipTo"))

        self._build_line_items(doc)

    def _parse_document_body(self, root: ET.Element) -> None:
        doc = root.find("orderResponse")
        if doc is None:
            return
        self.document_number = doc.get("number", "")
        self.document_date = doc.get("date", "")
        self.status = doc.get("status", "")

        o = doc.find("originOrder")
        if o is not None:
            self.origin_order_number = o.get("number", "")
            self.origin_order_date = o.get("date", "")

        parties = self._parse_parties(doc)
        self.seller, self.buyer, self.invoicee = parties["seller"], parties["buyer"], parties["invoicee"]

        di = self._parse_delivery_info(doc)
        self.requested_delivery_dt = di.get("requested_delivery_dt", "")
        self.estimated_delivery_dt = di.get("estimated_delivery_dt", "")
        self.ship_from = di.get("ship_from")
        self.ship_to = di.get("ship_to")

        li_root = doc.find("lineItems")
        if li_root is not None:
            self.line_items = [LineItemOrdrsp.from_xml(li) for li in li_root.findall("lineItem")]