import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.checkbox import CheckBox
from kivy.utils import platform
from kivy.metrics import dp

from mexc_core import save_setting, get_setting

class TradingBotUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=dp(10), spacing=dp(8), **kwargs)
        self.build_ui()
        self.load_settings()

    def build_ui(self):
        cfg_grid = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(250))
        
        cfg_grid.add_widget(Label(text="API Key:"))
        self.api_key = TextInput(text="", multiline=False, password=True)
        cfg_grid.add_widget(self.api_key)

        cfg_grid.add_widget(Label(text="Secret Key:"))
        self.secret_key = TextInput(text="", multiline=False, password=True)
        cfg_grid.add_widget(self.secret_key)

        cfg_grid.add_widget(Label(text="Scan Limit (Top Coins):"))
        self.scan_limit = TextInput(text="200", multiline=False, input_filter="int")
        cfg_grid.add_widget(self.scan_limit)

        cfg_grid.add_widget(Label(text="Trade Amount ($):"))
        self.amount = TextInput(text="79", multiline=False, input_filter="float")
        cfg_grid.add_widget(self.amount)

        cfg_grid.add_widget(Label(text="Trail Activation %:"))
        self.trail_act = TextInput(text="1.0", multiline=False, input_filter="float")
        cfg_grid.add_widget(self.trail_act)

        cfg_grid.add_widget(Label(text="Trail Callback %:"))
        self.trail_cb = TextInput(text="0.4", multiline=False, input_filter="float")
        cfg_grid.add_widget(self.trail_cb)

        self.add_widget(cfg_grid)

        # خيارات الشروط
        cond_grid = GridLayout(cols=6, spacing=dp(4), size_hint_y=None, height=dp(35))
        cond_grid.add_widget(Label(text="RSI:"))
        self.ui_use_rsi = CheckBox(active=True)
        cond_grid.add_widget(self.ui_use_rsi)
        
        cond_grid.add_widget(Label(text="MACD:"))
        self.ui_use_macd = CheckBox(active=False)
        cond_grid.add_widget(self.ui_use_macd)

        cond_grid.add_widget(Label(text="Volume:"))
        self.ui_use_volume = CheckBox(active=True)
        cond_grid.add_widget(self.ui_use_volume)
        self.add_widget(cond_grid)

        # أزرار التشغيل والإيقاف
        btn_grid = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(50))
        
        self.start_btn = Button(text="Start Scan / Service", background_color=(0.2, 0.8, 0.2, 1))
        self.start_btn.bind(on_press=self.start_scan)
        btn_grid.add_widget(self.start_btn)

        self.stop_btn = Button(text="Stop Scan", background_color=(0.8, 0.2, 0.2, 1))
        self.stop_btn.bind(on_press=self.stop_scan)
        btn_grid.add_widget(self.stop_btn)
        self.add_widget(btn_grid)

        # زر إغلاق الصفقة يدوياً
        self.manual_close_btn = Button(
            text="Close Active Position Manually", 
            size_hint_y=None, 
            height=dp(45),
            background_color=(0.9, 0.5, 0.1, 1)
        )
        self.manual_close_btn.bind(on_press=self.close_position_manual)
        self.add_widget(self.manual_close_btn)

        self.log_label = Label(text="Bot Status: Ready...", size_hint_y=1)
        self.add_widget(self.log_label)

    def save_ui_settings(self):
        save_setting("api_key", self.api_key.text.strip())
        save_setting("secret_key", self.secret_key.text.strip())
        save_setting("scan_limit", self.scan_limit.text.strip())
        save_setting("amount", self.amount.text.strip())
        save_setting("trail_activation", self.trail_act.text.strip())
        save_setting("trail_callback", self.trail_cb.text.strip())
        save_setting("use_rsi", "1" if self.ui_use_rsi.active else "0")
        save_setting("use_macd", "1" if self.ui_use_macd.active else "0")
        save_setting("use_volume", "1" if self.ui_use_volume.active else "0")

    def load_settings(self):
        self.api_key.text = str(get_setting("api_key", ""))
        self.secret_key.text = str(get_setting("secret_key", ""))
        self.scan_limit.text = str(get_setting("scan_limit", "200"))
        self.amount.text = str(get_setting("amount", "79"))
        self.trail_act.text = str(get_setting("trail_activation", "1.0"))
        self.trail_cb.text = str(get_setting("trail_callback", "0.4"))
        self.ui_use_rsi.active = str(get_setting("use_rsi", "1")) == "1"
        self.ui_use_macd.active = str(get_setting("use_macd", "0")) == "1"
        self.ui_use_volume.active = str(get_setting("use_volume", "1")) == "1"

    def start_scan(self, instance):
        self.save_ui_settings()
        save_setting("bot_active", "1")
        
        if platform == 'android':
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Intent = autoclass('android.content.Intent')
                PythonService = autoclass('org.kivy.android.PythonService')
                
                activity = PythonActivity.mActivity
                intent = Intent(activity, PythonService)
                intent.putExtra('python.service.argument', 'service.py')
                activity.startService(intent)
                
                self.log_label.text = "Status: Bot & Service Running..."
            except Exception as e:
                self.log_label.text = f"Error starting service:\n{type(e).__name__}: {str(e)}"
        else:
            self.log_label.text = "Status: Running on Desktop (Bot Active)."

    def stop_scan(self, instance):
        save_setting("bot_active", "0")
        if platform == 'android':
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                Intent = autoclass('android.content.Intent')
                PythonService = autoclass('org.kivy.android.PythonService')
                
                activity = PythonActivity.mActivity
                intent = Intent(activity, PythonService)
                activity.stopService(intent)
            except Exception as e:
                print(f"Error stopping service: {e}")
        self.log_label.text = "Status: Scanning Stopped."

    def close_position_manual(self, instance):
        save_setting("manual_close_trigger", "1")
        self.log_label.text = "Status: Sent Manual Close Signal!"

class ProScalpingMexcApp(App):
    def build(self):
        return TradingBotUI()

if __name__ == '__main__':
    ProScalpingMexcApp().run()