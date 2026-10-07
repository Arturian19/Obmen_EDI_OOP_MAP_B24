"""
Конфигурация приложения.

Почему ООП: единая точка хранения настроек. Все модули получают их
через AppConfig, а не хардкодят пути по коду.

ВАЖНО: пути считаются от корня, а не от текущей папки запуска.
Иначе .exe, запущенный через ярлык, создаст пустую базу в «RANDOM» месте.
"""
import sys
from dataclasses import dataclass
from pathlib import Path

# Если программа собрана в .exe — берём папку рядом с .exe,
# иначе (python main.py) — корень проекта (edi/infrastructure/config.py -> ../..)
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass
class AppConfig:
    # --- база данных ---
    db_path: str = str(BASE_DIR / "edi.db")

    # --- файловый обмен ---
    inbox_dir: str = str(BASE_DIR / "exchange" / "inbox")
    outbox_dir: str = str(BASE_DIR / "exchange" / "outbox")
    processed_dir: str = str(BASE_DIR / "exchange" / "processed")

    # --- 1С (HTTP-сервис) ---
    onec_base_url: str = "http://localhost:8080/edi/hs"
    onec_user: str = "edi_user"
    onec_password: str = ""

    # --- своя сторона ---
    my_gln: str = "2865059663174"
    my_role: str = "supplier"      # 'supplier' | 'network'