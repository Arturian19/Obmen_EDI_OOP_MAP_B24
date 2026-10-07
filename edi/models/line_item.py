"""
Базовый класс строки табличной части.

Почему ООП:
- Наследование: LineItemOrders, LineItemOrdrsp, LineItemDesadv,
  LineItemRecadv, LineItemInvoic переиспользуют общие поля
  (gtin, description, net_price, vat_rate) и расчёты НДС.
- Полиморфизм: каждый наследник знает, СВОЙ тег количества писать
  в XML (requestedQuantity / confirmedQuantity / despatchedQuantity
  / acceptedQuantity / quantity).
- Инкапсуляция: расчёты суммы и НДС спрятаны внутри класса —
  вызывающий код просто получает готовое число.
"""
from dataclasses import dataclass
import xml.etree.ElementTree as ET


@dataclass
class LineItem:
    gtin: str = ""
    buyer_code: str = ""
    supplier_code: str = ""
    description: str = ""
    unit: str = "PCE"
    net_price: float = 0.0
    vat_rate: str = "20"
    line_number: int = 0

    # ---------- вычисляемые поля ----------
    @property
    def vat_rate_percent(self) -> float:
        """Возвращает числовую ставку НДС. 'NOT_APPLICABLE'/'Без НДС' → 0."""
        if self.vat_rate in ("NOT_APPLICABLE", "Без НДС", "", None):
            return 0.0
        try:
            return float(str(self.vat_rate).replace("%", ""))
        except ValueError:
            return 0.0

    def calc_price_with_vat(self) -> float:
        """Цена с НДС за единицу."""
        return round(self.net_price * (1 + self.vat_rate_percent / 100), 4)

    def calc_vat_amount(self, quantity: float) -> float:
        """Сумма НДС на всё количество."""
        return round((self.calc_price_with_vat() - self.net_price) * quantity, 4)

    def calc_amount(self, quantity: float) -> float:
        """Итоговая сумма с НДС на всё количество."""
        return round(self.calc_price_with_vat() * quantity, 4)

    @property
    def quantity(self) -> float:
        """
        Количество, по которому считаются итоги.
        В базовом классе — 0.0. Наследники переопределяют
        это свойство, чтобы вернуть СВОЁ поле.
        """
        return 0.0

    # ---------- ОБЩИЕ БЛОКИ XML ----------
    def _base_xml(self) -> ET.Element:
        """
        Формирует <lineItem> с общими для всех сообщений тегами:
        gtin, internalBuyerCode, internalSupplierCode, description.
        """
        li = ET.Element("lineItem")
        ET.SubElement(li, "gtin").text = self.gtin
        ET.SubElement(li, "internalBuyerCode").text = self.buyer_code
        ET.SubElement(li, "internalSupplierCode").text = self.supplier_code
        ET.SubElement(li, "description").text = self.description
        return li

    def _base_from_xml(self, elem: ET.Element) -> dict:
        """
        Читает из <lineItem> общие поля и возвращает словарь,
        который можно передать в конструктор наследников:
            cls(**base, ...остальные_поля...)
        """
        return {
            "gtin": elem.findtext("gtin", ""),
            "buyer_code": elem.findtext("internalBuyerCode", ""),
            "supplier_code": elem.findtext("internalSupplierCode", ""),
            "description": elem.findtext("description", ""),
            "net_price": float(elem.findtext("netPrice", "0") or 0),
            "vat_rate": elem.findtext("vATRate", ""),
        }

    # ---------- АБСТРАКТНЫЙ ИНТЕРФЕЙС ----------
    def to_xml(self) -> ET.Element:
        """Наследники обязаны реализовать."""
        raise NotImplementedError

    @classmethod
    def from_xml(cls, elem: ET.Element) -> "LineItem":
        """Наследники обязаны реализовать."""
        raise NotImplementedError