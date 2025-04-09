from flask import Flask, request, jsonify
import requests
import datetime
import threading
import time
import schedule
import openpyxl
import os
import pandas as pd
import numpy as np
import yfinance as yf
import MetaTrader5 as mt5
import requests
import datetime
# Your Telegram bot's token
TELEGRAM_BOT_TOKEN = "---------------------------------------------"
# Your Telegram group chat ID (e.g.,YOUR CHAT ID)
TELEGRAM_CHAT_ID = "-4704348739"
def send_telegram_alert(symbol, action, entry, sl, tp, confluences):
    now = datetime.datetime.now(datetime.timezone.utc)
    message = f"📢 **Forex Alert - {symbol}**\n\n➡️ Action: `{action.upper()}`\n💰 Entry: `{entry}`\n💸 SL: `{sl}`\n🎯 TP: `{tp}`\n🤖 Confluences: `{confluences}`\n⏰ Time: `{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`"
    
    url = f"https://api.telegram.org/bot{7728011216:AAFoMi3oyi6Dzvo-cTcgL6V4-KS6awwEO8w}/sendMessage"
    payload = {
        "chat_id":-4704348739,
        "text": message
    }
    
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print(f"Alert sent to Telegram: {message}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending to Telegram: {e}")
        return False
    

# --- Initialize MetaTrader 5 connection ---
# This function initializes the MetaTrader 5 connection and checks if it's successful.
#Initialize MetaTrader 5 connection 
def initialize_mt5():
    if not mt5.initialize():
        print("initialize() failed")
        mt5.shutdown()
app = Flask(__name__)




    


DISCORD_WEBHOOK_URL = "your webhook url "

WATCHLIST_SYMBOLS = [
    "AUDCAD=X", "AUDCHF=X", "AUDJPY=X", "AUDNZD=X", "AUDUSD=X",
    "CADCHF=X", "CADJPY=X", "CADJPY=X", "CHFJPY=X", "EURAUD=X",
    "EURCAD=X", "EURCHF=X", "EURGBP=X", "EURJPY=X", "EURNZD=X",
    "EURUSD=X", "GBPCAD=X", "GBPCHF=X", "GBPJPY=X", "GBPNZD=X",
    "GBPUSD=X", "NZDCAD=X", "NZDCHF=X", "NZDJPY=X", "NZDUSD=X",
    "USDCAD=X", "USDCHF=X", "USDJPY=X", "CL=F", "XAGUSD=X", "XAUUSD=X"
]

EXCEL_FILE = "trading_journal.xlsx"

# --- Utility: Get current UTC time with timezone awareness
def get_current_time():
    return datetime.datetime.now(datetime.timezone.utc)

# --- Calculate RSI ---
def calculate_rsi(data, length=14):
    delta = data['Close'].diff(1)
    up, down = delta.copy(), delta.copy()
    up[up < 0] = 0
    down[down > 0] = 0
    roll_up = up.rolling(window=length).mean()
    roll_down = down.rolling(window=length).mean().abs()
    RS = roll_up / roll_down
    RSI = 100.0 - (100.0 / (1.0 + RS))
    return RSI

# --- Calculate Divergence ---
def calculate_divergence(data, length=14, lookback_right=5, lookback_left=5):
    rsi = calculate_rsi(data, length)
    pl_found = np.where(rsi == rsi.groupby((rsi.shift(1) != rsi).cumsum()).transform('min'), True, False)
    ph_found = np.where(rsi == rsi.groupby((rsi.shift(1) != rsi).cumsum()).transform('max'), True, False)
    
    rsi_lbr = rsi.shift(lookback_right)
    bull_cond = (rsi_lbr > rsi_lbr.shift(1)) & (data['Low'].shift(lookback_right) < data['Low'].shift(lookback_right + 1)) & pl_found
    bear_cond = (rsi_lbr < rsi_lbr.shift(1)) & (data['High'].shift(lookback_right) > data['High'].shift(lookback_right + 1)) & ph_found
    
    return bull_cond, bear_cond

# --- Market Structure Shift (MSS) ---
def market_structure_shift(data, length=5):
    data['MSS'] = 0
    for i in range(length, len(data)):
        if data['Close'][i] > data['Close'][i-length:i].max():
            data['MSS'][i] = 1  # Bullish MSS
        elif data['Close'][i] < data['Close'][i-length:i].min():
            data['MSS'][i] = -1  # Bearish MSS
    return data

# --- Order Blocks ---
def identify_order_blocks(data):
    bullish_ob = []
    bearish_ob = []
    for i in range(1, len(data)):
        if data['Close'][i] > data['Close'][i-1]:  # Bullish condition
            bullish_ob.append((data['High'][i], data['Low'][i]))
        elif data['Close'][i] < data['Close'][i-1]:  # Bearish condition
            bearish_ob.append((data['High'][i], data['Low'][i]))
    return bullish_ob, bearish_ob

# --- Liquidity Zones ---
def identify_liquidity_zones(data):
    liquidity_zones = []
    for i in range(1, len(data)):
        if data['Close'][i] > data['High'][i-1]:  # Example condition for liquidity
            liquidity_zones.append((data['High'][i], data['Low'][i]))
    return liquidity_zones

