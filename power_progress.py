from dataclasses import dataclass
from datetime import datetime
import math
import re

from utils import KYIV_TZ

MAX_PROGRESS_HOURS = 24


def hour_start(timestamp: float) -> float:
    return datetime.fromtimestamp(timestamp, KYIV_TZ).replace(
        minute=0, second=0, microsecond=0,
    ).timestamp()


def format_duration(seconds: float) -> str:
    minutes = max(0, int(seconds) // 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours} год {minutes} хв" if hours else f"{minutes} хв"


@dataclass
class PowerEvent:
    timestamp: float
    online: bool


@dataclass
class PowerMessage:
    online: bool
    since: float
    base_text: str
    start: float
    end: float | None
    events: list[PowerEvent]
    message_id: int | None = None
    updated_at: float = 0
    last_text: str = ""
    voltage: float | None = None
    outage_since: float | None = None

    @classmethod
    def from_dict(cls, data: object) -> "PowerMessage":
        if not isinstance(data, dict):
            raise ValueError("Invalid power message state")
        for name in ("since", "start", "updated_at"):
            value = data.get(name)
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"Invalid {name} in power message state")
        end = data.get("end")
        if end is not None and (
            type(end) not in (int, float) or not math.isfinite(end) or end <= data["start"]
        ):
            raise ValueError("Invalid end in power message state")
        if not isinstance(data.get("online"), bool):
            raise ValueError("Invalid online status in power message state")
        for name in ("base_text", "last_text"):
            if not isinstance(data.get(name), str):
                raise ValueError(f"Invalid {name} in power message state")
        voltage = data.get("voltage")
        if voltage is not None and (
            type(voltage) not in (int, float) or not math.isfinite(voltage)
        ):
            raise ValueError("Invalid voltage in power message state")
        outage_since = data.get("outage_since")
        if outage_since is not None and (
            type(outage_since) not in (int, float)
            or not math.isfinite(outage_since)
            or outage_since > data["since"]
        ):
            raise ValueError("Invalid outage start in power message state")
        base_text = data["base_text"]
        legacy_format = "voltage" not in data
        if legacy_format and data["online"]:
            match = re.search(r"Напруга в мережі: \*(\d+(?:\.\d+)?) Вольт\*", base_text)
            if match:
                voltage = float(match.group(1))
        if data["online"]:
            base_text = ""
        elif base_text.startswith("📣 "):
            base_text = base_text.partition("\n\n")[2]
            legacy_format = True
        message_id = data.get("message_id")
        if message_id is not None and (type(message_id) is not int or message_id <= 0):
            raise ValueError("Invalid message ID in power message state")
        raw_events = data.get("events")
        if not isinstance(raw_events, list) or not raw_events:
            raise ValueError("Missing power history in power message state")
        events = []
        for event in raw_events:
            if not isinstance(event, dict):
                raise ValueError("Invalid power history entry")
            timestamp = event.get("timestamp")
            online = event.get("online")
            if (
                type(timestamp) not in (int, float)
                or not math.isfinite(timestamp)
                or not isinstance(online, bool)
                or (events and timestamp < events[-1].timestamp)
            ):
                raise ValueError("Invalid power history entry")
            events.append(PowerEvent(timestamp, online))
        if data["online"] and "outage_since" not in data:
            outage_since = next((
                event.timestamp for event in reversed(events)
                if not event.online and event.timestamp <= data["since"]
            ), None)
            legacy_format = True
        return cls(
            online=data["online"],
            since=data["since"],
            base_text=base_text,
            start=data["start"],
            end=end,
            events=events,
            message_id=message_id,
            updated_at=0 if legacy_format else data["updated_at"],
            last_text=data["last_text"],
            voltage=voltage,
            outage_since=outage_since,
        )

    def _cell(self, start: float, end: float, now: float) -> str:
        if end > now:
            return "⬜"
        if start < self.events[0].timestamp:
            return "❔"
        online_seconds = 0.0
        for index, event in enumerate(self.events):
            next_timestamp = (
                self.events[index + 1].timestamp if index + 1 < len(self.events) else end
            )
            if event.online:
                online_seconds += max(0, min(end, next_timestamp) - max(start, event.timestamp))
        green = online_seconds > (end - start) * 2 / 3
        return "🟩" if green else "🟥"

    def _bar(self, start: float, end: float, now: float) -> str:
        hours, remainder = divmod(int(end - start), 3600)
        cells = [
            self._cell(start + hour * 3600, start + (hour + 1) * 3600, now)
            for hour in range(min(hours, MAX_PROGRESS_HOURS))
        ]
        if hours > MAX_PROGRESS_HOURS:
            cells.append("…")
        elif remainder:
            cells.append(self._cell(start + hours * 3600, end, now))
        return "".join(cells)

    def _clock(self, timestamp: float) -> str:
        value = datetime.fromtimestamp(timestamp, KYIV_TZ)
        start_date = datetime.fromtimestamp(self.start, KYIV_TZ).date()
        return value.strftime("%H:%M" if value.date() == start_date else "%d.%m %H:%M")

    def _elapsed_bar(self, start: float, now: float) -> str:
        return self._bar(start, max(start, now), now) or "…"

    def render(
        self, now: float, finished: bool = False,
        next_outage: tuple[datetime, datetime] | None = None,
    ) -> str:
        if self.online:
            today = datetime.fromtimestamp(now, KYIV_TZ).date()
            since = datetime.fromtimestamp(self.since, KYIV_TZ)
            since_text = since.strftime("%d.%m %H:%M")
            lines = [
                f"💡⚡ *Світло дали!* — *{since_text}*",
                (
                    f"🔌 Напруга в мережі: *{self.voltage:.1f} Вольт*"
                    if self.voltage is not None
                    else "🔌 Напруга на момент відновлення невідома."
                ),
                (
                    f"⏱ Світла не було: *{format_duration(self.since - self.outage_since)}*"
                    if self.outage_since is not None
                    else "⏱ Тривалість попереднього відключення невідома."
                ),
            ]
            if finished:
                return "\n".join(lines)
            elif next_outage is None:
                lines.extend(["", "⚠️ Наступне відключення поки невідоме."])
            else:
                start, end = next_outage
                active = start.timestamp() <= now < end.timestamp()
                start_text = start.strftime("%H:%M" if start.date() == today else "%d.%m %H:%M")
                end_text = end.strftime("%H:%M" if end.date() == start.date() else "%d.%m %H:%M")
                lines.extend([
                    "", (
                        "📅 Зараз триває період відключення за графіком:"
                        if active else "📅 Наступне відключення за графіком:"
                    ),
                    f"❌ *{start_text}–{end_text}*",
                ])
                if active:
                    lines.append("⚠️ Світло можуть вимкнути будь-якої миті.")
            return "\n".join(lines)
        lines = [self.base_text, ""]
        display_end = max(self.start, hour_start(now))
        if self.end is None:
            lines.extend([
                "*Зі світлом:*" if self.online else "*Без світла:*",
                f"*{self._clock(self.start)}* {self._elapsed_bar(self.start, display_end)} *{self._clock(display_end)}*",
            ])
        else:
            bar = f"*{self._clock(self.start)}* {self._bar(self.start, self.end, now)} *{self._clock(self.end)}*"
            if display_end > self.end:
                bar += f" | {self._elapsed_bar(self.end, display_end)} *{self._clock(display_end)}*"
            lines.extend(["*Графік:*", bar])
        lines.append("")
        if finished:
            label = "🔴 Світло зникло о" if self.online else "💡 Світло відновлено о"
            lines.append(f"{label} *{self._clock(now)}*.")
        elif self.end is None:
            lines.append(
                "⚠️ Наступне відключення поки невідоме."
                if self.online else "⚠️ Час відновлення невідомий."
            )
        elif now < self.end:
            label = "До наступного відключення" if self.online else "До відновлення за графіком"
            lines.append(f"⌛ {label}: *{format_duration(self.end - now)}*")
        elif now > self.end:
            label = "🟢 Екстра — зі світлом понад графік" if self.online else "⚠️ Екстра — понад графік"
            lines.append(f"{label}: *{format_duration(now - self.end)}*")
            if not self.online:
                lines.append("Час відновлення невідомий.")
        else:
            lines.append(
                "За графіком зараз має початися відключення."
                if self.online else "За графіком світло мають відновити зараз."
            )
        if self.events[0].timestamp > self.start:
            lines.append("❔ — немає даних про стан світла.")
        return "\n".join(lines)
