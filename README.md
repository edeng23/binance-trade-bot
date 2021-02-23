# binance-trade-bot

>Automated cryptocurrency trading bot

## Why?

This script was inspired by the observation that all cryptocurrencies pretty much behave in the same way. When one spikes, they all spike, and when one takes a dive, they all do. *Pretty much*. Moreover, all coins follow Bitcoin's lead; the difference is their phase offset.

So, if coins are basically oscillating with respect to each other, it seems smart to trade the rising coin for the falling coin, and then trade back when the ratio is reversed.

## How?

The trading is done in the Binance market platform, which of course does not have markets for every altcoin pair. The workaround for this is to use Tether (USDT), which is stable by design, as a bridge currency.

<p align="center">
  Coin A → USDT → Coin B
</p>

The way the bot takes advantage of this behaviour is to always downgrade from the "strong" coin to the "weak" coin, under the assumption that at some point the tables will turn. It will then return to the original coin, ultimately holding more of it than it did originally. This is done while taking into consideration the trading fees.

<div align="center">
  <p><b>Coin A</b> → USDT → Coin B</p>
  <p>Coin B → USDT → Coin C</p>
  <p>...</p>
  <p>Coin C → USDT → <b>Coin A</b></p>
</div>

The bot jumps between a configured set of coins on the condition that it does not return to a coin unless it is profitable in respect to the amount held last. This means that we will never end up having less of a certain coin. The risk is that one of the coins may freefall relative to the others all of a sudden, attracting our reverse greedy algorithm.

## Binance Setup

* Create a [Binance account](https://accounts.binance.com/en/register).
* Enable Two-factor Authentication.
* Create a new API key.
* Get a cryptocurrency. If its symbol is not in the default list, add it.

## Tool Setup

### Install Python dependencies

Run the following line in the terminal: `pip install -r requirements.txt`.

### Create user configuration

Create a .ini file named `user.cfg` based off `.user.cfg.example`, then add your API keys and current coin.

### Integration with Telegram Bots

You can integrate the bot with a Telegram bot that will notify you with log information. 
This is done by creating a bot using Telegram's BotFather and inserting the Telegram Bot's TOKEN and the corresponding CHAT_ID in the configuration file. 
For more information about Telegram bots refer to [Telegram's official documentation](https://core.telegram.org/bots).

### Run

`./crypto_trading.py`

### Docker

```shell
docker-compose up
```

if you only want to start the sqlitebrowser
```shell
docker-compose up -d sqlitebrowser
```
## Support the Project

<a href="https://www.buymeacoffee.com/edeng" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

## Join the Chat

* **Discord**: [Invite Link](https://discord.gg/m4TNaxreCN)

<p align="center">
  <img src = "https://usercontent2.hubstatic.com/6061829.jpg">
</p>

## Disclaimer

The code within this repository comes with no guarantee. Run it at your own risk. 
Do not risk money which you are afraid to lose. There might be bugs in the code - this software does not come with any warranty.
