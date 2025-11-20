![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11+-yellow.svg)
![Discord](https://img.shields.io/badge/Discord-Bot-blue.svg)


# 🚀 Crypto Discord Bot

A powerful and modern cryptocurrency Discord bot written in **Python (discord.py v2)**.  
Includes **live prices, charts, indicators, alerts, portfolios, news**, and more — all powered by **CoinGecko** and optional **mplfinance** charts.

---

# ✨ Features

## 🟢 Core Crypto Tools

### **Prices**
- `!price <coin>` rich embed with:
  - Thumbnail icon  
  - Price  
  - 24h change (colored)  
  - Market cap  
  - Rank  
  - 24h high/low  
  - Sparkline (unicode + optional PNG)

### **Charts**
- `!chart <coin> [vs] [days] [engine]`
- Engines:
  - `mplf` → mplfinance candles  
  - `mpl` → matplotlib fallback  
- Time ranges: `1, 7, 14, 30, 90, 180, 365, max`

### **Indicators**
- `!indicator <coin> [vs] [days] [indicator]`
- SMA, EMA, RSI, MACD, ALL dashboard

## 🔔 Price Alerts
- `!alert set <coin> <vs> <operator> <price>`
- Stored in `data/alerts.json`
- Background checker every 60s  
- Sends alerts to channel or DM  

## 📰 Crypto News
- `!news [coin] [limit]`
- Uses CryptoPanic-compatible wrapper  
- Clean embeds with source + link

## 💼 Portfolio
- Add holdings  
- Remove holdings  
- Show portfolio value  

## 🛠 Slash Commands Supported
Instant registration if `DEV_GUILD_ID` is set in `.env`.

## 🧹 Clean Shutdown
- Closes aiohttp sessions  
- Cancels tasks  
- Saves files safely  

---

# 📁 Project Structure

crypto-bot/
│
├── bot.py
├── .env
├── .gitignore
├── requirements.txt
├── LICENSE
│
├── cogs/
│ ├── alerts.py
│ ├── chart.py
│ ├── indicators.py
│ ├── price.py
│ ├── volume.py
│ ├── news.py
│ ├── portfolio.py
│ ├── misc.py
│
└── utils/
├── coingecko.py
├── converters.py
├── formatting.py
├── charting.py
├── news.py
├── db.py

# 🔧 Installation

## 1. Create / activate venv

### Windows:
```bash
python -m venv venv
venv\Scripts\activate
```

### Mac/Linux:
```bash 
python3 -m venv venv
source venv/bin/activate
```

## 2. Install dependencies
```bash
pip intall -r requirements.txt
```

### Optional (best chart quality)
```bash
pip install mplfinance pandas numpy pillow
```
## 3. Create `.env` file
- create a file named `.env`

# Important
DISCORD_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE

# Optional: CryptoPanic API KEY (News)
CRYPTOPANIC_KEY=

# Optional: Binance API keys (only if you want private endpoints)
BINANCE_API_KEY=
BINANCE_SECRET_KEY=

# Optional: Logging / debug settings
LOG_LEVEL=INFO

### Never commit `.env` -- it's already in `.gitignore`

### Running the Bot
```bash
python bot.py
```
# Shutdown safely using:
CTRL + C
The bot automatically"
loads cogs
syncs slash commands(if dev guild provided)
starts background tasks
closes sessions on exit
