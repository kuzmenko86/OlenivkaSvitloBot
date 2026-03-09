import time
import hashlib
import hmac
import requests
from config import TUYA_ACCESS_ID, TUYA_ACCESS_SECRET, TUYA_BASE_URL


class TuyaAuth:
    def __init__(self):
        self.client_id = TUYA_ACCESS_ID
        self.secret = TUYA_ACCESS_SECRET
        self.base_url = TUYA_BASE_URL
        self.access_token = ""

    def _generate_sign(self, method: str, url_path: str, token: str = "", body: str = "") -> dict:
        """Генерація підпису для Tuya API (аналог Pre-request скрипта в Postman)."""
        timestamp = str(int(time.time() * 1000))

        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest().lower()
        string_to_sign = f"{method}\n{content_hash}\n\n{url_path}"
        message = self.client_id + token + timestamp + string_to_sign
        sign = hmac.new(
            self.secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest().upper()

        headers = {
            "client_id": self.client_id,
            "sign": sign,
            "t": timestamp,
            "sign_method": "HMAC-SHA256",
        }

        if token:
            headers["access_token"] = token

        return headers

    def login(self) -> str:
        """Отримання access_token (аналог Login запиту в Postman)."""
        url_path = "/v1.0/token?grant_type=1"
        headers = self._generate_sign("GET", url_path, token="")

        response = requests.get(f"{self.base_url}{url_path}", headers=headers)
        data = response.json()

        if data.get("success"):
            self.access_token = data["result"]["access_token"]
            print("✅ Токен отримано успішно")
            return self.access_token
        else:
            raise Exception(f"❌ Помилка логіну: {data.get('msg')}")

    def get_headers(self, method: str, url_path: str, body: str = "") -> dict:
        """Отримання заголовків з підписом для авторизованих запитів."""
        if not self.access_token:
            self.login()

        return self._generate_sign(method, url_path, token=self.access_token, body=body)