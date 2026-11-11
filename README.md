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

Power-loss and restoration messages include a fixed progress bar anchored to the
schedule. Each square represents an hour, or the remaining partial hour at the
end of the interval. Half-hour intervals also use squares, not circles.
Only completed cells are colored: green when power was available for more than
40 minutes of an hour (20 minutes of a half hour), red otherwise. Future and
incomplete cells remain white; unknown past status is marked with a question mark.
The restoration bar covers the scheduled interval up to the next outage, including
any delayed restoration in red. When no next outage is known, it shows elapsed
time without predicting a cutoff.

The current power message is edited on the first monitoring check at or after
each Kyiv clock hour (:00), regardless of when power changed; only actual power transitions
publish new messages. A transition also finalizes the previous message with the
actual duration and end time instead of leaving a stale countdown.
Time beyond the captured schedule appears after `|`, with
the exact extra duration below it. Elapsed-only and extra-time bars end at the
current clock hour rounded down (09:13 becomes 09:00), while scheduled boundaries
such as 14:30 remain unchanged. Actual durations and transition times retain exact
minutes in the text; very long bars are capped at 24 squares
and an ellipsis. Kyiv dates are included when a bar crosses midnight.

The active Telegram message ID, its schedule window and observed power history
are saved locally in `power_message_state.json`, allowing hourly edits to resume
after a restart when the observed status still matches. Keep this file and
`offline_since.txt` on persistent storage. Schedule windows remain fixed for each
power message, even if DTEK later changes the schedule.
