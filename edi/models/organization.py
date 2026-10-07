"""
Модуль описывает контрагента (Организацию) и его адрес.

Почему ООП:
- Инкапсуляция: логика парсинга и генерации XML лежит ВНУТРИ класса.
- Один класс переиспользуется для seller/buyer/invoicee/shipFrom/shipTo.
"""
from dataclasses import dataclass, field
import xml.etree.ElementTree as ET


@dataclass
class Address:
    region_code: str = ""
    city: str = ""
    street: str = ""
    house: str = ""

    def to_xml(self, parent: ET.Element) -> None:
        """Собирает <russianAddress> внутрь родителя."""
        addr = ET.SubElement(parent, "russianAddress")
        if self.region_code:
            ET.SubElement(addr, "regionISOCode").text = self.region_code
        if self.city:
            ET.SubElement(addr, "city").text = self.city
        if self.street:
            ET.SubElement(addr, "street").text = self.street
        if self.house:
            ET.SubElement(addr, "house").text = self.house

    @classmethod
    def from_xml(cls, elem: ET.Element | None) -> "Address":
        if elem is None:
            return cls()
        return cls(
            region_code=elem.findtext("regionISOCode", ""),
            city=elem.findtext("city", ""),
            street=elem.findtext("street", ""),
            house=elem.findtext("house", ""),
        )


@dataclass
class Organization:
    gln: str = ""
    name: str = ""
    inn: str = ""
    kpp: str = ""
    address: Address = field(default_factory=Address)

    def to_xml(self, tag_name: str) -> ET.Element:
        """
        Создаёт тег <seller>/<buyer>/<invoicee>/<shipFrom>/<shipTo>
        с вложенными <gln>, <organization> и <russianAddress>.
        """
        node = ET.Element(tag_name)
        ET.SubElement(node, "gln").text = self.gln

        if self.name or self.inn or self.kpp:
            org = ET.SubElement(node, "organization")
            ET.SubElement(org, "name").text = self.name
            ET.SubElement(org, "inn").text = self.inn
            ET.SubElement(org, "kpp").text = self.kpp

        self.address.to_xml(node)
        return node

    @classmethod
    def from_xml(cls, elem: ET.Element | None) -> "Organization":
        if elem is None:
            return cls()
        org = elem.find("organization")
        return cls(
            gln=elem.findtext("gln", ""),
            name=org.findtext("name", "") if org is not None else "",
            inn=org.findtext("inn", "") if org is not None else "",
            kpp=org.findtext("kpp", "") if org is not None else "",
            address=Address.from_xml(elem.find("russianAddress")),
        )

    def address_line(self) -> str:
        """Адрес одной строкой: «город, улица, дом».
        Нужен для колонки «Адрес доставки» в таблице сообщений."""
        a = self.address
        return ", ".join(p for p in (a.city, a.street, a.house) if p)

    def __str__(self) -> str:
        return f"{self.name} (ИНН {self.inn}/{self.kpp}, GLN {self.gln})"