import os
import threading

OUTAGE_MESSAGES = (
    "А бодай йому грець!",
    "Йосип босий, знову без світла!",
    "Трясця його матері!",
    "Дідька лисого, а не електрики!",
    "От халепа, світло знову шубовснуло!",
    "А щоб тим москалям добра не було!",
    "Хай йому грець, знову темрява!",
    "Сто чортів у хату москалям!",
    "От тобі й наука, май ліхтарика напохваті!",
    "Оце так халепа, бодай її качка копнула!",
    "А щоб їх качка копнула, тих москалів!",
    "Хай йому абищо, знову сидимо навпомацки!",
    "От дідько, саме вчасно!",
    "Знову клята русня світло забрала!",
    "Пішло все шкереберть — і світло за ним!",
    "Отакої! Світло пішло гуляти.",
    "Крути не крути — без світла не покрутиш!",
    "Ой лишенько, знову електрика навтьоки!",
    "Йосип босий!",
    "Ось тобі й маєш!",
    "Хай йому абищо!",
    "А щоб їх підняло та гепнуло!",
    "А щоб їм заціпило!",
    "Щоб їх лиха година взяла!",
)

OUTAGE_MESSAGE_INDEX_FILE = os.path.join(
    os.path.dirname(__file__),
    "outage_message_index.txt",
)

_index_lock = threading.Lock()


def next_outage_message(index_file: str = OUTAGE_MESSAGE_INDEX_FILE) -> str:
    with _index_lock:
        try:
            with open(index_file, encoding="utf-8") as f:
                index = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            index = 0

        message = OUTAGE_MESSAGES[index % len(OUTAGE_MESSAGES)]
        next_index = (index + 1) % len(OUTAGE_MESSAGES)
        temp_file = f"{index_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            f.write(str(next_index))
        os.replace(temp_file, index_file)
        return message
