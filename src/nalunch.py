from dataclasses import dataclass
import requests
from datetime import datetime, timedelta

from typing import Optional
from config import NalunchCredentials


@dataclass
class VendingItemToBuy:
    id: str
    count: int

    def json(self):
        return {
            "id": self.id,
            "count": self.count,
        }


class NalunchAccount:
    creds: NalunchCredentials
    access_token: Optional[str]
    refresh_token: Optional[str]
    refreshed: datetime

    def __init__(self, creds: NalunchCredentials):
        self.creds = creds

    def login(self):
        res = requests.post(
            "https://api.nalunch.me/v3/account/auth",
            json={
                "username": self.creds.username,
                "password": self.creds.password,
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": "",
                "Expires": "0",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "User-Agent": "NaLaunch/174 CFNetwork/1410.0.3 Darwin/22.6.0",
                "Connection": "close",
            },
        )
        if res.status_code != 200:
            raise Exception(
                f"Unable to login: code = {res.status_code}, text = {res.text}"
            )

        data = res.json()
        self.refreshed = datetime.now()
        self.access_token = data["details"]["access_token"]
        self.refresh_token = data["details"]["refresh_token"]

    def do_refresh_token(self):
        res = requests.post(
            "https://api.nalunch.me/v3/account/refresh",
            json={
                "accessToken": self.access_token,
                "refreshToken": self.refresh_token,
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": "",
                "Expires": "0",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "User-Agent": "NaLaunch/174 CFNetwork/1410.0.3 Darwin/22.6.0",
                "Connection": "close",
            },
        )
        if res.status_code != 200:
            raise Exception(
                f"Unable to refresh: code = {res.status_code}, text = {res.text}"
            )

        data = res.json()
        self.refreshed = datetime.now()
        self.access_token = data["details"]["access_token"]
        self.refresh_token = data["details"]["refresh_token"]

    def get_balance(self) -> int:
        if datetime.now() - self.refreshed > timedelta(minutes=5):
            self.do_refresh_token()

        res = requests.get(
            "https://api.nalunch.me/billing",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {self.access_token}",
                "Expires": "0",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "User-Agent": "NaLaunch/174 CFNetwork/1410.0.3 Darwin/22.6.0",
                "Connection": "close",
            },
        )
        if res.status_code != 200:
            raise Exception(
                f"Unable to login: code = {res.status_code}, text = {res.text}"
            )

        data = res.json()
        return int(data["compensationSum"]) - int(data["spentSum"])

    def pay(self, path: str):
        if datetime.now() - self.refreshed > timedelta(minutes=5):
            self.do_refresh_token()
        if not path.startswith("/"):
            path = "/" + path

        res = requests.put(
            f"https://api.nalunch.me{path.replace('/check', '/approve')}",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {self.access_token}",
                "Expires": "0",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "User-Agent": "NaLaunch/174 CFNetwork/1410.0.3 Darwin/22.6.0",
                "Connection": "close",
            },
        )
        if res.status_code != 200:
            raise Exception(
                f"Unable to pay: code = {res.status_code}, text = {res.text}"
            )

        return int(res.json()["details"]["amount"])

    def pay_vending(self, device_id: str, items_to_buy: list[VendingItemToBuy]):
        if datetime.now() - self.refreshed > timedelta(minutes=5):
            self.do_refresh_token()

        res = requests.post(
            "https://api.nalunch.me/v3/vending/transaction",
            json={
                "deviceId": int(device_id),
                "dateTimeUtc": datetime.utcnow().isoformat(timespec="milliseconds"),
                "items": list(map(lambda x: x.json(), items_to_buy)),
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {self.access_token}",
                "Expires": "0",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "User-Agent": "NaLaunch/174 CFNetwork/1410.0.3 Darwin/22.6.0",
                "Connection": "close",
            },
        )

        if res.status_code != 200:
            raise Exception(
                f"Unable to pay: code = {res.status_code}, text = {res.text}"
            )

        return int(res.json()["details"]["sum"])

    def get_vending_name(self, device_id):
        if datetime.now() - self.refreshed > timedelta(minutes=5):
            self.do_refresh_token()

        res = requests.get(
            f"https://api.nalunch.me/v3/vending/{device_id}",
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {self.access_token}",
                "Expires": "0",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "User-Agent": "NaLaunch/174 CFNetwork/1410.0.3 Darwin/22.6.0",
                "Connection": "close",
            },
        )

        if res.status_code != 200:
            raise Exception(
                f"Unable to get vending info: code = {res.status_code}, text = {res.text}"
            )
        
        return res.json()["details"]["restaurantName"]
    
    def get_vending_products(self, device_id: str):
        if datetime.now() - self.refreshed > timedelta(minutes=5):
            self.do_refresh_token()

        res = requests.post(
            f"https://api.nalunch.me/v2/vending/products?deviceId={device_id}&page=1&limit=50",
            json={
                "code": "string",
            },
            headers={
                "Accept": "application/json, text/plain, */*",
                "Authorization": f"Bearer {self.access_token}",
                "Expires": "0",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-GB,en;q=0.9",
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "User-Agent": "NaLaunch/174 CFNetwork/1410.0.3 Darwin/22.6.0",
                "Connection": "close",
            },
        )

        if res.status_code != 200:
            raise Exception(
                f"Unable to pay: code = {res.status_code}, text = {res.text}"
            )
        
        return res.json()["details"]["items"]

    def init(self):
        pass
