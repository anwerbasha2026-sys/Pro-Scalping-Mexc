"""Background scanner/trade manager used by Android foreground service and Windows worker."""
from __future__ import annotations

import os
import sys
import time
from decimal import Decimal
from typing import Any, Dict, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from mexc_core import (  # noqa: E402
    MexcAPIError,
    MexcOrderUnknownError,
    check_trade_conditions_from_main,
    get_account_info,
    get_free_balance,
    get_setting,
    get_symbol_info,
    get_ticker_price,
    get_top_symbols,
    order_average_price,
    place_market_buy,
    place_market_sell,
    save_setting,
    save_settings,
)

POLL_SECONDS = 1.0
DEFAULT_STOP_LOSS = 1.5
DEFAULT_TRAIL_ACTIVATION = 1.0
DEFAULT_TRAIL_CALLBACK = 0.4
DEFAULT_TAKE_PROFIT = 0.0  # disabled by default; user config controls this.


def _dec(value: Any, default: float = 0.0) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(str(default))


def _load_active_trade() -> Optional[Dict[str, Any]]:
    trade = get_setting("active_trade", None)
    return trade if isinstance(trade, dict) and trade.get("symbol") else None


def _persist_trade(trade: Optional[Dict[str, Any]]) -> None:
    save_setting("active_trade", trade)


def _status(message: str) -> None:
    save_setting("last_scan_status", message)


