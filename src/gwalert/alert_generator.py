import json
import time
from typing import NamedTuple

import dotenv
import pendulum
import requests
from pydantic import BaseModel
from sqlalchemy import asc, or_

from gwalert.config import DEFAULT_ENV_FILE, Settings
from gwalert.db import configure, get_db
from gwalert.models import MessageSql
from gwalert.google_sheet_reader import read_google_sheet, schedule_json_path
from gwalert.types import Glitch, LayoutLite, Report, SnapshotSpaceheat

SIMULATING = False
SIMULATING_REFERENCE_TIME = pendulum.parse('2026-06-10T00:21:00-04:00')
if SIMULATING:
    print(f"SIMULATING RUN AT {SIMULATING_REFERENCE_TIME}")


class ParsedLayoutLite(NamedTuple):
    house_alias: str
    message_persisted_ms: int
    layout: LayoutLite


class ParsedReport(NamedTuple):
    house_alias: str
    report: Report


class ParsedGlitch(NamedTuple):
    house_alias: str
    message_persisted_ms: int
    glitch: Glitch


class ParsedSnapshotSpaceheat(NamedTuple):
    message_persisted_ms: int
    snapshot: SnapshotSpaceheat


class AlertSend(BaseModel):
    recipients: list[str]
    sent_at: int


class Alert(BaseModel):
    count: int = 1
    sends: list[AlertSend] = []
    message: str
    house_alias: str
    alert_alias: str


