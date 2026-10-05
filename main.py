"""Kivy UI for Pro Scalping MEXC (Windows + Android)."""
from __future__ import annotations

import threading
from typing import Optional

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.utils import platform

from mexc_core import (
    MexcAPIError,
    format_account_balances,
    get_account_info,
    get_setting,
    load_all_settings,
    save_settings,
)

SERVICE_CLASS_NAME = "com.proscalpingmexc.proscalpingmexc.ServiceScanner"


class TradingBotUI(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), **kwargs)
        self.service_thread: Optional[threading.Thread] = None
        self.build_navigation()
        self.build_scanner_screen()
        self.build_live_trades_screen()
        self.build_account_screen()
        self.show_screen("scanner")
        self.load_settings()
        Clock.schedule_interval(self.update_status, 1.0)
        Clock.schedule_interval(self.refresh_account, 5.0)

    def build_navigation(self):
        nav = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(5))
        for key, title in (("scanner", "Scanner"), ("live", "Live Trades"), ("account", "Account")):
            btn = Button(text=title)
            btn.bind(on_press=lambda _btn, name=key: self.show_screen(name))
            nav.add_widget(btn)
        self.add_widget(nav)
        self.content = BoxLayout(orientation="vertical")
        self.add_widget(self.content)

    def _make_input(self, default="", password=False, numeric=False):
        return TextInput(
            text=str(default),
            multiline=False,
            password=password,
            input_filter="float" if numeric else None,
            size_hint_y=None,
            height=dp(38),
        )

    def build_scanner_screen(self):
        self.scanner = BoxLayout(orientation="vertical", spacing=dp(6))
        scroll = ScrollView()
        form = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, padding=dp(3))
        form.bind(minimum_height=form.setter("height"))

        def row(label, widget):
            form.add_widget(Label(text=label, size_hint_y=None, height=dp(38)))
            form.add_widget(widget)

        self.api_key = self._make_input(password=True)
        self.secret_key = self._make_input(password=True)
        self.scan_limit = self._make_input("100", numeric=False)
        self.amount = self._make_input("20", numeric=True)
        self.stop_loss = self._make_input("1.5", numeric=True)
        self.trail_act = self._make_input("1.0", numeric=True)
        self.trail_cb = self._make_input("0.4", numeric=True)
        self.take_profit = self._make_input("0", numeric=True)

        row("API Key", self.api_key)
        row("Secret Key", self.secret_key)
        row("Scan Limit (Top Coins)", self.scan_limit)
        row("Trade Amount (USDT)", self.amount)
        row("Stop Loss (%)", self.stop_loss)
        row("Trail Activation (%)", self.trail_act)
        row("Trail Callback (%)", self.trail_cb)
        row("Max Profit / Take Profit (%) — 0=Off", self.take_profit)

        self.ui_use_rsi = Button(text="RSI: ON", size_hint_y=None, height=dp(38))
        self.ui_use_macd = Button(text="MACD: OFF", size_hint_y=None, height=dp(38))
        self.ui_use_volume = Button(text="Volume: ON", size_hint_y=None, height=dp(38))
        self.ui_use_rsi.bind(on_press=lambda *_: self.toggle_bool("use_rsi", self.ui_use_rsi, "RSI"))
        self.ui_use_macd.bind(on_press=lambda *_: self.toggle_bool("use_macd", self.ui_use_macd, "MACD"))
        self.ui_use_volume.bind(on_press=lambda *_: self.toggle_bool("use_volume", self.ui_use_volume, "Volume"))
        row("Strategy Filter", self.ui_use_rsi)
        row("Strategy Filter", self.ui_use_macd)
        row("Strategy Filter", self.ui_use_volume)

        scroll.add_widget(form)
        self.scanner.add_widget(scroll)

        controls = GridLayout(cols=3, size_hint_y=None, height=dp(50), spacing=dp(5))
        save_btn = Button(text="Save Settings")
        save_btn.bind(on_press=lambda *_: self.save_ui_settings())
        start_btn = Button(text="Start Scan")
        start_btn.bind(on_press=lambda *_: self.start_scan())
        stop_btn = Button(text="Stop New Entries")
        stop_btn.bind(on_press=lambda *_: self.stop_scan())
        controls.add_widget(save_btn)
        controls.add_widget(start_btn)
        controls.add_widget(stop_btn)
        self.scanner.add_widget(controls)

        manual = Button(text="CLOSE REAL ACTIVE TRADE NOW", size_hint_y=None, height=dp(48))
        manual.bind(on_press=lambda *_: self.close_position_manual())
        self.scanner.add_widget(manual)

        self.status_label = Label(text="Live Status: Ready", halign="left", valign="top")
        self.status_label.bind(size=self.status_label.setter("text_size"))
        self.scanner.add_widget(self.status_label)

    def build_live_trades_screen(self):
        self.live = BoxLayout(orientation="vertical", spacing=dp(5))
        self.live_title = Label(text="REAL ACCOUNT / LIVE TRADES", size_hint_y=None, height=dp(40))
        self.live_body = Label(text="Loading...", halign="left", valign="top")
        self.live_body.bind(size=self.live_body.setter("text_size"))
        self.live.add_widget(self.live_title)
        self.live.add_widget(self.live_body)

    def build_account_screen(self):
        self.account = BoxLayout(orientation="vertical", spacing=dp(5))
        self.account_body = Label(text="Loading...", halign="left", valign="top")
        self.account_body.bind(size=self.account_body.setter("text_size"))
        self.account.add_widget(Label(text="PLATFORM BALANCE", size_hint_y=None, height=dp(40)))
        self.account.add_widget(self.account_body)

    def show_screen(self, name):
        self.content.clear_widgets()
        if name == "live":
            self.content.add_widget(self.live)
        elif name == "account":
            self.content.add_widget(self.account)
        else:
            self.content.add_widget(self.scanner)

    def toggle_bool(self, key, button, label):
        current = str(get_setting(key, "1" if label != "MACD" else "0")) == "1"
        new_value = "0" if current else "1"
        button.text = f"{label}: {'ON' if new_value == '1' else 'OFF'}"
        save_settings({key: new_value})

    def load_settings(self):
        settings = load_all_settings()
        self.api_key.text = str(settings.get("api_key", ""))
        self.secret_key.text = str(settings.get("secret_key", ""))
        self.scan_limit.text = str(settings.get("scan_limit", "100"))
        self.amount.text = str(settings.get("amount", "20"))
        self.stop_loss.text = str(settings.get("stop_loss_pct", "1.5"))
        self.trail_act.text = str(settings.get("trail_activation", "1.0"))
        self.trail_cb.text = str(settings.get("trail_callback", "0.4"))
        self.take_profit.text = str(settings.get("take_profit_pct", "0"))
        self._set_bool_button(self.ui_use_rsi, "RSI", settings.get("use_rsi", "1"))
        self._set_bool_button(self.ui_use_macd, "MACD", settings.get("use_macd", "0"))
        self._set_bool_button(self.ui_use_volume, "Volume", settings.get("use_volume", "1"))

    @staticmethod
    def _set_bool_button(button, label, value):
        button.text = f"{label}: {'ON' if str(value) == '1' else 'OFF'}"

    def save_ui_settings(self):
        try:
            scan_limit = max(1, int(self.scan_limit.text.strip() or "100"))
            amount = float(self.amount.text.strip())
            stop_loss = float(self.stop_loss.text.strip())
            trail_act = float(self.trail_act.text.strip())
            trail_cb = float(self.trail_cb.text.strip())
            take_profit = float(self.take_profit.text.strip())
            if amount <= 0:
                raise ValueError("Trade amount must be > 0")
            if stop_loss <= 0 or trail_act < 0 or trail_cb <= 0 or take_profit < 0:
                raise ValueError("Risk/trailing values are invalid")
            ok = save_settings({
                "api_key": self.api_key.text.strip(),
                "secret_key": self.secret_key.text.strip(),
                "scan_limit": str(scan_limit),
                "amount": str(amount),
                "stop_loss_pct": str(stop_loss),
                "trail_activation": str(trail_act),
                "trail_callback": str(trail_cb),
                "take_profit_pct": str(take_profit),
                "use_rsi": "1" if "ON" in self.ui_use_rsi.text else "0",
                "use_macd": "1" if "ON" in self.ui_use_macd.text else "0",
                "use_volume": "1" if "ON" in self.ui_use_volume.text else "0",
            })
            if not ok:
                raise RuntimeError("Settings file could not be saved")
            self.status_label.text = "Live Status:\n✅ Settings saved atomically."
            return True
        except Exception as exc:
            self.status_label.text = f"Live Status:\n❌ Settings error: {exc}"
            return False

    def _ensure_desktop_worker(self):
        if platform == "android":
            return
        if self.service_thread and self.service_thread.is_alive():
            return
        from service import main_service_loop
        self.service_thread = threading.Thread(target=main_service_loop, name="MEXC-Service", daemon=True)
        self.service_thread.start()

    def start_scan(self):
        if not self.save_ui_settings():
            return
        if not save_settings({"bot_active": "1", "manual_close_trigger": "0", "last_scan_status": "Starting scanner..."}):
            self.status_label.text = "Live Status:\n❌ Could not enable scanner because settings storage failed."
            return
        if platform == "android":
            try:
                from jnius import autoclass
                PythonActivity = autoclass("org.kivy.android.PythonActivity")
                ServiceScanner = autoclass(SERVICE_CLASS_NAME)
                activity = PythonActivity.mActivity
                ServiceScanner.start(activity, "")
                save_settings({"last_scan_status": "✅ Foreground scanner service started."})
            except Exception as exc:
                save_settings({"bot_active": "0", "last_scan_status": f"❌ Service start error: {exc}"})
        else:
            self._ensure_desktop_worker()
            save_settings({"last_scan_status": "✅ Windows scanner worker started."})

    def stop_scan(self):
        # Stop NEW entries but keep the worker alive so an existing real position can still exit safely.
        save_settings({"bot_active": "0", "last_scan_status": "New entries stopped; active position management remains enabled."})

    def close_position_manual(self):
        save_settings({"manual_close_trigger": "1", "last_scan_status": "🔔 Manual close requested."})
        if platform != "android":
            self._ensure_desktop_worker()

    def update_status(self, _dt):
        status = get_setting("last_scan_status", "Ready...")
        active = get_setting("active_trade", None)
        active_text = "No tracked real position."
        if isinstance(active, dict):
            active_text = (
                f"Tracked: {active.get('symbol')} | Entry ${float(active.get('entry_price', 0)):.8f} | "
                f"Qty {active.get('quantity', 0)}"
            )
        self.status_label.text = f"Live Status:\n{status}\n\n{active_text}"

    def refresh_account(self, _dt):
        try:
            account = get_account_info()
            balances = format_account_balances(account, include_zero=False)
            lines = []
            for item in balances:
                lines.append(f"{item['asset']}: free={item['free']} | locked={item['locked']}")
            text = "\n".join(lines) if lines else "No non-zero balances returned."
            self.live_body.text = text

            self.account_body.text = (
                f"Account type: {account.get('accountType', 'SPOT')}\n"
                f"Can trade: {account.get('canTrade')}\n"
                f"Can deposit: {account.get('canDeposit')}\n"
                f"Can withdraw: {account.get('canWithdraw')}\n\n{text}"
            )
        except Exception as exc:
            # Missing keys are normal before configuration; show the reason without crashing the UI.
            self.live_body.text = f"Account sync error:\n{exc}"
            self.account_body.text = f"Account sync error:\n{exc}"


class ProScalpingMexcApp(App):
    def build(self):
        return TradingBotUI()


if __name__ == "__main__":
    ProScalpingMexcApp().run()
