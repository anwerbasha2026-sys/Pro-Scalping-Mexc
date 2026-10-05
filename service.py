import os
import sys
import time

# 1. حل مشكلة مسار الاستيراد في أندرويد لضمان العثور على mexc_core.py
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# 2. محاولة استيراد الدوال مع اصتياد أخطاء الاستيراد
try:
    from mexc_core import (
        get_top_symbols, check_trade_conditions_from_main, 
        get_setting, save_setting, place_market_buy, place_market_sell
    )
except Exception as import_err:
    # كتابة الخطأ في ملف الإعدادات ليظهر بالواجهة فوراً
    try:
        import json
        settings_path = os.path.join(CURRENT_DIR, "settings.json")
        data = {}
        if os.path.exists(settings_path):
            with open(settings_path, "r") as f:
                data = json.load(f)
        data["last_scan_status"] = f"Import Error in service.py:\n{import_err}"
        with open(settings_path, "w") as f:
            json.dump(data, f)
    except:
        pass
    sys.exit(1)

def main_service_loop():
    # تحديث الواجهة فور بدء الخدمة الفعلية
    save_setting("last_scan_status", "Service Core Loaded. Starting scan loop...")
    active_trade = None

    while True:
        try:
            bot_active = str(get_setting("bot_active", "0"))
            if bot_active == "0":
                save_setting("last_scan_status", "Scan Stopped / Paused")
                time.sleep(2)
                continue

            limit = int(get_setting("scan_limit", 100))
            trade_amount = float(get_setting("amount", 20))
            use_rsi = str(get_setting("use_rsi", "1")) == "1"
            use_macd = str(get_setting("use_macd", "0")) == "1"
            use_volume = str(get_setting("use_volume", "1")) == "1"
            trail_act_pct = float(get_setting("trail_activation", "1.0"))
            trail_cb_pct = float(get_setting("trail_callback", "0.4"))

            # متابعة الصفقة إن وجدت
            if active_trade:
                symbol = active_trade["symbol"]
                entry_p = active_trade["entry_price"]
                peak_p = active_trade["peak_price"]
                stop_p = active_trade["current_stop"]
                qty = active_trade.get("quantity", 0)

                import requests
                res = requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}", timeout=5)
                if res.status_code == 200:
                    curr_p = float(res.json().get("price", entry_p))
                    if curr_p > peak_p:
                        active_trade["peak_price"] = curr_p
                        peak_p = curr_p

                    profit_pct = ((peak_p - entry_p) / entry_p) * 100
                    if profit_pct >= trail_act_pct:
                        new_stop = peak_p * (1 - (trail_cb_pct / 100.0))
                        if new_stop > stop_p:
                            active_trade["current_stop"] = new_stop

                    save_setting("last_scan_status", f"Holding {symbol} | Price: ${curr_p:.4f} | SL: ${active_trade['current_stop']:.4f}")

                    if curr_p <= active_trade["current_stop"]:
                        if qty > 0:
                            place_market_sell(symbol, qty)
                        active_trade = None
                        save_setting("last_scan_status", f"Closed {symbol} via Trailing Stop.")

                time.sleep(2)
                continue

            # جلب العملات
            save_setting("last_scan_status", "Fetching top coins from MEXC...")
            symbols = get_top_symbols(limit=limit)

            if not symbols:
                save_setting("last_scan_status", "Error: Symbol list is empty. Check internet connection.")
                time.sleep(4)
                continue

            # فحص العملات واختبار الشروط
            for symbol in symbols:
                if str(get_setting("bot_active", "0")) == "0":
                    break

                valid, price, msg = check_trade_conditions_from_main(
                    symbol, check_rsi=use_rsi, check_macd=use_macd, check_volume=use_volume
                )

                # تحديث اسم العملة المفحوصة فوراً على واجهة التطبيق
                status_text = f"Scanning: [{symbol}]\nPrice: ${price:.4f}\nStatus: {'✅ PASS' if valid else '❌ ' + msg}"
                save_setting("last_scan_status", status_text)

                if valid:
                    order_res = place_market_buy(symbol, trade_amount)
                    bought_qty = float(order_res.get("origQty", 0)) if order_res and "origQty" in order_res else 0.0

                    initial_sl = price * (1 - 0.015)
                    active_trade = {
                        "symbol": symbol,
                        "entry_price": price,
                        "peak_price": price,
                        "current_stop": initial_sl,
                        "quantity": bought_qty
                    }
                    save_setting("last_scan_status", f"✅ Trade Entered: {symbol} at ${price:.4f}")
                    break

                time.sleep(0.3)

            time.sleep(2)

        except Exception as loop_e:
            save_setting("last_scan_status", f"Service Loop Error:\n{loop_e}")
            time.sleep(4)

if __name__ == '__main__':
    try:
        main_service_loop()
    except Exception as main_e:
        from mexc_core import save_setting
        save_setting("last_scan_status", f"Fatal Service Crash:\n{main_e}")