class AlertGenerator:
    def __init__(self):
        self.settings = Settings(_env_file=dotenv.find_dotenv(DEFAULT_ENV_FILE))
        configure(self.settings)
        self.timezone_str = 'America/New_York'
        self.ignored_house_aliases = ['moss', 'orange', 'spruce'] # TODO: put this in the .env file
        self.max_time_no_data = 10*60 #TODO nyquist
        self.main_loop_seconds = 5*60
        self.hours_back = 2
        self.max_setpoint_violation_f = 2
        self.min_dist_pump_w = 2
        self.min_store_pump_w = 5
        self.min_dist_pump_gpm = 0.5
        self.min_store_pump_gpm = 0.5
        self.min_hp_kw = 1
        self.on_peak_hours = [7,8,9,10,11,16,17,18,19]
        self.whitewire_threshold_watts = {'beech': 100, 'default': 20, 'elm': 0.9}
        self.simulated_reference_time = SIMULATING_REFERENCE_TIME
        self.critical_zones_by_house = {}
        self.houses_in_standby = []
        self.reports: list[ParsedReport] = []
        self.layout_lites: list[ParsedLayoutLite] = []
        self.selected_house_aliases: list[str] = []
        self.data = {}
        self.relays = {}
        self.spruce_snapshots: list[ParsedSnapshotSpaceheat] = []
        self.alert_status = {}
        self.active_telegram_alerts: dict[str, Alert] = {}
        self.telegram_update_offset = 0
        self.max_alert_count = 6
        self.main()

    def send_alert(self, message, house_alias, alert_alias):
        read_google_sheet()
        print(f"[ALERT] {message}")
        full_alias = f"{pendulum.now(tz=self.timezone_str).format('YYYY-MM-DD')}-{house_alias}-{alert_alias}"

        if full_alias not in self.active_telegram_alerts:
            self.active_telegram_alerts[full_alias] = Alert(
                message=message,
                house_alias=house_alias,
                alert_alias=alert_alias,
            )
        elif self.active_telegram_alerts[full_alias].count < self.max_alert_count:
            self.active_telegram_alerts[full_alias].count += 1
        else:
            return

        count = self.active_telegram_alerts[full_alias].count
        recipients = self.get_alert_recipients(alert_count=count)
        if not recipients:
            print(f"Skipping telegram alert {full_alias}: no recipients resolved")
            return

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token.get_secret_value()}/sendMessage"
        sent_to: list[str] = []
        for chat_id in recipients:
            response = requests.post(url, json={"chat_id": chat_id, "text": message})
            if response.status_code == 200:
                sent_to.append(chat_id)
            else:
                print(
                    f"Failed to send telegram alert to {chat_id}: "
                    f"{response.status_code}, {response.text}"
                )

        if sent_to:
            self.active_telegram_alerts[full_alias].sends.append(
                AlertSend(recipients=sent_to, sent_at=int(time.time()))
            )
            print(f"Telegram alert {full_alias} sent to {len(sent_to)} recipient(s)")

    def get_alert_recipients(self, alert_count: int) -> list[str]:
        alert_time = pendulum.now(tz=self.timezone_str)

        schedule_path = schedule_json_path()
        with schedule_path.open(encoding="utf-8") as schedule_file:
            oncall_data = json.load(schedule_file)
        schedule = oncall_data.get("schedule", {})
        contacts = oncall_data.get("contacts", {})

        if alert_count > 3:
            recipients = [str(chat_id) for chat_id in contacts.values() if chat_id]
            print(f"Escalation: sending to all {len(recipients)} contact(s)")
            return recipients

        names = schedule.get(str(alert_time.weekday()), {}).get(str(alert_time.hour), [])

        if not names:
            return []

        recipients: list[str] = []
        for name in names:
            chat_id = contacts.get(name, "")
            if chat_id:
                recipients.append(str(chat_id))
            else:
                print(f"No Telegram chat ID configured for {name}")

        print(f"On-call: {', '.join(names)} -> {len(recipients)} recipient(s)")
        return recipients

    def check_telegram_alerts(self):
        print(f"\nChecking active alerts...")
        print(f"There are {len(self.active_telegram_alerts)} active alerts.")
        if not self.active_telegram_alerts:
            return            

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token.get_secret_value()}/getUpdates"
        response = requests.get(url, params={"offset": self.telegram_update_offset, "timeout": 0})
        replies_by_chat: dict[str, list[int]] = {}
        if response.status_code == 200:
            for update in response.json().get("result", []):
                self.telegram_update_offset = update["update_id"] + 1
                msg = update.get("message") or update.get("edited_message")
                if not msg or msg.get("from", {}).get("is_bot"):
                    continue
                chat_id = str(msg["chat"]["id"])
                replies_by_chat.setdefault(chat_id, []).append(msg["date"])

        for full_alert_alias, alert in list(self.active_telegram_alerts.items()):
            acknowledged = False
            for sent in alert.sends:
                for recipient in sent.recipients:
                    reply_times = replies_by_chat.get(str(recipient), [])
                    if any(t >= sent.sent_at for t in reply_times):
                        acknowledged = True
                        break
                if acknowledged:
                    break

            if acknowledged:
                print(f"Telegram alert {full_alert_alias} acknowledged")
                self.active_telegram_alerts.pop(full_alert_alias)
            else:
                self.send_alert(
                    alert.message,
                    alert.house_alias,
                    alert.alert_alias,
                )
        
    def unix_ms_to_date(self, time_ms):
        return pendulum.from_timestamp(time_ms/1000, tz=self.timezone_str).replace(microsecond=0)

    def reference_now(self) -> pendulum.DateTime:
        """Datetime used anywhere we meant 'now' for alert windows (frozen when SIMULATING)."""
        if SIMULATING:
            return self.simulated_reference_time
        return pendulum.now(tz=self.timezone_str)

    def reference_epoch(self) -> float:
        """Unix seconds aligned with ``reference_now`` (replacement for ``time.time()`` in alert logic)."""
        if SIMULATING:
            return float(self.simulated_reference_time.timestamp())
        return time.time()

    def _parse_layout_lite_message(
        self, message: MessageSql
    ) -> ParsedLayoutLite | None:
        try:
            layout = LayoutLite.from_dict(message.payload)
        except ValueError as e:
            print(
                f"Skipping invalid layout.lite from {message.from_alias}: {e}"
            )
            return None
        return ParsedLayoutLite(
            house_alias=message.from_alias.split(".")[-2],
            message_persisted_ms=message.message_persisted_ms,
            layout=layout,
        )

    def _parse_report_message(self, message: MessageSql) -> ParsedReport | None:
        try:
            report = Report.from_dict(message.payload)
        except ValueError as e:
            print(f"Skipping invalid report from {message.from_alias}: {e}")
            return None
        return ParsedReport(
            house_alias=message.from_alias.split(".")[-2],
            report=report,
        )

    def _house_alias_from_g_node_alias(self, source: str) -> str | None:
        if ".scada" in source and source.split(".")[-1] in ["scada", "s2"]:
            return source.split(".scada")[0].split(".")[-1]
        if len(source.split(".")) > 1:
            return source.split(".")[-1]
        print(f"Unknown source: {source}")
        return None

    def _parse_glitch_message(self, message: MessageSql) -> ParsedGlitch | None:
        try:
            glitch = Glitch.from_dict(message.payload)
        except ValueError as e:
            print(f"Skipping invalid glitch from {message.from_alias}: {e}")
            return None
        house_alias = self._house_alias_from_g_node_alias(glitch.from_g_node_alias)
        if house_alias is None:
            return None
        return ParsedGlitch(
            house_alias=house_alias,
            message_persisted_ms=message.message_persisted_ms,
            glitch=glitch,
        )

    def _parse_snapshot_spaceheat_message(
        self, message: MessageSql
    ) -> ParsedSnapshotSpaceheat | None:
        try:
            snapshot = SnapshotSpaceheat.from_dict(message.payload)
        except ValueError as e:
            print(
                f"Skipping invalid snapshot.spaceheat from {message.from_alias}: {e}"
            )
            return None
        return ParsedSnapshotSpaceheat(
            message_persisted_ms=message.message_persisted_ms,
            snapshot=snapshot,
        )

    def get_data_from_journaldb(self):
        print("\nFinding data from journaldb...")
        time_now = self.reference_now()
        try:
            with next(get_db()) as session:
                start_ms = time_now.add(hours=-self.hours_back).timestamp() * 1000
                end_ms = time_now.timestamp() * 1000
                sql_messages = (
                    session.query(MessageSql).filter(
                        or_(
                            MessageSql.message_type_name == "report",
                            MessageSql.message_type_name == "layout.lite",
                        ),
                        MessageSql.message_persisted_ms >= start_ms,
                        MessageSql.message_persisted_ms <= end_ms,
                        ).order_by(asc(MessageSql.message_persisted_ms)).all()
                    )
                if not sql_messages:
                    raise Exception("No messages found.")
        except Exception as e:
            print(f"An error occured while getting data from journaldb: {e}")
            return
        
        report_messages = [
            m for m in sql_messages if m.message_type_name == "report"
        ]
        self.reports = [
            parsed
            for m in report_messages
            if (parsed := self._parse_report_message(m)) is not None
        ]
        layout_lite_messages = [
            m for m in sql_messages if m.message_type_name == "layout.lite"
        ]
        self.layout_lites = [
            parsed
            for m in layout_lite_messages
            if (parsed := self._parse_layout_lite_message(m)) is not None
        ]
        print(
            f"Found {len(self.reports)} reports "
            f"({len(report_messages) - len(self.reports)} skipped) and "
            f"{len(self.layout_lites)} layout lites "
            f"({len(layout_lite_messages) - len(self.layout_lites)} skipped)"
        )
        for parsed in self.layout_lites:
            self.critical_zones_by_house[parsed.house_alias] = {
                "known": True,
                "list": parsed.layout.critical_zone_list,
            }
            if (
                parsed.layout.system_mode == "Standby"
                and parsed.house_alias not in self.houses_in_standby
            ):
                self.houses_in_standby.append(parsed.house_alias)
                print(f"Adding {parsed.house_alias} to the list of houses in standby")
            elif (
                parsed.layout.system_mode != "Standby"
                and parsed.house_alias in self.houses_in_standby
            ):
                self.houses_in_standby.remove(parsed.house_alias)
                print(f"Removing {parsed.house_alias} from the list of houses in standby")
        all_house_aliases = list({x.house_alias for x in self.reports})
        self.selected_house_aliases = [x for x in all_house_aliases if x not in self.ignored_house_aliases]
        print(f"Selected house aliases: {self.selected_house_aliases}")

        for house_alias in all_house_aliases:
            self.data[house_alias] = {}
            self.relays[house_alias] = {}
            if house_alias not in self.alert_status:
                self.alert_status[house_alias] = {}
            if house_alias not in self.critical_zones_by_house:
                self.critical_zones_by_house[house_alias] = {'known': False, 'list': []}

            if house_alias not in self.selected_house_aliases:
                print(f"- {house_alias}: House is not in the selected aliases")
                continue

            for parsed in [r for r in self.reports if r.house_alias == house_alias]:
                for channel in parsed.report.channel_reading_list:
                    channel_name = channel.channel_name
                    if channel_name not in self.data[house_alias]:
                        self.data[house_alias][channel_name] = {}
                        self.data[house_alias][channel_name]['times'] = []
                        self.data[house_alias][channel_name]['values'] = []
                    self.data[house_alias][channel_name]["times"].extend(
                        channel.scada_read_time_unix_ms_list
                    )
                    self.data[house_alias][channel_name]["values"].extend(
                        channel.value_list
                    )

                for state in parsed.report.state_list:
                    if 'relay' in state.machine_handle:
                        relay_name = state.machine_handle.split('.')[-1]
                        if relay_name not in self.relays[house_alias]:
                            self.relays[house_alias][relay_name] = {}
                        if state.machine_handle not in self.relays[house_alias][relay_name]:
                            self.relays[house_alias][relay_name][state.machine_handle] = {}
                            self.relays[house_alias][relay_name][state.machine_handle]["times"] = []
                            self.relays[house_alias][relay_name][state.machine_handle]["values"] = []
                        self.relays[house_alias][relay_name][state.machine_handle]["times"].extend(
                            state.unix_ms_list
                        )
                        self.relays[house_alias][relay_name][state.machine_handle]["values"].extend(
                            state.state_list
                        )

            for channel in self.data[house_alias]:
                sorted_times_values = sorted(zip(self.data[house_alias][channel]["times"], self.data[house_alias][channel]["values"]))
                sorted_times, sorted_values = zip(*sorted_times_values)
                self.data[house_alias][channel]["times"] = list(sorted_times)
                self.data[house_alias][channel]["values"] = list(sorted_values)

            for relay in self.relays[house_alias]:
                for relay_boss in self.relays[house_alias][relay]:
                    sorted_times_values = sorted(zip(self.relays[house_alias][relay][relay_boss]["times"], 
                                                     self.relays[house_alias][relay][relay_boss]["values"]))
                    sorted_times, sorted_values = zip(*sorted_times_values)
                    self.relays[house_alias][relay][relay_boss]["times"] = list(sorted_times)
                    self.relays[house_alias][relay][relay_boss]["values"] = list(sorted_values)

            if self.data[house_alias]:
                print(f"- {house_alias}: Found data")
            else:
                print(f"- {house_alias}: Did not find any data")

    def get_data_from_journaldb_spruce(self):
        print("\nFinding Spruce data from journaldb...")
        time_now = self.reference_now()
        self.spruce_snapshots = []
        try:
            with next(get_db()) as session:
                start_ms = time_now.add(minutes=-10).timestamp() * 1000
                end_ms = time_now.timestamp() * 1000
                snapshot_messages = (
                    session.query(MessageSql).filter(
                        MessageSql.message_type_name == "snapshot.spaceheat",
                        MessageSql.from_alias == f"hw1.isone.me.versant.keene.spruce.scada",
                        MessageSql.message_persisted_ms >= start_ms,
                        MessageSql.message_persisted_ms <= end_ms,
                    ).order_by(asc(MessageSql.message_persisted_ms)).all()
                )
                self.spruce_snapshots = [
                    parsed
                    for m in snapshot_messages
                    if (parsed := self._parse_snapshot_spaceheat_message(m))
                    is not None
                ]
                print(
                    f"Found {len(self.spruce_snapshots)} snapshots "
                    f"({len(snapshot_messages) - len(self.spruce_snapshots)} skipped)"
                )
        except Exception as e:
            print(f"An error occured while getting data from journaldb: {e}")
            return

    def check_for_glitches(self):
        alert_alias = "critical_glitch"
        print("\nChecking for glitches...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = {}

            expired_glitches = []
            for active_critical_glitch in self.alert_status[house_alias][alert_alias]:
                if self.reference_epoch() - self.alert_status[house_alias][alert_alias][active_critical_glitch] > self.hours_back*60*60:
                    expired_glitches.append(active_critical_glitch)
            for active_critical_glitch in expired_glitches:
                self.alert_status[house_alias][alert_alias].pop(active_critical_glitch)

        try:
            message_aliases = []
            for house_alias in self.selected_house_aliases:
                message_aliases.extend([
                    f"hw1.isone.me.versant.keene.{house_alias}",
                    f"hw1.isone.me.versant.keene.{house_alias}.scada",
                    f"hw1.isone.me.versant.keene.{house_alias}.scada.s2",
                ])
            with next(get_db()) as session:
                start_ms = self.reference_now().add(hours=-self.hours_back).timestamp() * 1000
                glitch_messages = (
                    session.query(MessageSql).filter(
                        MessageSql.message_type_name == "glitch",
                        MessageSql.from_alias.in_(message_aliases),
                        MessageSql.message_persisted_ms >= start_ms,
                        ).order_by(asc(MessageSql.message_persisted_ms)).all()
                    )
                parsed_glitches = [
                    parsed
                    for m in glitch_messages
                    if (parsed := self._parse_glitch_message(m)) is not None
                ]
                if not parsed_glitches:
                    print("No glitches found")
                else:
                    critical_count = sum(
                        1
                        for p in parsed_glitches
                        if p.glitch.type == "Critical"
                    )
                    print(
                        f"Found {len(parsed_glitches)} glitches "
                        f"({len(glitch_messages) - len(parsed_glitches)} skipped), "
                        f"of which {critical_count} are critical"
                    )
                for parsed in parsed_glitches:
                    house_alias = parsed.house_alias
                    if house_alias not in self.alert_status:
                        continue
                    summary = parsed.glitch.summary
                    time_received = int(parsed.message_persisted_ms / 1000)
                    unique_id = f"{house_alias}-{summary}"
                    if (
                        parsed.glitch.type == "Critical"
                        and unique_id
                        not in self.alert_status[house_alias][alert_alias]
                    ):
                        self.send_alert(
                            f"{house_alias} - critical glitch: {summary}",
                            house_alias,
                            alert_alias,
                        )
                        self.alert_status[house_alias][alert_alias][
                            unique_id
                        ] = time_received
        except Exception as e:
            print(f"An error occured while checking for glitches: {e}")
            return

    def check_no_data(self):
        alert_alias = "no_data"
        print("\nChecking for data...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = False

            most_recent_ms = 0
            for channel in self.data[house_alias]:
                if self.data[house_alias][channel]['times'][-1] > most_recent_ms:
                    most_recent_ms = self.data[house_alias][channel]['times'][-1]

            if not self.data[house_alias]:
                if not self.alert_status[house_alias][alert_alias]:
                    alert_message = f"{house_alias}: No data found in the last {self.hours_back} hour(s)"
                    self.send_alert(alert_message, house_alias, alert_alias)
                    self.alert_status[house_alias][alert_alias] = True

            elif self.reference_epoch() - most_recent_ms/1000 > self.max_time_no_data:
                if not self.alert_status[house_alias][alert_alias]:
                    alert_message = f"{house_alias}: No data coming in since {round((self.reference_epoch()-most_recent_ms/1000)/60,1)} minutes"
                    self.send_alert(alert_message, house_alias, alert_alias)
                    self.alert_status[house_alias][alert_alias] = True

            else:
                print(f"- {house_alias}: Found data up to {round((self.reference_epoch()-most_recent_ms/1000)/60,1)} minutes ago")
                self.alert_status[house_alias][alert_alias] = False

        print("\nChecking for Spruce data...")
        if 'spruce' not in self.alert_status:
            self.alert_status['spruce'] = {}
        if alert_alias not in self.alert_status['spruce']:
            self.alert_status['spruce'][alert_alias] = False

        most_recent_ms = 0
        if self.spruce_snapshots:
            most_recent_ms = max([x.message_persisted_ms for x in self.spruce_snapshots])

        if not self.spruce_snapshots:
            if not self.alert_status['spruce'][alert_alias]:
                alert_message = f"{'spruce'}: No data found in the last 10 minutes"
                self.send_alert(alert_message, 'spruce', alert_alias)
                self.alert_status['spruce'][alert_alias] = True
            
        elif self.reference_epoch() - most_recent_ms/1000 > self.max_time_no_data:
            if not self.alert_status['spruce'][alert_alias]:
                alert_message = f"{'spruce'}: No data coming in since {round((self.reference_epoch()-most_recent_ms/1000)/60,1)} minutes"
                self.send_alert(alert_message, 'spruce', alert_alias)
                self.alert_status['spruce'][alert_alias] = True

        else:
            print(f"- {'spruce'}: Found data up to {round((self.reference_epoch()-most_recent_ms/1000)/60,1)} minutes ago")
            self.alert_status['spruce'][alert_alias] = False

    def check_zone_below_setpoint(self):
        alert_alias = "zone_setpoint"
        print("\nChecking for zones below setpoint...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = {}
            print(f"- {house_alias}:")

            if house_alias in self.houses_in_standby:
                print(f"-- {house_alias} is in Standby, skipping")
                continue

            channels_by_zone = {}
            for channel in [x for x in self.data[house_alias] if 'zone' in x]:
                if len(channel.split("-")) >= 2:
                    channel_name_short = channel.split("-")[0] + "-" + channel.split("-")[1]
                else:
                    channel_name_short = channel[:5]
                if channel_name_short not in channels_by_zone:
                    channels_by_zone[channel_name_short] = []
                channels_by_zone[channel_name_short].append(channel)

            for zone in channels_by_zone:

                # Temporary fix while layout.lite messages are getting to journaldb
                if 'garage' in zone and 'elm' in house_alias:
                    print(f"-- {zone} is the garage zone in Elm, skipping")
                    continue

                if zone not in self.alert_status[house_alias][alert_alias]:
                    self.alert_status[house_alias][alert_alias][zone] = False

                zone_is_critical = False
                if self.critical_zones_by_house[house_alias]['known']:
                    for critical_zone in self.critical_zones_by_house[house_alias]['list']:
                        if zone[6:] in critical_zone:
                            zone_is_critical = True
                            break
                    if not zone_is_critical:
                        print(f"-- {zone} is not a critical zone")
                        continue

                setpoint = 0
                temperature = 0
                found_setpoint = False
                found_temperature = False
                for channel in channels_by_zone[zone]:
                    if "set" in channel:
                        values = self.data[house_alias][channel]["values"]
                        if values:
                            setpoint = values[-1] / 1000
                            found_setpoint = True
                    if "temp" in channel and "gw" not in channel:
                        values = self.data[house_alias][channel]["values"]
                        if values:
                            temperature = values[-1] / 1000
                            found_temperature = True
                if not found_setpoint:
                    print(f"-- {zone}: Missing setpoint channel or readings")
                    continue
                if not found_temperature:
                    print(f"-- {zone}: Missing temperature channel or readings")
                    continue

                if setpoint - temperature < self.max_setpoint_violation_f:
                    print(f"-- {zone} is ok")
                    self.alert_status[house_alias][alert_alias][zone] = False
                else:                    
                    # Check for a recent setpoint increase 
                    setpoint_channel: str = [x for x in channels_by_zone[zone] if "set" in x][0]
                    if len(set(self.data[house_alias][setpoint_channel]["values"])) == 1:
                        if not self.alert_status[house_alias][alert_alias][zone]:
                            alert_message = f"{house_alias}: {setpoint_channel.replace('-set','')} is significantly below setpoint"
                            self.send_alert(alert_message, house_alias, alert_alias+f"_{zone}")
                            self.alert_status[house_alias][alert_alias][zone] = True
                    else:
                        setpoint_values = [x/1000 for x in self.data[house_alias][setpoint_channel]["values"]]
                        if min(setpoint_values) < setpoint_values[-1] and min(setpoint_values)-temperature < self.max_setpoint_violation_f:
                            print(f"-- {zone} is significantly below setpoint but the setpoint was increased recently")
                        else:
                            if not self.alert_status[house_alias][alert_alias][zone]:
                                alert_message = f"{house_alias}: {setpoint_channel.replace('-set','')} is significantly below setpoint"
                                self.send_alert(alert_message, house_alias, alert_alias+f"_{zone}")
                                self.alert_status[house_alias][alert_alias][zone] = True
    
    def check_zone_freezing(self):
        alert_alias = "zone_freezing"
        print("\nChecking for zones freezing...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = {}
            print(f"- {house_alias}:")

            if house_alias in self.houses_in_standby:
                print(f"-- {house_alias} is in Standby, skipping")
                continue

            channels_by_zone = {}
            for channel in [x for x in self.data[house_alias] if 'zone' in x]:
                if len(channel.split("-")) >= 2:
                    channel_name_short = channel.split("-")[0] + "-" + channel.split("-")[1]
                else:
                    channel_name_short = channel[:5]
                if channel_name_short not in channels_by_zone:
                    channels_by_zone[channel_name_short] = []
                channels_by_zone[channel_name_short].append(channel)

            for zone in channels_by_zone:
                if zone not in self.alert_status[house_alias][alert_alias]:
                    self.alert_status[house_alias][alert_alias][zone] = False

                freezing_threshold = 40
                temperature = 60
                found_temperature = False
                for channel in channels_by_zone[zone]:
                    if "temp" in channel and "gw" not in channel:
                        temperature = self.data[house_alias][channel]["values"][-1] / 1000
                        found_temperature = True
                if not found_temperature:
                    print(f"-- {zone}: Missing temperature channel")
                    continue

                if freezing_threshold <= temperature:
                    print(f"-- {zone} is ok")
                    self.alert_status[house_alias][alert_alias][zone] = False
                else:                    
                    if not self.alert_status[house_alias][alert_alias][zone]:
                        alert_message = f"{house_alias}: {zone} is below 40F"
                        self.send_alert(alert_message, house_alias, alert_alias+f"_{zone}")
                        self.alert_status[house_alias][alert_alias][zone] = True

    def check_dist_pump(self):
        alert_alias = "dist_pump"
        print("\nChecking for distribution pump activity...")
        for house_alias in self.selected_house_aliases:
            print(f"- {house_alias}:")

            if house_alias in self.houses_in_standby:
                print(f"-- {house_alias} is in Standby, skipping")
                continue

            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = 0

            if house_alias in self.whitewire_threshold_watts:
                threshold = self.whitewire_threshold_watts[house_alias]
            else:
                threshold = self.whitewire_threshold_watts['default']

            last_heatcall_time = 0
            for zone_state in [x for x in self.data[house_alias] if 'zone' in x and 'whitewire' in x]:
                channel = self.data[house_alias][zone_state]
                channel['values'] = [int(abs(x)>threshold) for x in channel['values']]
                min_heatcall_ms = 15 * 60 * 1000
                pairs = list(zip(channel['times'], channel['values']))
                zone_heatcall_times = []
                i = 0
                while i < len(pairs):
                    if pairs[i][1] != 1:
                        i += 1
                        continue
                    run_start_ms = pairs[i][0]
                    j = i
                    while j < len(pairs) and pairs[j][1] == 1:
                        j += 1
                    cutoff_ms = run_start_ms + min_heatcall_ms
                    for k in range(i, j):
                        tk, _ = pairs[k]
                        if tk >= cutoff_ms:
                            zone_heatcall_times.append(tk)
                    i = j
                no_heatcall_times = [t for t, state in zip(channel['times'], channel['values']) if state==0]
                valid_zone_heatcall_times = [t for t in zone_heatcall_times if self.reference_epoch()-t/1000 >= 5*60]
                if valid_zone_heatcall_times:
                    zone_last_heatcall_time = max(valid_zone_heatcall_times)
                else:
                    continue
                no_heatcall_times_before_heatcall = [t for t in no_heatcall_times if t<=zone_last_heatcall_time]
                if no_heatcall_times_before_heatcall:
                    last_no_heatcall_time_before_heatcall = max(no_heatcall_times_before_heatcall)
                    heatcall_on = [t for t in zone_heatcall_times if t>=last_no_heatcall_time_before_heatcall]
                    if heatcall_on:
                        start_of_heatcall = min(heatcall_on)
                    else:
                        start_of_heatcall = last_no_heatcall_time_before_heatcall
                    # print(f"-- {zone_state} Start of heatcall: {self.unix_ms_to_date(start_of_heatcall)}")
                    # print(f"-- {zone_state} End of heatcall: {self.unix_ms_to_date(zone_last_heatcall_time)}")
                    last_heatcall_length = max(0, zone_last_heatcall_time - start_of_heatcall)/1000
                    # print(f"-- {zone_state} Heat call length: {round(last_heatcall_length/60,1)} minutes")
                    if last_heatcall_length < 5*60:
                        # print(f"-- {zone_state} Heat call was less than 5 minutes long. Skip.")
                        continue
                if zone_last_heatcall_time > last_heatcall_time:
                    last_heatcall_time = zone_last_heatcall_time

            if (not [x for x in self.data[house_alias] if 'zone' in x and 'state' in x] 
                or 'dist-pump-pwr' not in self.data[house_alias] or 'dist-flow' not in self.data[house_alias]):
                print(f"{house_alias}: Missing data!") # TODO: create an alert?
                continue

            if last_heatcall_time == 0:
                print(f"-- No recent heat call or too short/recent heat call to tell")
                continue

            print(f"Last heat call time: {self.unix_ms_to_date(last_heatcall_time)}")

            # Try to find power around the latest heat call
            pwr = self.data[house_alias]['dist-pump-pwr']
            power_around_heatcall = [
                power for time, power in zip(pwr['times'], pwr['values']) 
                if time >= last_heatcall_time - 5*60*1000
            ]
            found_power_after_heatcall = False
            if not power_around_heatcall and pwr['values'][-1] <= self.min_dist_pump_w:
                print(f"-- No pump power recorded around heat call and latest power is low")
            elif power_around_heatcall and max(power_around_heatcall) <= self.min_dist_pump_w:
                print(f"-- No significant pump power around heat call")
            else:
                print(f"-- Found dist pump power after last heat call")
                found_power_after_heatcall = True

            # Try to find flow around the latest heat call
            flow = self.data[house_alias]['dist-flow']
            flow_around_heatcall = [
                flow/100 for time, flow in zip(flow['times'], flow['values']) 
                if time >= last_heatcall_time - 5*60*1000
            ]
            if not flow_around_heatcall and flow['values'][-1] <= self.min_dist_pump_gpm:
                print(f"-- No pump flow recorded around heat call and latest flow is low")
                self.alert_status[house_alias][alert_alias] += 1
            elif max(flow_around_heatcall) <= self.min_dist_pump_gpm:
                print(f"-- No significant pump flow around heat call")
                self.alert_status[house_alias][alert_alias] += 1
            else:
                print(f"-- Found dist pump flow after last heat call")
                self.alert_status[house_alias][alert_alias] = 0
                continue

            if self.alert_status[house_alias][alert_alias] == 3:
                alert_message = f"{house_alias}: No distribution pump flow recorded since the last heat call"
                if found_power_after_heatcall:
                    alert_message += ", but found pump power"
                else:
                    alert_message += ", and no pump power found"
                self.send_alert(alert_message, house_alias, alert_alias)
    
    def check_store_pump(self):
        alert_alias = "store_pump"
        print("\nChecking for store pump activity...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = False

            if house_alias in self.houses_in_standby:
                print(f"-- {house_alias} is in Standby, skipping")
                continue

            if 'relay9' not in self.relays[house_alias]:
                print(f"{house_alias}: Missing relay9 data!")
                continue

            current_relay9_boss = list(self.relays[house_alias]['relay9'].keys())[0]
            latest_relay_time = 0
            for relay9_boss in self.relays[house_alias]['relay9']:
                boss_latest_time = max(self.relays[house_alias]['relay9'][relay9_boss]['times'])
                if boss_latest_time > latest_relay_time:
                    latest_relay_time = boss_latest_time
                    current_relay9_boss = relay9_boss

            r = self.relays[house_alias]['relay9'][current_relay9_boss]
            pairs = list(zip(r["times"], r["values"]))
            time_since_in_current_state = next(
                (pairs[i+1][0] for i in range(len(pairs) - 2, -1, -1) if pairs[i][1] != pairs[i+1][1]),
                pairs[0][0],
            )
            relay9_state = r['values'][-1]

            if 'store-pump-pwr' not in self.data[house_alias] or 'store-flow' not in self.data[house_alias]:
                print(f"{house_alias}: Missing data!") # TODO: create an alert?
                continue

            if relay9_state == "RelayClosed":
                if self.reference_epoch() - time_since_in_current_state/1000 > 10*60:
                    print(f"- {house_alias}: Relay 9 is closed since more than 10 minutes, expecting store flow")

                    # Try to find power
                    pwr = self.data[house_alias]['store-pump-pwr']
                    power_since_closed = [
                        power for time, power in zip(pwr['times'], pwr['values']) 
                        if time >= time_since_in_current_state
                    ]
                    found_power_after_closed = False
                    if not power_since_closed and pwr['values'][-1] <= self.min_store_pump_w:
                        print(f"- {house_alias}: No pump power recorded after relay 9 was closed")
                    elif max(power_since_closed) <= self.min_store_pump_w:
                        print(f"- {house_alias}: No significant pump power after relay 9 was closed")
                    else:
                        print(f"- {house_alias}: Found store pump power after relay 9 was closed")
                        found_power_after_closed = True

                    # Try to find flow
                    flow = self.data[house_alias]['store-flow']
                    flow_since_closed = [
                        flow/100 for time, flow in zip(flow['times'], flow['values']) 
                        if time >= time_since_in_current_state
                    ]
                    if not flow_since_closed and flow['values'][-1] <= self.min_store_pump_gpm:
                        print(f"- {house_alias}: No pump flow recorded after relay 9 was closed")
                    elif max(flow_since_closed) <= self.min_store_pump_gpm:
                        print(f"- {house_alias}: No significant pump flow after relay 9 was closed")
                    else:
                        print(f"- {house_alias}: Found store pump flow after relay 9 was closed")
                        self.alert_status[house_alias][alert_alias] = False
                        continue

                    if not self.alert_status[house_alias][alert_alias]:
                        alert_message = f"{house_alias}: No store pump flow since relay 9 was closed"
                        if found_power_after_closed:
                            alert_message += ", but found pump power"
                        else:
                            alert_message += ", and no pump power found"
                        self.send_alert(alert_message, house_alias, alert_alias)
                        self.alert_status[house_alias][alert_alias] = True
            
            elif relay9_state == "RelayOpen":
                print(f"- {house_alias}: Relay 9 is open, not expecting any store flow at the moment")
                self.alert_status[house_alias][alert_alias] = False

    def check_hp(self):
        alert_alias = "hp_on"
        print("\nChecking for HP activity...")
        for house_alias in self.selected_house_aliases:
            print(f"- {house_alias}:")
            if 'maple' in house_alias:
                print(f"-- Skipping for Maple")
                continue

            if house_alias in self.houses_in_standby:
                print(f"-- {house_alias} is in Standby, skipping")
                continue

            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = False

            # TODO: check if monoblock and adapt the code as a consequence
            if 'hp-idu-pwr' not in self.data[house_alias] or 'hp-odu-pwr' not in self.data[house_alias]:
                print(f"{house_alias}: Missing data!")
                continue

            if 'relay5' not in self.relays[house_alias]:
                print(f"{house_alias}: Missing relay5 data!")
                continue

            current_relay5_boss = list(self.relays[house_alias]['relay5'].keys())[0]
            latest_relay_time = 0
            for relay5_boss in self.relays[house_alias]['relay5']:
                boss_latest_time = max(self.relays[house_alias]['relay5'][relay5_boss]['times'])
                if boss_latest_time > latest_relay_time:
                    latest_relay_time = boss_latest_time
                    current_relay5_boss = relay5_boss

            r = self.relays[house_alias]['relay5'][current_relay5_boss]
            pairs = list(zip(r["times"], r["values"]))
            time_since_in_current_state = next(
                (pairs[i+1][0] for i in range(len(pairs) - 2, -1, -1) if pairs[i][1] != pairs[i+1][1]),
                pairs[0][0],
            )
            relay5_state = r['values'][-1]

            if relay5_state == "Scada":
                if self.reference_epoch() - time_since_in_current_state/1000 > 15*60:
                    print(f"-- Relay 5 is in Scada since more than 15 minutes")
                else:
                    self.alert_status[house_alias][alert_alias] = False
                    print(f"-- The HP should not be on")
                    continue
            else:
                self.alert_status[house_alias][alert_alias] = False
                print(f"-- The HP should not be on")
                continue

            current_relay6_boss = list(self.relays[house_alias]['relay6'].keys())[0]
            latest_relay_time = 0
            for relay6_boss in self.relays[house_alias]['relay6']:
                boss_latest_time = max(self.relays[house_alias]['relay6'][relay6_boss]['times'])
                if boss_latest_time > latest_relay_time:
                    latest_relay_time = boss_latest_time
                    current_relay6_boss = relay6_boss

            r = self.relays[house_alias]['relay6'][current_relay6_boss]
            pairs = list(zip(r["times"], r["values"]))
            time_since_in_current_state = next(
                (pairs[i+1][0] for i in range(len(pairs) - 2, -1, -1) if pairs[i][1] != pairs[i+1][1]),
                pairs[0][0],
            )
            relay6_state = r['values'][-1]

            if relay6_state == "RelayClosed":
                if self.reference_epoch() - time_since_in_current_state/1000 > 15*60:
                    print(f"-- Relay 6 is Closed since more than 15 minutes")
                else:
                    self.alert_status[house_alias][alert_alias] = False
                    print(f"-- The HP should not be on")
                    continue
            else: 
                self.alert_status[house_alias][alert_alias] = False
                print(f"-- The HP should not be on")
                continue

            print(f"-- The HP should be on")

            odu_channel = self.data[house_alias]['hp-odu-pwr']
            idu_channel = self.data[house_alias]['hp-idu-pwr']
            latest_reading_time_ms = max(max(odu_channel['times']), max(idu_channel['times']))
            if self.reference_epoch() - latest_reading_time_ms/1000 > 15*60:
                print("There is no recent HP power data available")
                continue

            on_times_odu = [t for t, v in zip(odu_channel['times'], odu_channel['values']) if v/1000 >= self.min_hp_kw]
            on_times_idu = [t for t, v in zip(idu_channel['times'], idu_channel['values']) if v/1000 >= self.min_hp_kw]
            on_times = sorted(on_times_odu + on_times_idu)
            on_times = [x for x in on_times if self.reference_epoch() - x/1000 < 15*60]

            if on_times:
                self.alert_status[house_alias][alert_alias] = False
                print(f"-- The HP is on")
            elif not self.alert_status[house_alias][alert_alias]:
                alert_message = f"{house_alias}: The HP is not coming on"
                self.send_alert(alert_message, house_alias, alert_alias)
                self.alert_status[house_alias][alert_alias] = True
        
    def check_in_atn(self):
        alert_alias = "not_in_atn"
        print("\nChecking that ATN is in control...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = False

            if house_alias in self.houses_in_standby:
                print(f"-- {house_alias} is in Standby, skipping")
                continue

            if 'relay5' not in self.relays[house_alias]:
                print(f"{house_alias}: Missing relay5 data!")
                continue

            current_relay5_boss = list(self.relays[house_alias]['relay5'].keys())[0]
            latest_relay_time = 0
            for relay9_boss in self.relays[house_alias]['relay5']:
                boss_latest_time = max(self.relays[house_alias]['relay5'][relay9_boss]['times'])
                if boss_latest_time > latest_relay_time:
                    latest_relay_time = boss_latest_time
                    current_relay5_boss = relay9_boss

            if current_relay5_boss == 'ltn.la.relay5':
                print(f"- {house_alias}: ATN is in control")
                self.alert_status[house_alias][alert_alias] = False

            elif current_relay5_boss == 'auto.lc.n.relay5' and not self.alert_status[house_alias][alert_alias]:
                self.send_alert(f"{house_alias}: Not in Atn!", house_alias, alert_alias)
                self.alert_status[house_alias][alert_alias] = True

    def check_hp_on_during_onpeak(self):
        alert_alias = "hp_onpeak"
        print("\nChecking that the HP is not on during onpeak...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = False

            if house_alias in self.houses_in_standby:
                print(f"-- {house_alias} is in Standby, skipping")
                continue

            if "hp-odu-pwr" not in self.data[house_alias] or "hp-odu-pwr" not in self.data[house_alias]:
                print(f"{house_alias}: Missing data!") # TODO: create an alert?
                continue

            odu_channel = self.data[house_alias]['hp-odu-pwr']
            on_times_odu = [t for t, v in zip(odu_channel['times'], odu_channel['values']) if v/1000 >= self.min_hp_kw]
            idu_channel = self.data[house_alias]['hp-idu-pwr']
            on_times_idu = [t for t, v in zip(idu_channel['times'], idu_channel['values']) if v/1000 >= self.min_hp_kw]
            on_times = sorted(on_times_odu + on_times_idu)

            sent_alert = False
            for time_ms in on_times:
                time_dt = self.unix_ms_to_date(time_ms)
                if time_dt.hour in self.on_peak_hours and time_dt.day_of_week < 5:
                    if (time_dt.hour == 7 or time_dt.hour == 16) and time_dt.minute < 2:
                        continue
                    if not self.alert_status[house_alias][alert_alias]:
                        alert_message = f"{house_alias}: HP was seen on at {time_dt}, which is during onpeak"
                        self.send_alert(alert_message, house_alias, alert_alias+f"_{time_dt.hour}")
                        self.alert_status[house_alias][alert_alias] = True
                        sent_alert = True
            
            if not sent_alert:
                print(f"- {house_alias}: HP is not on during onpeak")
                self.alert_status[house_alias][alert_alias] = False
    
    def check_rebooting(self):
        alert_alias = "rebooting"
        print("\nChecking for rebooting...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = False

            layouts_for_house = [
                m for m in self.layout_lites if m.house_alias == house_alias
            ]
            layout_times_for_house = [
                m.message_persisted_ms for m in layouts_for_house
            ]
            # Check for more than 5 layout records in the same 5-minute window
            if layout_times_for_house:
                rounded_times = [int(t//(5*60*1000)) for t in layout_times_for_house]
                time_counts = {}
                for t in rounded_times:
                    if t in time_counts:
                        time_counts[t] += 1
                    else:
                        time_counts[t] = 1
                reboot_detected = False
                for count in time_counts.values():
                    if count > 5:
                        reboot_detected = True
                        print(f"- {house_alias}: Rebooting detected")
                        alert_message = f"{house_alias}: Rebooting detected"
                        if not self.alert_status[house_alias][alert_alias]:
                            self.send_alert(alert_message, house_alias, alert_alias)
                            self.alert_status[house_alias][alert_alias] = True
                        break
                if not reboot_detected:
                    print(f"- {house_alias}: No rebooting detected in found layout.lite messages")
                    self.alert_status[house_alias][alert_alias] = False
            else:
                print(f"- {house_alias}: No rebooting (no layout.lite messages found)")
                self.alert_status[house_alias][alert_alias] = False
    
    def check_no_more_oil(self):
        return
        alert_alias = "no_more_oil"
        print("\nChecking for no more oil remaining...")
        for house_alias in self.selected_house_aliases:
            if alert_alias not in self.alert_status[house_alias]:
                self.alert_status[house_alias][alert_alias] = False

            if "oil-boiler-pwr" not in self.data[house_alias]:
                print(f"{house_alias}: Missing oil boiler power data!")
                continue

            oil_boiler_channel = self.data[house_alias]['oil-boiler-pwr']
            on_times_oil_boiler = [t for t, v in zip(oil_boiler_channel['times'], oil_boiler_channel['values']) if v/1000 >= self.min_hp_kw]

            sent_alert = False
            for time_ms in on_times_oil_boiler:
                
                    if not self.alert_status[house_alias][alert_alias]:
                        alert_message = f"{house_alias}: Oil boiler is on but is not heating the buffer"
                        self.send_alert(alert_message, house_alias, alert_alias)
                        self.alert_status[house_alias][alert_alias] = True
                        sent_alert = True
            
            if not sent_alert:
                print(f"- {house_alias}: Oil boiler is doing fine")
                self.alert_status[house_alias][alert_alias] = False

    def main(self):
        while True:
            print(f"-------------- CHECKS START --------------")
            try:
                self.check_telegram_alerts()
                self.get_data_from_journaldb()
                self.get_data_from_journaldb_spruce()
                self.check_for_glitches()
                self.check_no_data()
                self.check_zone_below_setpoint()
                self.check_zone_freezing()
                self.check_dist_pump()
                self.check_store_pump()
                self.check_hp()
                # self.check_in_atn()
                self.check_hp_on_during_onpeak()
                self.check_rebooting()
                # self.check_no_more_oil()
            except Exception as e:
                print(f"Error in alert loop: {e}")
            time.sleep(self.main_loop_seconds)


def main() -> None:
    AlertGenerator()


if __name__ == "__main__":
    main()