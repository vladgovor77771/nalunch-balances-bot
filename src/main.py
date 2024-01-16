import argparse

from config import parse_config
from nalunch import NalunchAccount
from tg import NalunchTelegramBot


def parse_arguments():
    parser = argparse.ArgumentParser(description='Process some paths.')
    parser.add_argument('--config', type=str, help='Path to the config file', required=True)
    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_arguments()
    config = parse_config(args.config)
    accounts = []
    for account in config.accounts:
        acc = NalunchAccount(account)
        try:
            acc.login()
            accounts.append(acc)
        except Exception as e:
            print(account, e)
            raise e
    
    bot = NalunchTelegramBot(config.telegram_token, config.allowed_chat_ids, accounts, config.known_vending_devices)

    print("starting")
    bot.run()
