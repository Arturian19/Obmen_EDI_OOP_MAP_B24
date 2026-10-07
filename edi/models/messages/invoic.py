"""
INVOIC — счёт-фактура / УПД (от поставщика).
"""
from dataclasses import dataclass
import xml.etree.ElementTree as ET

from edi.models.messages.base import BaseEDIMessage
from edi.models.line_item import LineItem


@dataclass
class LineItemInvoic(LineItem):
    quantity_val: float = 0.0

    @property
    def quantity(self) -> float:
        return self.quantity_val

    def to_xml(self) -> ET.Element:
        li = self._base_xml()
        ET.SubElement(li, "quantity",
                      {"unitOfMeasure": self.unit}).text = f"{self.quantity_val:.3f}"
        ET.SubElement(li, "netPrice").text = f"{self.net_price:.4f}"
        ET.SubElement(li, "netPriceWithVAT").text = f"{self.calc_price_with_vat():.4f}"
        ET.SubElement(li, "netAmount").text = f"{self.net_price * self.quantity:.4f}"
        ET.SubElement(li, "vATRate").text = self.vat_rate
        ET.SubElement(li, "vATAmount").text = f"{self.calc_vat_amount(self.quantity):.4f}"
        ET.SubElement(li, "amount").text = f"{self.calc_amount(self.quantity):.4f}"
        return li

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "LineItemInvoic":
        base = cls()._base_from_xml(elem)
        q = elem.find("quantity")
        return cls(
            **base,
            unit=q.get("unitOfMeasure", "PCE") if q is not None else "PCE",
            quantity_val=float(elem.findtext("quantity", "0") or 0),
        )


class InvoiceMessage(BaseEDIMessage):
    DOCUMENT_TYPE = "INVOIC"

    def __init__(self):
        super().__init__()
        self.utd_function = ""           # "DOP" или "SCHFDOP"
        self.invoice_type = "Original"
        self.order_response_number = ""
        self.order_response_date = ""
        self.despatch_number = ""
        self.despatch_date = ""
        self.delivery_note_number = ""
        self.delivery_note_date = ""

    def _make_line_item(self) -> LineItem:
        return LineItemInvoic()

    def _build_document_body(self, root: ET.Element) -> None:
        attrs = {
            "number": self.document_number,
            "date": self.document_date,
            "type": self.invoice_type,
        }
        if self.utd_function:
            attrs["utdFunction"] = self.utd_function

        doc = ET.SubElement(root, "invoice", attrs)
        self._build_origin_order(doc)
        self._build_contract(doc)
        if self.order_response_number:
            ET.SubElement(doc, "orderResponse", {
                "number": self.order_response_number,
                "date": self.order_response_date,
            })
        if self.despatch_number:
            ET.SubElement(doc, "despatchIdentificator", {
                "number": self.despatch_number,
                "date": self.despatch_date,
            })
        if self.delivery_note_number:
            ET.SubElement(doc, "deliveryNoteIdentificator", {
                "number": self.delivery_note_number,
                "date": self.delivery_note_date,
            })
        self._build_parties(doc)

        di = ET.SubElement(doc, "deliveryInfo")
        if self.actual_delivery_dt:
            ET.SubElement(di, "actualDeliveryDateTime").text = self.actual_delivery_dt
        di.append(self.ship_from.to_xml("shipFrom"))
        di.append(self.ship_to.to_xml("shipTo"))

        self._build_line_items(doc)

    def _parse_document_body(self, root: ET.Element) -> None:
        doc = root.find("invoice")
        if doc is None:
            return
        self.document_number = doc.get("number", "")
        self.document_date = doc.get("date", "")
        self.invoice_type = doc.get("type", "Original")
        self.utd_function = doc.get("utdFunction", "")

        o = doc.find("originOrder")
        if o is not None:
            self.origin_order_number = o.get("number", "")
            self.origin_order_date = o.get("date", "")

        c = doc.find("contractIdentificator")
        if c is not None:
            self.contract_number = c.get("number", "")
            self.contract_date = c.get("date", "")

        r = doc.find("orderResponse")
        if r is not None:
            self.order_response_number = r.get("number", "")
            self.order_response_date = r.get("date", "")

        d = doc.find("despatchIdentificator")
        if d is not None:
            self.despatch_number = d.get("number", "")
            self.despatch_date = d.get("date", "")

        dn = doc.find("deliveryNoteIdentificator")
        if dn is not None:
            self.delivery_note_number = dn.get("number", "")
            self.delivery_note_date = dn.get("date", "")

        parties = self._parse_parties(doc)
        self.seller, self.buyer, self.invoicee = parties["seller"], parties["buyer"], parties["invoicee"]

        di = self._parse_delivery_info(doc)
        self.actual_delivery_dt = di.get("actual_delivery_dt", "")
        self.ship_from = di.get("ship_from")
        self.ship_to = di.get("ship_to")

        li_root = doc.find("lineItems")
        if li_root is not None:
            self.line_items = [LineItemInvoic.from_xml(li) for li in li_root.findall("lineItem")]