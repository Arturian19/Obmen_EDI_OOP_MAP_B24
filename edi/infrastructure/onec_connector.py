"""
Клиент HTTP-сервиса 1С УТ 11.5.

Почему ООП:
- Инкапсуляция: логика запросов, обработки ошибок и парсинга JSON
  спрятана внутри класса. UI просто вызывает get_orders() и получает
  готовые объекты OneCOrder.
- Абстракция: вызывающий код не знает, реальный это HTTP-запрос или
  заглушка (use_mock=True). Позже достаточно поставить use_mock=False
  и указать боевой URL — остальной проект не меняется.
- DTO-классы (OneCOrder, OneCOrderLine) — простые структуры данных,
  отделяющие «формат 1С» от «формата EDI-сообщения».
"""
import requests
from dataclasses import dataclass, field
from typing import List

from edi.models.organization import Organization, Address


# ============================================================
# DTO (Data Transfer Objects) — плоские структуры для обмена с 1С
# ============================================================

@dataclass
class OneCOrderLine:
    """Строка заказа поставщику, полученная из 1С."""
    gtin: str
    name: str
    quantity: float
    price: float
    vat_rate: str
    supplier_code: str = ""
    buyer_code: str = ""


@dataclass
class OneCOrder:
    """Заказ поставщику из 1С."""
    number: str
    date: str
    supplier: Organization
    buyer: Organization
    consignee: Organization
    lines: List[OneCOrderLine] = field(default_factory=list)


# ============================================================
# Основной коннектор
# ============================================================

class OneCConnector:
    """
    Клиент для получения данных из 1С через HTTP-сервис.

    use_mock=True  -> возвращает тестовые данные (отладка и защита курсовой)
    use_mock=False -> делает настоящие HTTP-запросы к base_url
    """

    def __init__(self, base_url: str, username: str = "",
                 password: str = "", use_mock: bool = True):
        self.base_url = base_url.rstrip("/")
        self.auth = (username, password) if username else None
        self.timeout = 30
        self.use_mock = use_mock

    # ---------- низкоуровневый запрос ----------
    def _get(self, path: str, params: dict = None) -> dict:
        if self.use_mock:
            return self._mock_get(path, params or {})

        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            resp = requests.get(url, params=params, auth=self.auth,
                                timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise ConnectionError(f"Ошибка запроса к 1С: {e}") from e

    # ---------- парсинг Organization из JSON 1С ----------
    @staticmethod
    def _parse_org(data: dict) -> Organization:
        addr = data.get("address", {}) or {}
        return Organization(
            gln=data.get("gln", ""),
            name=data.get("name", ""),
            inn=data.get("inn", ""),
            kpp=data.get("kpp", ""),
            address=Address(
                region_code=addr.get("region", ""),
                city=addr.get("city", ""),
                street=addr.get("street", ""),
                house=addr.get("house", ""),
            ),
        )

    # ==================================================
    # ЗАГЛУШКА: тестовые данные (3 заказа)
    # ==================================================
    def _mock_get(self, path: str, params: dict) -> dict:
        """Возвращает правдоподобные данные без обращения к 1С."""
        supplier = {
            "gln": "2865059663174",
            "name": "Тестовый поставщик Макс Артур",
            "inn": "5345177209",
            "kpp": "885685952",
            "address": {"region": "RU-KR"},
        }
        buyer = {
            "gln": "2622104526514",
            "name": "Тестовая сеть Макс Артур",
            "inn": "1215332600",
            "kpp": "067801090",
            "address": {"region": "RU-NVS", "city": "Новосибирск",
                        "street": "Ленина", "house": "12"},
        }

        if path == "orders":
            # ТРИ заказа, чтобы кнопка «Сформировать ORDERS» работала
            # больше одного раза (иначе второй клик даёт «уже отправлено»)
            items = []
            for i, (number, day, qty, price) in enumerate([
                ("ЧП00-000002", "02", 10.0, 66.67),
                ("ЧП00-000003", "03",  5.0, 120.0),
                ("ЧП00-000004", "04", 20.0, 45.50),
            ], start=1):
                items.append({
                    "number": number,
                    "date": f"2026-04-{day}",
                    "supplier": supplier,
                    "buyer": buyer,
                    "consignee": buyer,
                    "lines": [{
                        "gtin": "6787655434561",
                        "name": f"Тестовый товар {i}",
                        "quantity": qty,
                        "price": price,
                        "vat_rate": "20",
                        "supplier_code": f"00{i:02d}",
                        "buyer_code": f"00-0000029{i}",
                    }],
                })
            return {"items": items}

        # Остальные методы пока возвращают пустышку
        return {}

    # ==================================================
    # ПУБЛИЧНЫЕ МЕТОДЫ
    # ==================================================
    def get_orders(self, supplier_inn: str = "",
                   date_from: str = "", date_to: str = "") -> List[OneCOrder]:
        """
        Возвращает список заказов поставщику из 1С.
        supplier_inn -- фильтр по ИНН поставщика.
        date_from / date_to -- в формате 'YYYY-MM-DD'.
        """
        params = {}
        if supplier_inn:
            params["supplier_inn"] = supplier_inn
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        raw = self._get("orders", params)
        result: List[OneCOrder] = []
        for item in raw.get("items", []):
            lines = [
                OneCOrderLine(
                    gtin=line.get("gtin", ""),
                    name=line.get("name", ""),
                    quantity=float(line.get("quantity", 0)),
                    price=float(line.get("price", 0)),
                    vat_rate=str(line.get("vat_rate", "")),
                    supplier_code=line.get("supplier_code", ""),
                    buyer_code=line.get("buyer_code", ""),
                )
                for line in item.get("lines", [])
            ]
            result.append(OneCOrder(
                number=item["number"],
                date=item["date"],
                supplier=self._parse_org(item["supplier"]),
                buyer=self._parse_org(item["buyer"]),
                consignee=self._parse_org(item.get("consignee", item["buyer"])),
                lines=lines,
            ))
        return result

    def get_customer_order(self, order_number: str) -> dict:
        """ORDRSP: Заказ клиента из 1С по реквизиту 'Заказ по данным клиента'."""
        return self._get("customer-orders", {"number": order_number})

    def get_sales_invoice(self, despatch_number: str) -> dict:
        """DESADV: Реализация товаров и услуг по номеру накладной."""
        return self._get("sales-invoices", {"number": despatch_number})

    def get_receipt(self, despatch_number: str) -> dict:
        """RECADV: Поступление товаров и услуг по номеру DESADV."""
        return self._get("receipts", {"number": despatch_number})

    def get_invoice_document(self, order_number: str) -> dict:
        """INVOIC: счёт-фактура или реализация."""
        return self._get("invoices", {"number": order_number})