def _restore_trade(trade: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not trade:
        return None
    try:
        symbol = str(trade["symbol"]).upper()
        info = get_symbol_info(symbol)
        asset = str(info.get("baseAsset") or symbol[:-4])
        free = get_free_balance(asset)
        if free <= 0:
            _status(f"Tracked position {symbol} no longer exists on the account.")
            _persist_trade(None)
            return None
        old_qty = _dec(trade.get("quantity"), 0)
        trade["quantity"] = float(min(old_qty if old_qty > 0 else free, free))
        trade["asset"] = asset
        return trade
    except Exception as exc:
        _status(f"Position restore check error: {exc}")
        return trade


def _close_trade(trade: Dict[str, Any], reason: str) -> bool:
    symbol = str(trade.get("symbol", "")).upper()
    if not symbol:
        _persist_trade(None)
        return True
    try:
        info = get_symbol_info(symbol)
        asset = str(info.get("baseAsset") or symbol[:-4])
        free = get_free_balance(asset)
        if free <= 0:
            _persist_trade(None)
            _status(f"{symbol} already closed externally.")
            return True
        _status(f"Closing {symbol} ({reason})...")
        order = place_market_sell(symbol, float(free))
        sold_qty = _dec(order.get("executedQty"), 0)
        if sold_qty <= 0:
            raise MexcAPIError("Sell order returned zero executed quantity")
        _persist_trade(None)
        save_settings({
            "last_closed_symbol": symbol,
            "last_closed_order_id": order.get("orderId"),
            "last_close_reason": reason,
            "last_close_time": int(time.time()),
            "manual_close_trigger": "0",
        })
        _status(f"✅ Closed {symbol} | Qty {sold_qty} | Reason: {reason}")
        return True
    except MexcOrderUnknownError as exc:
        _status(f"⚠️ Sell status unknown for {symbol}: {exc}")
        return False
    except Exception as exc:
        _status(f"❌ Close error {symbol}: {exc}")
        return False


def _manage_active_trade(trade: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    manual = str(get_setting("manual_close_trigger", "0")) == "1"
    if manual:
        if _close_trade(trade, "Manual close"):
            return None
        return trade

    symbol = str(trade["symbol"]).upper()
    try:
        current_price = get_ticker_price(symbol)
        if current_price <= 0:
            return trade

        entry = float(trade.get("entry_price", 0))
        if entry <= 0:
            _status(f"❌ Invalid entry price for {symbol}; position remains tracked.")
            return trade

        peak = max(float(trade.get("peak_price", entry)), current_price)
        stop = float(trade.get("current_stop", entry * (1 - DEFAULT_STOP_LOSS / 100)))
        trail_activation = float(get_setting("trail_activation", DEFAULT_TRAIL_ACTIVATION))
        trail_callback = float(get_setting("trail_callback", DEFAULT_TRAIL_CALLBACK))
        take_profit = float(get_setting("take_profit_pct", DEFAULT_TAKE_PROFIT))
        stop_loss = float(get_setting("stop_loss_pct", DEFAULT_STOP_LOSS))

        changed = peak != float(trade.get("peak_price", entry))
        trade["peak_price"] = peak

        # Do not hit the signed /account endpoint every second.  The saved fill
        # quantity is enough for monitoring; reconcile the real free balance only
        # periodically and always immediately before a sell.
        last_sync = float(trade.get("last_balance_sync", 0) or 0)
        if time.time() - last_sync >= 10.0:
            free = get_free_balance(str(trade.get("asset", symbol[:-4])))
            if free <= 0:
                _persist_trade(None)
                _status(f"{symbol} balance is now zero; position was closed outside the app.")
                return None
            saved_qty = _dec(trade.get("quantity"), 0)
            trade["quantity"] = float(min(saved_qty if saved_qty > 0 else free, free))
            trade["last_balance_sync"] = time.time()
            changed = True

        profit_pct = ((current_price - entry) / entry) * 100.0
        peak_profit_pct = ((peak - entry) / entry) * 100.0

        if changed and peak_profit_pct >= trail_activation:
            new_stop = peak * (1.0 - trail_callback / 100.0)
            if new_stop > stop:
                stop = new_stop
                trade["current_stop"] = stop
                changed = True

        # Always retain a defined initial stop in case the saved trade predates this version.
        if "current_stop" not in trade:
            stop = entry * (1.0 - stop_loss / 100.0)
            trade["current_stop"] = stop
            changed = True

        if current_price <= float(trade["current_stop"]):
            return None if _close_trade(trade, f"Stop/Trailing {profit_pct:.2f}%") else trade

        if take_profit > 0 and profit_pct >= take_profit:
            return None if _close_trade(trade, f"Take profit {profit_pct:.2f}%") else trade

        _status(
            f"Holding {symbol} | Price ${current_price:.8f} | P/L {profit_pct:.2f}% | "
            f"Peak {peak_profit_pct:.2f}% | SL ${float(trade['current_stop']):.8f}"
        )
        if changed:
            _persist_trade(trade)
        return trade
    except Exception as exc:
        _status(f"Position monitor error {symbol}: {exc}")
        return trade


def _enter_trade(symbol: str, signal_price: float, amount: float) -> Optional[Dict[str, Any]]:
    try:
        _status(f"🟢 Signal accepted for {symbol}; submitting market buy...")
        order = place_market_buy(symbol, amount)
        executed_qty = _dec(order.get("executedQty"), 0)
        if executed_qty <= 0:
            raise MexcAPIError(f"Buy order returned no executed quantity: {order}")
        entry_price = order_average_price(order, signal_price)
        info = get_symbol_info(symbol)
        asset = str(info.get("baseAsset") or symbol[:-4])
        stop_loss = float(get_setting("stop_loss_pct", DEFAULT_STOP_LOSS))
        trade = {
            "symbol": symbol,
            "asset": asset,
            "order_id": order.get("orderId"),
            "entry_price": entry_price,
            "signal_price": signal_price,
            "quantity": float(executed_qty),
            "peak_price": entry_price,
            "current_stop": entry_price * (1.0 - stop_loss / 100.0),
            "entry_time": int(time.time()),
            "last_balance_sync": time.time(),
        }
        _persist_trade(trade)
        save_settings({
            "manual_close_trigger": "0",
            "last_order_id": order.get("orderId"),
            "last_order_symbol": symbol,
            "last_order_entry_price": entry_price,
            "last_order_executed_qty": float(executed_qty),
        })
        _status(f"✅ Real trade entered: {symbol} @ ${entry_price:.8f} | Qty {executed_qty}")
        return trade
    except MexcOrderUnknownError as exc:
        # Safe behavior: do not retry a potentially successful order. Pause new entries.
        save_settings({
            "bot_active": "0",
            "manual_close_trigger": "0",
        })
        _status(f"⚠️ Buy order status unknown for {symbol}; new entries paused: {exc}")
        return None
    except Exception as exc:
        _status(f"❌ Buy failed for {symbol}: {exc}")
        return None


def main_service_loop() -> None:
    _status("Service core loaded. Starting scanner...")
    active_trade = _restore_trade(_load_active_trade())

    while True:
        try:
            # Manage an existing real position even when scanning is stopped.
            if active_trade:
                active_trade = _manage_active_trade(active_trade)
                if active_trade:
                    time.sleep(POLL_SECONDS)
                    continue

            # A manual close request with no tracked trade is simply consumed.
            if str(get_setting("manual_close_trigger", "0")) == "1":
                save_setting("manual_close_trigger", "0")
                _status("No tracked position to close.")

            bot_active = str(get_setting("bot_active", "0")) == "1"
            if not bot_active:
                time.sleep(2)
                continue

            try:
                limit = max(1, min(int(get_setting("scan_limit", 100)), 500))
                trade_amount = float(get_setting("amount", 20))
                use_rsi = str(get_setting("use_rsi", "1")) == "1"
                use_macd = str(get_setting("use_macd", "0")) == "1"
                use_volume = str(get_setting("use_volume", "1")) == "1"
            except (ValueError, TypeError) as exc:
                _status(f"❌ Invalid settings: {exc}")
                save_setting("bot_active", "0")
                time.sleep(2)
                continue

            if trade_amount <= 0:
                _status("❌ Trade amount must be greater than zero.")
                save_setting("bot_active", "0")
                time.sleep(2)
                continue

            try:
                symbols = get_top_symbols(limit)
            except Exception as exc:
                _status(f"❌ Symbol list error: {exc}")
                time.sleep(4)
                continue
            if not symbols:
                _status("No eligible USDT market-order symbols returned by MEXC.")
                time.sleep(4)
                continue

            for symbol in symbols:
                if str(get_setting("bot_active", "0")) != "1" or active_trade:
                    break
                valid, price, msg = check_trade_conditions_from_main(
                    symbol,
                    check_rsi=use_rsi,
                    check_macd=use_macd,
                    check_volume=use_volume,
                )
                _status(
                    f"Scanning [{symbol}]\nPrice ${price:.8f}\n"
                    f"Status: {'✅ PASS' if valid else '❌ ' + msg}"
                )
                if not valid:
                    time.sleep(0.10)
                    continue
                active_trade = _enter_trade(symbol, price, trade_amount)
                if active_trade:
                    break

            time.sleep(1.5)
        except Exception as exc:
            _status(f"❌ Service loop error: {exc}")
            time.sleep(4)


if __name__ == "__main__":
    try:
        main_service_loop()
    except Exception as exc:
        _status(f"Fatal Service Crash: {exc}")
