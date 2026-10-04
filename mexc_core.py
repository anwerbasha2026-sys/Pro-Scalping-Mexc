import requests
import json
import os

BASE_URL = "https://api.mexc.com/api/v3"
SETTINGS_FILE = "settings.json"

def save_setting(key, value):
    settings = load_all_settings()
    settings[key] = value
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)

def get_setting(key, default_value=None):
    settings = load_all_settings()
    return settings.get(key, default_value)

def load_all_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def _request_json(method, url, timeout=8):
    try:
        return requests.request(method, url, timeout=timeout)
    except:
        return None

def _safe_json(response):
    try:
        return response.json()
    except:
        return {}

def get_supported_spot_symbols():
    try:
        res = _request_json("GET", f"{BASE_URL}/exchangeInfo", timeout=8)
        if res and res.status_code == 200:
            data = _safe_json(res)
            symbols = set()
            for s in data.get("symbols", []):
                if s.get("status") == "ENABLED" and s.get("quoteAsset") == "USDT":
                    symbols.add(s.get("symbol"))
            return symbols
    except:
        pass
    return set()

def get_top_symbols(limit=200):
    try:
        supported = get_supported_spot_symbols()
        response = _request_json("GET", f"{BASE_URL}/ticker/24hr", timeout=8)
        if response is not None and response.status_code == 200:
            data = _safe_json(response)
            if isinstance(data, dict):
                data = data.get("data", data.get("ticker", []))
            if not isinstance(data, list):
                return []

            usdt_pairs = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol", "")).replace("/", "").upper()
                if not symbol.endswith("USDT"):
                    continue
                if supported and symbol not in supported:
                    continue
                status = str(item.get("status", "")).upper()
                if status and status not in {"1", "TRADING", "ENABLED", "ONLINE"}:
                    continue
                try:
                    quote_volume = float(item.get("quoteVolume", 0) or 0)
                except:
                    quote_volume = 0.0
                usdt_pairs.append((symbol, quote_volume))

            usdt_pairs.sort(key=lambda x: x[1], reverse=True)
            symbols = [symbol for symbol, _ in usdt_pairs[:int(limit)]]
            return symbols
    except Exception as e:
        print(f"Top Symbols error: {e}")
    return []

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    gains = []
    losses = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices):
    if len(prices) < 26:
        return 0, 0, 0
    ema12 = calculate_ema(prices, 12)
    ema26 = calculate_ema(prices, 26)
    macd_line = (ema12 or 0) - (ema26 or 0)
    signal_line = macd_line * 0.9 # مبسط أو حساب إضافي
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

# دالة الفحص المستندة للشروط القابلة للتفعيل/الإيقاف
def check_trade_conditions_from_main(symbol, check_rsi=True, check_macd=False, check_volume=True):
    try:
        res = _request_json("GET", f"{BASE_URL}/klines?symbol={symbol}&interval=15m&limit=210", timeout=8)
        if not res or res.status_code != 200:
            return False, 0.0, "API Error"
            
        klines = _safe_json(res)
        if not isinstance(klines, list) or len(klines) < 200:
            return False, 0.0, "Not enough kline data"

        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        
        last_closed_price = closes[-1]
        
        ema9 = calculate_ema(closes, 9)
        ema21 = calculate_ema(closes, 21)
        ema200 = calculate_ema(closes, 200)
        rsi_now = calculate_rsi(closes, 14)
        macd_val, signal_val, hist_val = calculate_macd(closes)
        
        if not ema9 or not ema21 or not ema200:
            return False, last_closed_price, "EMA calculation failed"

        ema9_prev = calculate_ema(closes[:-1], 9)
        ema21_prev = calculate_ema(closes[:-1], 21)
        
        has_recent_crossover = (ema9_prev <= ema21_prev) and (ema9 > ema21)
        
        # شرط حجم التداول (يُفعل أو يُتجاوز حسب اختيار المستخدم)
        avg_volume = sum(volumes[-20:]) / 20 if len(volumes) >= 20 else 1.0
        is_volume_high = (volumes[-1] > (avg_volume * 1.2)) if check_volume else True
        
        # شرط RSI
        is_rsi_bullish = (30 < rsi_now < 60) if check_rsi else True
        
        # شرط MACD
        is_macd_bullish = (macd_val > signal_val and hist_val > 0) if check_macd else True

        if (
            has_recent_crossover
            and ema9 > ema21
            and ema21 > ema200
            and last_closed_price >= ema9
            and is_volume_high
            and is_rsi_bullish
            and is_macd_bullish
        ):
            return True, last_closed_price, "Signal conditions confirmed via Strategy"

        return False, last_closed_price, "Conditions not complete"

    except Exception as e:
        return False, 0.0, f"Error: {e}"