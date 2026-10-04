import time
import requests
from plyer import notification
from mexc_core import (
    get_top_symbols, check_trade_conditions_from_main, 
    get_setting, save_setting, place_market_buy, place_market_sell
)

def send_notification(title, message):
    try:
        notification.notify(title=title, message=message, app_name='Pro Scalping Mexc', timeout=10)
    except Exception as e:
        print(f"Notification error: {e}")

def main_service_loop():
    print("[SERVICE] Scalping Service Started...")
    active_trade = None

    while True:
        try:
            if str(get_setting("bot_active", "1")) == "0":
                save_setting("last_scan_status", "Bot is PAUSED")
                time.sleep(3)
                continue

            # استجابة لإغلاق الصفقة يدوياً
            if str(get_setting("manual_close_trigger", "0")) == "1":
                if active_trade:
                    symbol = active_trade["symbol"]
                    qty = active_trade.get("quantity", 0)
                    if qty > 0:
                        place_market_sell(symbol, qty)
                    send_notification("Manual Close", f"Closed active trade for {symbol} manually.")
                    active_trade = None
                    save_setting("active_trade_symbol", "")
                save_setting("manual_close_trigger", "0")

            limit = int(get_setting("scan_limit", 200))
            trade_amount = float(get_setting("amount", 79))
            use_rsi = str(get_setting("use_rsi", "1")) == "1"
            use_macd = str(get_setting("use_macd", "0")) == "1"
            use_volume = str(get_setting("use_volume", "1")) == "1"
            
            trail_activation_pct = float(get_setting("trail_activation", "1.0"))
            trail_callback_pct = float(get_setting("trail_callback", "0.4"))

            # متابعة الصفقة القائمة بالإيقاف المتحرك
            if active_trade:
                symbol = active_trade["symbol"]
                entry_price = active_trade["entry_price"]
                peak_price = active_trade["peak_price"]
                current_stop = active_trade["current_stop"]
                qty = active_trade.get("quantity", 0)
                
                res = requests.get(f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}", timeout=5)
                if res.status_code == 200:
                    current_price = float(res.json().get("price", entry_price))
                    
                    if current_price > peak_price:
                        active_trade["peak_price"] = current_price
                        peak_price = current_price
                    
                    profit_pct = ((peak_price - entry_price) / entry_price) * 100
                    if profit_pct >= trail_activation_pct:
                        new_stop = peak_price * (1 - (trail_callback_pct / 100.0))
                        if new_stop > current_stop:
                            active_trade["current_stop"] = new_stop
                    
                    stop_msg = f"Holding {symbol} | Price: ${current_price:.5f} | Stop: ${active_trade['current_stop']:.5f}"
                    save_setting("last_scan_status", stop_msg)
                    
                    if current_price <= active_trade["current_stop"]:
                        msg = f"Trailing Stop hit for {symbol} at ${current_price:.5f}"
                        if qty > 0:
                            place_market_sell(symbol, qty)
                        send_notification("Trade Closed (Trailing Stop)", msg)
                        active_trade = None
                        save_setting("active_trade_symbol", "")
                
                time.sleep(2)
                continue

            # فحص العملات وإرسال سبب القبول أو الرفض للواجهة
            symbols = get_top_symbols(limit=limit)
            for symbol in symbols:
                if str(get_setting("bot_active", "1")) == "0":
                    break

                valid, price, msg = check_trade_conditions_from_main(
                    symbol, check_rsi=use_rsi, check_macd=use_macd, check_volume=use_volume
                )
                
                status_text = f"[{symbol}] ${price:.4f} -> {'✅ PASS' if valid else '❌ REJECT'}: {msg}"
                save_setting("last_scan_status", status_text)

                if valid:
                    order_res = place_market_buy(symbol, trade_amount)
                    bought_qty = float(order_res.get("origQty", 0)) if order_res and "origQty" in order_res else 0.0

                    send_notification("New Trade Executed!", f"Bought {symbol} at ${price:.5f}")
                    
                    initial_sl = price * (1 - 0.015)
                    active_trade = {
                        "symbol": symbol,
                        "entry_price": price,
                        "peak_price": price,
                        "current_stop": initial_sl,
                        "quantity": bought_qty
                    }
                    save_setting("active_trade_symbol", symbol)
                    break
                    
                time.sleep(0.3)
                
            time.sleep(5)
            
        except Exception as e:
            print(f"[SERVICE ERROR]: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main_service_loop()