# --- Fair Value Gaps (FVG) ---
def identify_fvg(data):
    fvg = []
    for i in range(1, len(data)):
        if data['Low'][i] > data['High'][i-1]:  # Example condition for FVG
            fvg.append((data['High'][i-1], data['Low'][i]))
    return fvg

# --- Fibonacci Levels ---
def calculate_fibonacci(data):
    max_price = data['Close'].max()
    min_price = data['Close'].min()
    diff = max_price - min_price
    levels = {
        '0.236': max_price - diff * 0.236,
        '0.382': max_price - diff * 0.382,
        '0.500': max_price - diff * 0.500,
        '0.618': max_price - diff * 0.618,
        '0.786': max_price - diff * 0.786,
    }
    return levels

# Fetch historical data from MT5
def fetch_mt5_historical_data(symbol, timeframe, num_bars):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, num_bars)
    if rates is None:
        print(f"Failed to get historical data for {symbol}")
        return None
    return pd.DataFrame(rates)

# --- Fetch Historical Data using Yahoo Finance API ---
def fetch_historical_data(symbol, period="1y", interval="1d"):
    data = yf.download(symbol, period=period, interval=interval)
    return data

# --- Send Discord Alerts ---
def send_discord_alert(symbol, action, entry, sl, tp, confluences):
    now = get_current_time()
    message = {
        "content": f"\ud83d\udce1 **Forex Alert - {symbol}**\n\n\u27a1\ufe0f Action: `{action.upper()}`\n\ud83d\udcb5 Entry: `{entry}`\n\ud83d\udcc9 SL: `{sl}`\n\ud83c\udfaf TP: `{tp}`\n\ud83e\udde0 Confluences: `{confluences}`\n\ud83d\udd52 Time: `{now.strftime('%Y-%m-%d %H:%M:%S UTC')}`"
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=message)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print("Error sending to Discord:", e)
        return False
    
# --- Webhook Endpoint ---
@app.route('/webhook', methods=['POST'])  # Accepts POST requests
def webhook():
    data = request.json
    print("Webhook received:", data)
    return jsonify({"status": "received"}), 200

# --- MT5 Historical Data Endpoint ---
@app.route('/mt5/historical', methods=['GET'])  # Fetch historical data
def get_historical_data():
    symbol = request.args.get('symbol')
    timeframe = request.args.get('timeframe', 'H1')  # Default to hourly
    num_bars = int(request.args.get('num_bars', 100))  # Default to 100 bars
    historical_data = fetch_mt5_historical_data(symbol, timeframe, num_bars)
    if historical_data is not None:
        return historical_data.to_json(orient='records'), 200
    return jsonify({"error": "Failed to fetch historical data"}), 500

# --- Log Trades to Excel ---
def log_trade_to_excel(symbol, action, entry, sl, tp, confluences):
    if not os.path.exists(EXCEL_FILE):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Date", "Symbol", "Action", "Entry", "SL", "TP", "Confluences"])
    else:
        wb = openpyxl.load_workbook(EXCEL_FILE)
        ws = wb.active
    
    now = get_current_time().strftime('%Y-%m-%d %H:%M:%S')
    ws.append([now, symbol, action, entry, sl, tp, confluences])
    wb.save(EXCEL_FILE)

# --- Daily Scan ---
def daily_scan():
    for symbol in WATCHLIST_SYMBOLS:
        # Fetch historical data for the symbol
        data = fetch_historical_data(symbol)
        
        # Apply the logic
       
        data = market_structure_shift(data)
        bullish_ob, bearish_ob = identify_order_blocks(data)
        liquidity_zones = identify_liquidity_zones(data)
        fvg = identify_fvg(data)
        fibonacci_levels = calculate_fibonacci(data)

        # Calculate divergence
        bull_cond, bear_cond = calculate_divergence(data)

        # Create trading alerts
        entry = "CMP"
        sl = "0.25% of balance"
        tp = "Wyckoff Target"
        confluences = f"FVG: {fvg}, MSS: {data['MSS'].iloc[-1]}, OB: {bullish_ob}"

        # Check for RSI conditions
        rsi = calculate_rsi(data)
        if rsi.iloc[-1] < 30 and bull_cond.any():  # Oversold condition
            action = "buy"
            send_discord_alert(symbol, action, entry, sl, tp, confluences)
            log_trade_to_excel(symbol, action, entry, sl, tp, confluences)
        elif rsi.iloc[-1] > 70 and bear_cond.any():  # Overbought condition
            action = "sell"
            send_discord_alert(symbol, action, entry, sl, tp, confluences)
            log_trade_to_excel(symbol, action, entry, sl, tp, confluences)

# --- Scheduler ---
def run_scheduler():
    def job():
        current_day = datetime.datetime.now().weekday()  # Monday is 0 and Sunday is 6
        if current_day < 5:  # Only run from Monday (0) to Friday (4)
            print("Running scheduled scan...")
            with app.app_context():
                daily_scan()
        else:
            print("It's the weekend. Skipping scan.")

    # Schedule scans every 8 hours from Monday to Friday
    schedule.every(8).hours.do(job)

    while True:
        schedule.run_pending()
        time.sleep(60)

if __name__ == "__main__":
    threading.Thread(target=run_scheduler, daemon=True).start()
    app.run(debug=True)