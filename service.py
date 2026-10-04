import time
from plyer import notification
from mexc_core import get_top_symbols, check_trade_conditions_from_main, get_setting

def send_notification(title, message):
    try:
        # تم تغيير app_name هنا إلى الاسم الجديد
        notification.notify(title=title, message=message, app_name='Pro Scalping Mexc', timeout=10)
    except Exception as e:
        print(f"Notification error: {e}")

def main_service_loop():
    print("[SERVICE] Starting Android Background Service...")
    while True:
        try:
            # 1. قراءة الإعدادات المحدثة من الواجهة
            limit = int(get_setting("scan_limit", 200))
            use_rsi = str(get_setting("use_rsi", "1")) == "1"
            use_macd = str(get_setting("use_macd", "0")) == "1"
            
            # 2. جلب العملات
            symbols = get_top_symbols(limit=limit)
            if not symbols:
                time.sleep(5)
                continue
                
            # 3. فحص الشروط
            for symbol in symbols:
                valid, price, msg = check_trade_conditions_from_main(symbol, check_rsi=use_rsi, check_macd=use_macd)
                
                if valid:
                    notify_msg = f"{symbol} | Price: ${price:.5f}\n{msg}"
                    print(f"[SIGNAL] {notify_msg}")
                    send_notification("New Trading Signal!", notify_msg)
                    
                time.sleep(0.3) # تجنب حظر الـ API
                
            # 4. الانتظار قبل الدورة التالية (مثلاً 30 ثانية)
            time.sleep(30)
            
        except Exception as e:
            print(f"[SERVICE ERROR]: {e}")
            time.sleep(5)

if __name__ == '__main__':
    main_service_loop()
