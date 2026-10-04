import requests
import json
import os

BASE_URL = "https://api.mexc.com/api/v3"
SETTINGS_FILE = "settings.json"

# --- دوال إدارة الإعدادات المشتركة بين الواجهة والخدمة ---
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

# --- دوال فحص العملات (التي تم تعديلها) ---
def get_top_symbols(limit=200):
    try:
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

def check_trade_conditions_from_main(symbol, check_rsi=True, check_macd=False):
    try:
        # ملاحظة: ضع هنا كود جلب الشموع والمؤشرات (Kline, MACD, RSI) الخاص بك
        # سأضع قيم افتراضية للتوضيح (يجب دمج كود المؤشرات الفني الخاص بك هنا)
        last_closed_price = 0.500
        rsi_now = 45.0
        macd_now = 0.1
        signal_now = 0.05
        hist_now = 0.05
        
        is_rsi_bullish = (30 < rsi_now < 60) if check_rsi else True
        is_macd_bullish = (macd_now > signal_now and hist_now > 0) if check_macd else True

        # افتراض أن باقي الشروط صحيحة للتوضيح (استبدلها بشروطك الحقيقية)
        conditions_met = is_rsi_bullish and is_macd_bullish

        if conditions_met:
            return True, last_closed_price, "Signal conditions confirmed"
        return False, last_closed_price, "Conditions not complete"

    except Exception as e:
        return False, 0.0, f"Error: {e}"
