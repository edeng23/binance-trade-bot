API_KEY = 'vmPUZE6mv9SD5VNHk4HlWFsOr6aKE2zvsw0MuIgwCIPy6utIco14y7Ju91duEh8A'
SECRET_KEY = 'NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j'
BRIDGE_SYMBOL = 'USDT'
BINANCE_TLD = 'com'
SCOUT_SLEEP_TIME = 5
SCOUT_MULTIPLIER = 5.0
SCOUT_HISTORY_PRUNE_TIME = 1.0

DEFAULT_USER_CONFIG = f"""[binance_user_config]
                        api_key={API_KEY}
                        api_secret_key={SECRET_KEY}
                        current_coin=
                        bridge=USDT
                        tld=com
                        hourToKeepScoutHistory=1
                        scout_multiplier=5
                        scout_sleep_time=5"""
