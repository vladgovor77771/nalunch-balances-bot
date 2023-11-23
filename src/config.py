import yaml
from dataclasses import dataclass


@dataclass
class NalunchCredentials:
    name: str
    username: str
    password: str


@dataclass
class Config:
    telegram_token: str
    accounts: list[NalunchCredentials]
    allowed_chat_ids: set[int]


def parse_config(path: str) -> Config:
    with open(path, "r") as file:
        data = yaml.safe_load(file)

    accounts = [NalunchCredentials(**account) for account in data["accounts"]]
    return Config(
        telegram_token=data["telegram_token"],
        accounts=accounts,
        allowed_chat_ids=set(data["allowed_chat_ids"]),
    )
