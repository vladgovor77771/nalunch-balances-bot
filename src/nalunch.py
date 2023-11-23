import requests
from datetime import datetime, timedelta

from typing import Optional
from config import NalunchCredentials


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
            raise Exception(f"Unable to login: code = {res.status_code}, text = {res.text}")
        
        data = res.json()
        self.refreshed = datetime.now()
        self.access_token = data["details"]["access_token"]
        self.refresh_token = data["details"]["refresh_token"]

    def refresh_token(self):
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
            raise Exception(f"Unable to refresh: code = {res.status_code}, text = {res.text}")
        
        data = res.json()
        self.refreshed = datetime.now()
        self.access_token = data["details"]["access_token"]
        self.refresh_token = data["details"]["refresh_token"]

    def get_balance(self) -> int:
        if datetime.now() - self.refreshed > timedelta(minutes=5):
            self.refresh_token()
        
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
            raise Exception(f"Unable to login: code = {res.status_code}, text = {res.text}")
        
        data = res.json()
        return int(data["compensationSum"])

    def init(self):
        pass
