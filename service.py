import time
import requests
from plyer import notification
from mexc_core import get_top_symbols, check_trade_conditions_from_main, get_setting

def send_notification(title, message):
    try:
        notification.notify(title=title, message=message, app_name='Pro Scalping Mexc', timeout=10)
    except Exception as e:
        print(f"Notification error: {e}")

def main_service_loop():
    print("[SERVICE] Starting Pro Scalping Service with Trailing Stop...")
    active_trade = None
    
    while True:
        try:
            # 1. قراءة إعدادات المستخدم من الملف المشترك
            limit = int(get_setting("scan_limit", 200))
            use_rsi = str(get_setting("use_rsi", "1")) == "1"
            use_macd = str(get_setting("use_macd", "0")) == "1"
            use_volume = str(get_setting("use_volume", "1")) == "1"
            
            trail_activation_pct = float(get_setting("trail_activation", "1.0"))
            trail_callback_pct = float(get_setting("trail_callback", "0.4"))

            # 2. إذا كانت هناك صفقة مفتوحة، قم بمتابعتها بنظام الإيقاف المتحرك
            if active_trade:
                symbol = active_trade["symbol"]
                entry_price = active_trade["entry_price"]
                peak_price = active_trade["peak_price"]
                current_stop = active_trade["current_stop"]
                
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
                            print(f"[TRAILING] Updated Stop Loss for {symbol} to ${new_stop:.5f} (Peak: ${peak_price})")
                    
                    if current_price <= active_trade["current_stop"]:
                        msg = f"Trailing Stop hit for {symbol} at ${current_price:.5f}!"
                        print(f"[CLOSED] {msg}")
                        send_notification("Trade Closed (Trailing Stop)", msg)
                        active_trade = None
                
                time.sleep(2)
                continue

            # 3. البحث عن صفقات جديدة بناءً على الشروط المفعلة
            symbols = get_top_symbols(limit=limit)
            if not symbols:
                time.sleep(5)
                continue
                
            for symbol in symbols:
                valid, price, msg = check_trade_conditions_from_main(
                    symbol, 
                    check_rsi=use_rsi, 
                    check_macd=use_macd, 
                    check_volume=use_volume
                )
                
                if valid:
                    notify_msg = f"{symbol} | Entry Price: ${price:.5f}\nTrailing Stop Active."
                    print(f"[SIGNAL] {notify_msg}")
                    send_notification("New Scalp Entry!", notify_msg)
                    
                    initial_sl = price * (1 - 0.015)
                    active_trade = {
                        "symbol": symbol,
                        "entry_price": price,
                        "peak_price": price,
                        "current_stop": initial_sl
                    }
                    break
                    
                time.sleep(0.3)
                
            time.sleep(10)
            
        except Exception as e:
            print(f"[SERVICE ERROR]: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main_service_loop()