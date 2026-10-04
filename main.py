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
        super().__init__(orientation='vertical', padding=dp(10), spacing=dp(10), **kwargs)
        self.build_ui()
        self.load_settings()

    def build_ui(self):
        # شبكة إعدادات العملات والمبالغ
        cfg_grid = GridLayout(cols=2, spacing=dp(6), size_hint_y=None, height=dp(100))
        
        cfg_grid.add_widget(Label(text="Scan Limit (Top Coins):"))
        self.scan_limit = TextInput(text="200", multiline=False, input_filter="int")
        cfg_grid.add_widget(self.scan_limit)

        cfg_grid.add_widget(Label(text="Trade Amount ($):"))
        self.amount = TextInput(text="79", multiline=False, input_filter="float")
        cfg_grid.add_widget(self.amount)

        self.add_widget(cfg_grid)

        # شبكة تفعيل المؤشرات
        cond_grid = GridLayout(cols=4, spacing=dp(6), size_hint_y=None, height=dp(50))
        
        cond_grid.add_widget(Label(text="Use RSI:"))
        self.ui_use_rsi = CheckBox(active=True)
        cond_grid.add_widget(self.ui_use_rsi)
        
        cond_grid.add_widget(Label(text="Use MACD:"))
        self.ui_use_macd = CheckBox(active=False)
        cond_grid.add_widget(self.ui_use_macd)
        
        self.add_widget(cond_grid)

        # زر التشغيل
        self.start_btn = Button(text="Save & Start Background Scan", size_hint_y=None, height=dp(60))
        self.start_btn.bind(on_press=self.start_scan)
        self.add_widget(self.start_btn)

        self.log_label = Label(text="Bot Status: Waiting for user...", size_hint_y=1)
        self.add_widget(self.log_label)

    def save_ui_settings(self):
        save_setting("scan_limit", self.scan_limit.text.strip())
        save_setting("amount", self.amount.text.strip())
        save_setting("use_rsi", "1" if self.ui_use_rsi.active else "0")
        save_setting("use_macd", "1" if self.ui_use_macd.active else "0")

    def load_settings(self):
        self.scan_limit.text = str(get_setting("scan_limit", "200"))
        self.amount.text = str(get_setting("amount", "79"))
        self.ui_use_rsi.active = str(get_setting("use_rsi", "1")) == "1"
        self.ui_use_macd.active = str(get_setting("use_macd", "0")) == "1"

    def start_scan(self, instance):
        self.save_ui_settings()
        
        if platform == 'android':
            try:
                from jnius import autoclass
                PythonActivity = autoclass('org.kivy.android.PythonActivity')
                
                # هام جداً: يجب أن يتطابق مع (package.domain) + (package.name) في buildozer
                # في هذا المثال: org.mexc.bot
                Service = autoclass('org.mexc.bot.ServiceScanner') 
                
                mActivity = PythonActivity.mActivity
                Service.start(mActivity, 'Bot is scanning in background...')
                self.log_label.text = "Success! Background service started."
            except Exception as e:
                self.log_label.text = f"Error starting service:\n{e}"
        else:
            self.log_label.text = "This bot is currently optimized for Android Background Service."

class BotApp(App):
    def build(self):
        return TradingBotUI()

if __name__ == '__main__':
    BotApp().run()
