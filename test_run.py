"""
Скрипт для проверки парсинга всех 5 типов EDI-сообщений.
НЕ часть программы — используется только для отладки.
"""
from pathlib import Path
from edi.infrastructure.file_exchange import FileExchange

print("=" * 70)
print("Проверка парсинга XML из папки samples/")
print("=" * 70)

samples = Path("samples")
if not samples.exists():
    print("❌ Папка samples/ не найдена!")
    exit(1)

files = list(samples.glob("*.xml"))
if not files:
    print("❌ В папке samples/ нет XML-файлов!")
    exit(1)

print(f"Найдено файлов: {len(files)}\n")

ok_count = 0
err_count = 0

for xml_file in files:
    try:
        content = xml_file.read_text(encoding="utf-8")
        msg = FileExchange.parse_message(content)
        totals = msg.calculate_totals()

        print(f"✅ [OK] {xml_file.name}")
        print(f"    Тип сообщения:  {msg.DOCUMENT_TYPE}")
        print(f"    Номер документа: {msg.document_number}")
        print(f"    Заказ-основание: {msg.origin_order_number or '(нет)'}")
        print(f"    Поставщик:      {msg.seller.name} (GLN {msg.seller.gln})")
        print(f"    Покупатель:     {msg.buyer.name} (GLN {msg.buyer.gln})")
        print(f"    Позиций:        {len(msg.line_items)}")
        print(f"    Сумма без НДС:  {totals['totalSumExcludingTaxes']} ₽")
        print(f"    Сумма НДС:      {totals['totalVATAmount']} ₽")
        print(f"    Итого:          {totals['totalAmount']} ₽")
        print()
        ok_count += 1
    except Exception as e:
        print(f"❌ [ОШИБКА] {xml_file.name}")
        print(f"    Причина: {type(e).__name__}: {e}")
        print()
        err_count += 1

print("=" * 70)
print(f"ИТОГО: успешно {ok_count}, ошибок {err_count}")
print("=" * 70)