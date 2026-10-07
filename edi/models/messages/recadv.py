"""
RECADV — уведомление о приёмке (от сети).
"""
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from edi.models.messages.base import BaseEDIMessage
from edi.models.line_item import LineItem


@dataclass
class LineItemRecadv(LineItem):
    ordered_quantity: float = 0.0
    despatched_quantity: float = 0.0
    delivered_quantity: float = 0.0
    accepted_quantity: float = 0.0

    @property
    def quantity(self) -> float:
        return self.accepted_quantity

    def to_xml(self) -> ET.Element:
        li = self._base_xml()
        ET.SubElement(li, "orderedQuantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.ordered_quantity:.3f}"
        ET.SubElement(li, "despatchedQuantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.despatched_quantity:.3f}"
        ET.SubElement(li, "deliveredQuantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.delivered_quantity:.3f}"
        ET.SubElement(li, "acceptedQuantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.accepted_quantity:.3f}"
        ET.SubElement(li, "netPrice").text = f"{self.net_price:.4f}"
        ET.SubElement(li, "netPriceWithVAT").text = f"{self.calc_price_with_vat():.4f}"
        ET.SubElement(li, "netAmount").text = f"{self.net_price * self.quantity:.4f}"
        ET.SubElement(li, "vATRate").text = self.vat_rate
        ET.SubElement(li, "vATAmount").text = f"{self.calc_vat_amount(self.quantity):.4f}"
        ET.SubElement(li, "amount").text = f"{self.calc_amount(self.quantity):.4f}"
        return li

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "LineItemRecadv":
        base = cls()._base_from_xml(elem)
        aq = elem.find("acceptedQuantity")
        return cls(
            **base,
            unit=aq.get("unitOfMeasure", "PCE") if aq is not None else "PCE",
            ordered_quantity=float(elem.findtext("orderedQuantity", "0") or 0),
            despatched_quantity=float(elem.findtext("despatchedQuantity", "0") or 0),
            delivered_quantity=float(elem.findtext("deliveredQuantity", "0") or 0),
            accepted_quantity=float(elem.findtext("acceptedQuantity", "0") or 0),
        )


class RecadvMessage(BaseEDIMessage):
    DOCUMENT_TYPE = "RECADV"

    def __init__(self):
        super().__init__()
        self.despatch_number = ""
        self.despatch_date = ""

    def _make_line_item(self) -> LineItem:
        return LineItemRecadv()

    def _build_document_body(self, root: ET.Element) -> None:
        doc = ET.SubElement(root, "receivingAdvice", {
            "number": self.document_number,
            "date": self.document_date,
        })
        self._build_origin_order(doc)
        self._build_contract(doc)
        if self.despatch_number:
            ET.SubElement(doc, "despatchIdentificator", {
                "number": self.despatch_number,
                "date": self.despatch_date,
            })
        self._build_parties(doc)

        di = ET.SubElement(doc, "deliveryInfo")
        if self.reception_dt:
            ET.SubElement(di, "receptionDateTime").text = self.reception_dt
        di.append(self.ship_from.to_xml("shipFrom"))
        di.append(self.ship_to.to_xml("shipTo"))

        self._build_line_items(doc)

    def _parse_document_body(self, root: ET.Element) -> None:
        doc = root.find("receivingAdvice")
        if doc is None:
            return
        self.document_number = doc.get("number", "")
        self.document_date = doc.get("date", "")

        o = doc.find("originOrder")
        if o is not None:
            self.origin_order_number = o.get("number", "")
            self.origin_order_date = o.get("date", "")

        c = doc.find("contractIdentificator")
        if c is not None:
            self.contract_number = c.get("number", "")
            self.contract_date = c.get("date", "")

        d = doc.find("despatchIdentificator")
        if d is not None:
            self.despatch_number = d.get("number", "")
            self.despatch_date = d.get("date", "")

        parties = self._parse_parties(doc)
        self.seller, self.buyer, self.invoicee = parties["seller"], parties["buyer"], parties["invoicee"]

        di = self._parse_delivery_info(doc)
        self.reception_dt = di.get("reception_dt", "")
        self.ship_from = di.get("ship_from")
        self.ship_to = di.get("ship_to")

        li_root = doc.find("lineItems")
        if li_root is not None:
            self.line_items = [LineItemRecadv.from_xml(li) for li in li_root.findall("lineItem")]