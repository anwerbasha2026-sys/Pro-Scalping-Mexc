import json
import os
import tempfile
from pathlib import Path

import mexc_core


def test_macd_uses_real_signal_ema():
    prices = [100.0] * 50 + [100 + i * 1.8 for i in range(1, 31)]
    macd, signal, hist = mexc_core.calculate_macd(prices)
    assert macd > signal
    assert abs(hist - (macd - signal)) < 1e-12


def test_order_average_price_uses_actual_fill():
    assert abs(mexc_core.order_average_price({"executedQty": "2", "cummulativeQuoteQty": "5.4"}) - 2.7) < 1e-12


def test_settings_merge_preserves_existing_keys(tmp_path):
    original = mexc_core.SETTINGS_FILE
    original_lock = mexc_core.LOCK_FILE
    try:
        mexc_core.SETTINGS_FILE = tmp_path / "settings.json"
        mexc_core.LOCK_FILE = tmp_path / "settings.json.lock"
        assert mexc_core.save_settings({"api_key": "a", "amount": "20"})
        assert mexc_core.save_settings({"bot_active": "1"})
        data = json.loads(mexc_core.SETTINGS_FILE.read_text())
        assert data == {"api_key": "a", "amount": "20", "bot_active": "1"}
    finally:
        mexc_core.SETTINGS_FILE = original
        mexc_core.LOCK_FILE = original_lock


def test_bool_parser_handles_api_string_flags():
    assert mexc_core._as_bool("true") is True
    assert mexc_core._as_bool("false") is False
    assert mexc_core._as_bool("1") is True
    assert mexc_core._as_bool("0") is False
