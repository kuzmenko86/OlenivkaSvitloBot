import requests
from tuya_auth import TuyaAuth
from config import TUYA_BASE_URL


class TuyaAPI:
    def __init__(self):
        self.auth = TuyaAuth()
        self.base_url = TUYA_BASE_URL

    def get_device_status(self, device_id: str) -> dict:
        """Отримання повного статусу девайса по ID."""
        url_path = f"/v1.0/devices/{device_id}"
        headers = self.auth.get_headers("GET", url_path)

        response = requests.get(f"{self.base_url}{url_path}", headers=headers)
        data = response.json()

        if data.get("success"):
            return data["result"]

        # Якщо токен протух — перелогінюємось
        if data.get("code") == 1010:
            print("🔄 Токен протух, оновлюю...")
            self.auth.access_token = ""
            headers = self.auth.get_headers("GET", url_path)
            response = requests.get(f"{self.base_url}{url_path}", headers=headers)
            data = response.json()
            if data.get("success"):
                return data["result"]

        raise Exception(f"❌ Помилка: {data.get('msg')}")

    def get_device_online(self, device_id: str) -> bool:
        """Перевірка чи девайс онлайн."""
        result = self.get_device_status(device_id)
        return result.get("online", False)

    def get_status_value(self, device_id: str, code: str):
        """Отримання значення конкретного параметра зі status."""
        result = self.get_device_status(device_id)
        for item in result.get("status", []):
            if item.get("code") == code:
                return item.get("value")
        return None

    def get_electricity_info(self, device_id: str) -> dict:
        """Отримання інформації про електрику з девайса."""
        result = self.get_device_status(device_id)
        online = result.get("online", False)
        name = result.get("name", "Unknown")

        status_map = {}
        for item in result.get("status", []):
            status_map[item["code"]] = item["value"]

        voltage_raw = status_map.get("cur_voltage", 0)
        voltage = voltage_raw / 10  # 2403 → 240.3

        current_raw = status_map.get("cur_current", 0)
        current = current_raw / 1000  # мА → А

        power_raw = status_map.get("cur_power", 0)
        power = power_raw / 10  # → Вт

        return {
            "name": name,
            "online": online,
            "voltage": voltage,
            "current": current,
            "power": power,
            "switch": status_map.get("switch_1", False),
        }

    def get_temperature_info(self, device_id: str) -> dict:
        """Отримання інформації з температурного девайса."""
        result = self.get_device_status(device_id)
        name = result.get("name", "Unknown")
        online = result.get("online", False)

        status_map = {}
        for item in result.get("status", []):
            status_map[item["code"]] = item["value"]

        return {
            "name": name,
            "online": online,
            "status": status_map,
        }