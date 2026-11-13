# OlenivkaSvitloBot

Create .env file with such content:

```env
TUYA_ACCESS_ID=
TUYA_ACCESS_SECRET=
TUYA_BASE_URL=https://openapi.tuyaeu.com
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
ELECTRICITY_DEVICE_ID=
TEMPERATURE_DEVICE_ID=
MONITOR_INTERVAL=15

DTEK_CITY=Бориспіль
DTEK_STREET=Шевченка
DTEK_HOUSE_NUM=1
SCHEDULE_MONITOR_INTERVAL=3600
```

Schedule notifications are sent for actual changes to today's schedule and for
new or changed schedules for tomorrow. Moving yesterday's unchanged tomorrow
schedule into today's section does not send a duplicate notification, even when
the tomorrow section disappears. The cached schedule still updates normally.

Restoration messages keep three fixed lines: "Світло дали!" with the restoration
date and time, voltage measured at restoration, and the previous outage duration.
These lines do not change during hourly updates or when power is lost again.
Unknown previous outage duration is explicitly identified, not reported as zero.
They have no progress bar, continuous power duration, countdown, or extra-time text.
The next outage is selected from the latest cached schedule on every monitoring
check, skipping finished intervals. During an active scheduled outage, the message
shows that interval and warns that power may be cut at any moment, even if it is
still available. Schedule changes and the start of an outage interval update the
same message without waiting for the next hour or fetching DTEK again.
Dates distinguish tomorrow's outages and power restored on previous days.
If neither an active nor a future interval is known, the message explicitly says so.

Power-loss messages include a fixed progress bar anchored to the
schedule. Each square represents an hour, or the remaining partial hour at the
end of the interval. Half-hour intervals also use squares, not circles.
Only completed cells are colored: green when power was available for more than
40 minutes of an hour (20 minutes of a half hour), red otherwise. Future and
incomplete cells remain white; unknown past status is marked with a question mark.
When the restoration time is unknown, the bar shows elapsed time without
predicting a cutoff. Outage alerts contain only status and schedule information;
there are no rotating humorous phrases or rotation state.

The current power message is edited on the first monitoring check at or after
each Kyiv clock hour (:00), regardless of when power changed; only actual power transitions
publish new messages. A transition finalizes the previous outage message with the
restoration time instead of leaving a stale countdown. Restoration messages retain
their original three lines, with the obsolete schedule section removed.
There are no standalone "Без світла" or "Зі світлом" duration lines below the bar.
Time beyond the captured schedule appears after `|`, with
the exact extra duration below it. Elapsed-only and extra-time bars end at the
current clock hour rounded down (09:13 becomes 09:00), while scheduled boundaries
such as 14:30 remain unchanged. Actual durations and transition times retain exact
minutes in the text; very long bars are capped at 24 squares
and an ellipsis. Kyiv dates are included when a bar crosses midnight.

The active Telegram message ID, its schedule window and observed power history
are saved locally in `power_message_state.json`, allowing hourly edits to resume
after a restart when the observed status still matches. Keep this file and
`offline_since.txt` on persistent storage. Progress-bar windows remain fixed for
power-loss messages; restoration messages always use the current cached schedule.
The previous outage start is also saved so its duration survives restarts and
power-history pruning. Existing saved restoration messages recover it from
observed history when available.
Existing saved messages migrate to the fixed restoration format (or lose their
old phrase prefix for outage messages) on the first check after a restart.
