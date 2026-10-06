"""Core MEXC Spot API, settings storage, indicators and order helpers."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.parse
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

BASE_URL = "https://api.mexc.com/api/v3"
BASE_DIR = Path(__file__).resolve().parent
SETTINGS_FILE = BASE_DIR / "settings.json"
LOCK_FILE = BASE_DIR / "settings.json.lock"

_REQUEST_TIMEOUT = 8


class MexcAPIError(RuntimeError):
    """A known MEXC API error."""


class MexcOrderUnknownError(MexcAPIError):
    """The order request could not be confirmed; the order may have succeeded."""


def _as_decimal(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def _fmt_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    units = (value / step).to_integral_value(rounding=ROUND_DOWN)
    return units * step


@contextmanager
def _settings_lock(timeout: float = 4.0):
    """Cross-process lock using an atomic lock file (works on Windows/Linux/Android)."""
    deadline = time.monotonic() + timeout
    fd = None
    while fd is None:
        try:
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
        except FileExistsError:
            try:
                age = time.time() - LOCK_FILE.stat().st_mtime
                if age > 15:
                    LOCK_FILE.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for settings lock")
            time.sleep(0.03)
    try:
        yield
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            LOCK_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def _read_settings_unlocked() -> Dict[str, Any]:
    if not SETTINGS_FILE.exists():
        return {}
    for _ in range(3):
        try:
            raw = SETTINGS_FILE.read_text(encoding="utf-8")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            time.sleep(0.03)
    return {}


def load_all_settings() -> Dict[str, Any]:
    try:
        return _read_settings_unlocked()
    except Exception:
        return {}


def save_settings(updates: Dict[str, Any]) -> bool:
    """Merge settings atomically so UI/service cannot corrupt or lose each other's keys."""
    if not isinstance(updates, dict):
        raise TypeError("updates must be a dict")
    try:
        with _settings_lock():
            settings = _read_settings_unlocked()
            settings.update(updates)
            tmp_path = SETTINGS_FILE.with_suffix(".json.tmp")
            tmp_path.write_text(
                json.dumps(settings, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            with tmp_path.open("rb") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp_path, SETTINGS_FILE)
        return True
    except Exception as exc:
        print(f"Error saving settings: {exc}")
        return False


def save_setting(key: str, value: Any) -> bool:
    return save_settings({key: value})


def get_setting(key: str, default_value: Any = None) -> Any:
    return load_all_settings().get(key, default_value)


def _public_request(method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    response = requests.request(
        method,
        f"{BASE_URL}{endpoint}",
        params=params or {},
        timeout=_REQUEST_TIMEOUT,
        headers={"User-Agent": "Pro-Scalping-Mexc/1.1", "Accept": "application/json"},
    )
    if response.status_code >= 500:
        raise MexcAPIError(f"MEXC server error HTTP {response.status_code}")
    try:
        data = response.json()
    except ValueError as exc:
        raise MexcAPIError(f"Invalid MEXC response HTTP {response.status_code}") from exc
    if response.status_code >= 400:
        message = data.get("msg") or data.get("message") or f"HTTP {response.status_code}"
        raise MexcAPIError(str(message))
    return data


def _signed_request(method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    api_key = str(get_setting("api_key", "")).strip()
    secret_key = str(get_setting("secret_key", "")).strip()
    if not api_key or not secret_key:
        raise MexcAPIError("API Key or Secret Key is missing")

    payload = dict(params or {})
    payload.setdefault("recvWindow", 5000)
    payload["timestamp"] = int(time.time() * 1000)
    query_string = urllib.parse.urlencode(payload, doseq=True)
    signature = hmac.new(secret_key.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()
    url = f"{BASE_URL}{endpoint}?{query_string}&signature={signature}"

    try:
        response = requests.request(
            method,
            url,
            timeout=_REQUEST_TIMEOUT,
            headers={"X-MEXC-APIKEY": api_key, "Content-Type": "application/json"},
        )
    except requests.RequestException as exc:
        raise MexcOrderUnknownError(f"Network error; order status may be unknown: {exc}") from exc

    if response.status_code >= 500:
        raise MexcOrderUnknownError(
            f"MEXC returned HTTP {response.status_code}; execution status is unknown"
        )
    try:
        data = response.json()
    except ValueError as exc:
        raise MexcAPIError(f"Invalid MEXC response HTTP {response.status_code}") from exc

    if response.status_code >= 400:
        message = data.get("msg") or data.get("message") or f"HTTP {response.status_code}"
        raise MexcAPIError(str(message))

    # Successful API calls normally have no error code. Treat a nonzero numeric code as failure.
    code = data.get("code") if isinstance(data, dict) else None
    if isinstance(code, int) and code not in (0, 200):
        message = data.get("msg") or data.get("message") or f"MEXC code {code}"
        raise MexcAPIError(str(message))
    return data if isinstance(data, dict) else {"data": data}


def get_server_time() -> int:
    data = _public_request("GET", "/time")
    return int(data.get("serverTime", int(time.time() * 1000)))


def get_ticker_price(symbol: str) -> float:
    data = _public_request("GET", "/ticker/price", {"symbol": symbol})
    return float(data.get("price", 0) or 0)


_EXCHANGE_INFO_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}


def get_exchange_info(symbol: Optional[str] = None) -> Dict[str, Any]:
    key = symbol or "__all__"
    cached = _EXCHANGE_INFO_CACHE.get(key)
    if cached and (time.monotonic() - cached[0]) < 60:
        return cached[1]
    params = {"symbol": symbol} if symbol else None
    data = _public_request("GET", "/exchangeInfo", params)
    if isinstance(data, dict) and isinstance(data.get("data"), (dict, list)):
        data = data["data"]
    if symbol and isinstance(data, dict) and "symbols" not in data and "symbol" in data:
        data = {"symbols": [data]}
    if isinstance(data, list):
        data = {"symbols": data}
    if not isinstance(data, dict):
        data = {"symbols": []}
    _EXCHANGE_INFO_CACHE[key] = (time.monotonic(), data)
    return data


def get_symbol_info(symbol: str) -> Dict[str, Any]:
    data = get_exchange_info(symbol)
    for item in data.get("symbols", []):
        if str(item.get("symbol", "")).upper() == symbol.upper():
            return item
    raise MexcAPIError(f"Symbol information not found: {symbol}")


def get_top_symbols(limit: int = 100) -> List[str]:
    limit = max(1, min(int(limit), 500))
    info = get_exchange_info()
    allowed: Dict[str, Dict[str, Any]] = {}
    for item in info.get("symbols", []):
        symbol = str(item.get("symbol", "")).upper()
        if not symbol.endswith("USDT"):
            continue
        status = str(item.get("status", "")).upper()
        online = status in {"1", "ENABLED", "ONLINE", "TRADING"}
        if not online:
            continue
        if item.get("isSpotTradingAllowed") is False:
            continue
        order_types = {str(x).upper() for x in (item.get("orderTypes") or [])}
        if "MARKET" not in order_types:
            continue
        trade_side = str(item.get("tradeSideType", "1"))
        if trade_side not in {"1", "2"}:
            continue
        allowed[symbol] = item

    data = _public_request("GET", "/ticker/24hr")
    if isinstance(data, dict):
        data = data.get("data", data.get("ticker", []))
    if not isinstance(data, list):
        return []

    ranked: List[Tuple[str, float]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).replace("/", "").upper()
        if symbol not in allowed:
            continue
        try:
            volume = float(item.get("quoteVolume", item.get("quoteVol", 0)) or 0)
        except (TypeError, ValueError):
            volume = 0.0
        ranked.append((symbol, volume))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return [symbol for symbol, _ in ranked[:limit]]


def _extract_klines(data: Any) -> List[list]:
    if isinstance(data, dict):
        data = data.get("data", data.get("klines", []))
    return data if isinstance(data, list) else []


def get_klines(symbol: str, interval: str = "15m", limit: int = 210) -> List[list]:
    return _extract_klines(_public_request("GET", "/klines", {"symbol": symbol, "interval": interval, "limit": limit}))


def calculate_ema(prices: Iterable[float], period: int) -> Optional[float]:
    prices = [float(p) for p in prices]
    if period <= 0 or len(prices) < period:
        return None
    multiplier = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calculate_ema_series(prices: Iterable[float], period: int) -> List[float]:
    prices = [float(p) for p in prices]
    if period <= 0 or len(prices) < period:
        return []
    multiplier = 2.0 / (period + 1)
    ema = sum(prices[:period]) / period
    values = [ema]
    for price in prices[period:]:
        ema = (price - ema) * multiplier + ema
        values.append(ema)
    return values


def calculate_rsi(prices: Iterable[float], period: int = 14) -> float:
    prices = [float(p) for p in prices]
    if len(prices) < period + 1:
        return 50.0
    gains: List[float] = []
    losses: List[float] = []
    for i in range(1, len(prices)):
        change = prices[i] - prices[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    return 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))


def calculate_macd(prices: Iterable[float]) -> Tuple[float, float, float]:
    """Proper MACD(12,26,9), not the previous synthetic 0.9 approximation."""
    prices = [float(p) for p in prices]
    if len(prices) < 35:
        return 0.0, 0.0, 0.0
    ema12 = calculate_ema_series(prices, 12)
    ema26 = calculate_ema_series(prices, 26)
    if not ema12 or not ema26:
        return 0.0, 0.0, 0.0
    # Align EMA12 with EMA26 by the shared endpoint sequence.
    offset = 26 - 12
    ema12_aligned = ema12[offset:]
    macd_series = [a - b for a, b in zip(ema12_aligned, ema26)]
    if len(macd_series) < 9:
        return macd_series[-1], macd_series[-1], 0.0
    signal_series = calculate_ema_series(macd_series, 9)
    macd_line = macd_series[-1]
    signal_line = signal_series[-1]
    return macd_line, signal_line, macd_line - signal_line

_EMA200_TREND_CACHE: Dict[Tuple[str, str], Tuple[float, bool]] = {}

def check_ema200_trend(formatted_symbol: str, interval: str) -> bool:
    """Require price above a rising EMA200 on the requested closed timeframe."""
    try:
        key = (formatted_symbol.upper(), interval)
        ttl = {"60m": 120.0, "15m": 60.0, "5m": 15.0}.get(interval, 30.0)
        cached = _EMA200_TREND_CACHE.get(key)
        now = time.monotonic()
        if cached and now - cached[0] < ttl:
            return cached[1]

        klines = get_klines(formatted_symbol, interval, 500)
        if not klines or len(klines) < 202:
            _EMA200_TREND_CACHE[key] = (now, False)
            return False

        closes = [float(k[4]) for k in klines[:-1]]
        ema200_series = calculate_ema_series(closes, 200)
        if len(ema200_series) < 2:
            _EMA200_TREND_CACHE[key] = (now, False)
            return False

        ema200_now = ema200_series[-1]
        ema200_prev = ema200_series[-2]
        result = closes[-1] > ema200_now and ema200_now > ema200_prev
        _EMA200_TREND_CACHE[key] = (now, result)
        return result
    except Exception:
        return False


def _ema_value_at_candle(
    ema_series: List[float],
    period: int,
    candle_index: int,
) -> Optional[float]:
    series_index = candle_index - (period - 1)
    if series_index < 0 or series_index >= len(ema_series):
        return None
    return ema_series[series_index]


def check_trade_conditions_from_main(
    symbol: str,
    check_rsi: bool = True,
    check_macd: bool = False,
    check_volume: bool = True,
) -> Tuple[bool, float, str]:
    """5m strategy gate; 1m is only used later to time the entry."""
    try:
        formatted_symbol = symbol.replace("/", "").upper()

        for interval, label in (("60m", "1h"), ("15m", "15m"), ("5m", "5m")):
            if not check_ema200_trend(formatted_symbol, interval):
                return False, 0.0, f"{label} EMA200 trend not bullish"

        klines = get_klines(formatted_symbol, "5m", 500)
        if not klines or len(klines) < 202:
            return False, 0.0, "Insufficient 5m kline data"

        closes_all = [float(k[4]) for k in klines]
        volumes_all = [float(k[5]) for k in klines]
        closes = closes_all[:-1]
        volumes = volumes_all[:-1]
        signal_price = closes[-1]

        ema9_series = calculate_ema_series(closes, 9)
        ema21_series = calculate_ema_series(closes, 21)
        if len(ema9_series) < 2 or len(ema21_series) < 2:
            return False, signal_price, "EMA calculation error"

        ema9_now = ema9_series[-1]
        ema21_now = ema21_series[-1]
        if ema9_now <= ema21_now:
            return False, signal_price, "5m EMA9 is not above EMA21"

        recent_candles = 4
        search_start = max(1, len(closes) - recent_candles)
        has_recent_crossover = False

        for candle_index in range(search_start, len(closes)):
            prev_index = candle_index - 1
            ema9_prev = _ema_value_at_candle(ema9_series, 9, prev_index)
            ema21_prev = _ema_value_at_candle(ema21_series, 21, prev_index)
            ema9_at = _ema_value_at_candle(ema9_series, 9, candle_index)
            ema21_at = _ema_value_at_candle(ema21_series, 21, candle_index)
            if None in (ema9_prev, ema21_prev, ema9_at, ema21_at):
                continue
            if ema9_prev <= ema21_prev and ema9_at > ema21_at:
                has_recent_crossover = True
                break

        if not has_recent_crossover:
            return False, signal_price, "No EMA9/EMA21 bullish crossover in last 4 closed 5m candles"

        if signal_price < ema9_now:
            return False, signal_price, "5m closed price is below EMA9"

        if check_volume:
            baseline = volumes[-21:-1]
            avg_vol = sum(baseline) / len(baseline) if baseline else 0.0
            if avg_vol <= 0 or volumes[-1] <= (avg_vol * 1.5):
                return False, signal_price, f"Low volume ({volumes[-1]:.0f} <= avg*1.5 {avg_vol*1.5:.0f})"

        rsi_now = calculate_rsi(closes, 14)
        if check_rsi and not (30 < rsi_now < 60):
            return False, signal_price, f"RSI out of bounds ({rsi_now:.1f})"

        macd_line, signal_line, hist = calculate_macd(closes)
        if check_macd and not (macd_line > signal_line and hist > 0):
            return False, signal_price, "MACD signal not bullish"

        return True, signal_price, "5m strategy passed; waiting for 1m entry trigger"
    except Exception as exc:
        return False, 0.0, f"Error: {exc}"


def check_1m_entry_trigger(symbol: str) -> Tuple[bool, float, str]:
    """Use 1m only to time entry after the 5m strategy has already passed."""
    try:
        formatted_symbol = symbol.replace("/", "").upper()
        klines = get_klines(formatted_symbol, "1m", 60)
        if not klines or len(klines) < 25:
            return False, 0.0, "Insufficient 1m kline data"

        closes_all = [float(k[4]) for k in klines]
        closes = closes_all[:-1]
        if len(closes) < 21:
            return False, 0.0, "Insufficient closed 1m candles"

        ema9_series = calculate_ema_series(closes, 9)
        ema21_series = calculate_ema_series(closes, 21)
        if not ema9_series or not ema21_series:
            return False, 0.0, "1m EMA calculation error"

        ema9_now = ema9_series[-1]
        ema21_now = ema21_series[-1]
        current_price = get_ticker_price(formatted_symbol)
        last_closed = closes[-1]

        if current_price <= 0:
            return False, 0.0, "Invalid 1m ticker price"
        if ema9_now <= ema21_now:
            return False, current_price, "1m EMA9 not above EMA21"
        if current_price <= ema9_now:
            return False, current_price, "1m price has not reclaimed EMA9"
        if current_price <= last_closed:
            return False, current_price, "1m continuation not confirmed"

        return True, current_price, "1m entry trigger confirmed"
    except Exception as exc:
        return False, 0.0, f"1m trigger error: {exc}"

def get_account_info() -> Dict[str, Any]:
    return _signed_request("GET", "/account")


def format_account_balances(account: Dict[str, Any], include_zero: bool = False) -> List[Dict[str, Any]]:
    balances = account.get("balances", []) if isinstance(account, dict) else []
    result: List[Dict[str, Any]] = []
    for item in balances:
        try:
            free = _as_decimal(item.get("free"))
            locked = _as_decimal(item.get("locked"))
        except Exception:
            continue
        if include_zero or free > 0 or locked > 0:
            result.append({
                "asset": str(item.get("asset", "")),
                "free": _fmt_decimal(free),
                "locked": _fmt_decimal(locked),
            })
    return result


def get_account_balances(include_zero: bool = False) -> List[Dict[str, Any]]:
    return format_account_balances(get_account_info(), include_zero=include_zero)


def get_free_balance(asset: str) -> Decimal:
    for item in get_account_balances(include_zero=True):
        if item["asset"].upper() == asset.upper():
            return _as_decimal(item["free"])
    return Decimal("0")


def _base_asset(symbol_info: Dict[str, Any], symbol: str) -> str:
    asset = str(symbol_info.get("baseAsset", "")).strip()
    if asset:
        return asset
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def _get_base_step(symbol_info: Dict[str, Any]) -> Decimal:
    value = symbol_info.get("baseSizePrecision")
    if value:
        return _as_decimal(value, "0.00000001")
    precision = symbol_info.get("baseAssetPrecision")
    if precision is not None:
        return Decimal(1).scaleb(-int(precision))
    return Decimal("0.00000001")


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _get_min_market_quote(symbol_info: Dict[str, Any]) -> Decimal:
    # MEXC documents this as the minimum market-order quote amount.
    value = symbol_info.get("quoteAmountPrecisionMarket")
    return _as_decimal(value, "0") if value not in (None, "") else Decimal("0")


def _get_max_market_quote(symbol_info: Dict[str, Any]) -> Decimal:
    value = symbol_info.get("maxQuoteAmountMarket")
    return _as_decimal(value, "0") if value not in (None, "") else Decimal("0")


def get_order(symbol: str, order_id: Optional[str] = None, client_order_id: Optional[str] = None) -> Dict[str, Any]:
    params: Dict[str, Any] = {"symbol": symbol}
    if order_id:
        params["orderId"] = order_id
    elif client_order_id:
        params["origClientOrderId"] = client_order_id
    else:
        raise ValueError("order_id or client_order_id is required")
    return _signed_request("GET", "/order", params)


def _confirm_order(symbol: str, initial: Dict[str, Any], client_order_id: str) -> Dict[str, Any]:
    order_id = str(initial.get("orderId", ""))
    latest = dict(initial)
    if order_id:
        for delay in (0.10, 0.20, 0.40, 0.80, 1.20):
            try:
                latest = get_order(symbol, order_id=order_id)
            except MexcAPIError:
                latest = initial
            status = str(latest.get("status", "")).upper()
            if status in {"FILLED", "PARTIALLY_FILLED", "CANCELED", "REJECTED", "EXPIRED"}:
                break
            time.sleep(delay)
    else:
        try:
            latest = get_order(symbol, client_order_id=client_order_id)
        except MexcAPIError:
            pass
    return latest


def _submit_market_order(symbol: str, side: str, *, quote_amount: Optional[Decimal] = None, quantity: Optional[Decimal] = None) -> Dict[str, Any]:
    side = side.upper()
    if side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")

    client_order_id = f"psm_{int(time.time() * 1000)}_{side.lower()}"
    params: Dict[str, Any] = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "newClientOrderId": client_order_id,
    }
    if quote_amount is not None:
        params["quoteOrderQty"] = _fmt_decimal(quote_amount)
    elif quantity is not None:
        params["quantity"] = _fmt_decimal(quantity)
    else:
        raise ValueError("quote_amount or quantity is required")

    try:
        response = _signed_request("POST", "/order", params)
    except MexcOrderUnknownError:
        # Never blindly submit a second order. The first may have reached the matching engine.
        try:
            recovered = get_order(symbol, client_order_id=client_order_id)
        except Exception:
            raise
        if recovered:
            return recovered
        raise

    response = _confirm_order(symbol, response, client_order_id)
    status = str(response.get("status", "FILLED")).upper()
    if status in {"REJECTED", "CANCELED", "EXPIRED"}:
        raise MexcAPIError(response.get("msg") or f"Order {status}")
    return response


def place_market_buy(symbol: str, usdt_amount: float) -> Dict[str, Any]:
    amount = _as_decimal(usdt_amount)
    if amount <= 0:
        raise MexcAPIError("Trade amount must be greater than zero")

    info = get_symbol_info(symbol)
    if info.get("isSpotTradingAllowed") is False:
        raise MexcAPIError(f"Spot API trading not allowed for {symbol}")
    order_types = {str(x).upper() for x in (info.get("orderTypes") or [])}
    if "MARKET" not in order_types:
        raise MexcAPIError(f"MARKET orders are not supported for {symbol}")

    quote_allowed = _as_bool(info.get("quoteOrderQtyMarketAllowed", False), False)
    min_quote = _get_min_market_quote(info)
    max_quote = _get_max_market_quote(info)
    if min_quote > 0 and amount < min_quote:
        raise MexcAPIError(f"Trade amount {amount} is below market minimum {min_quote}")
    if max_quote > 0 and amount > max_quote:
        raise MexcAPIError(f"Trade amount {amount} is above market maximum {max_quote}")

    if quote_allowed:
        return _submit_market_order(symbol, "BUY", quote_amount=amount)

    price = _as_decimal(get_ticker_price(symbol))
    if price <= 0:
        raise MexcAPIError(f"Invalid market price for {symbol}")
    step = _get_base_step(info)
    quantity = _floor_to_step(amount / price, step)
    if quantity <= 0:
        raise MexcAPIError(f"Trade amount is too small for {symbol} quantity precision")
    return _submit_market_order(symbol, "BUY", quantity=quantity)


def place_market_sell(symbol: str, quantity: Optional[float] = None) -> Dict[str, Any]:
    info = get_symbol_info(symbol)
    asset = _base_asset(info, symbol)
    free = get_free_balance(asset)
    requested = _as_decimal(quantity) if quantity is not None else free
    sellable = min(requested, free)
    step = _get_base_step(info)
    sellable = _floor_to_step(sellable, step)
    if sellable <= 0:
        raise MexcAPIError(f"No sellable balance for {asset}")
    return _submit_market_order(symbol, "SELL", quantity=sellable)


def order_average_price(order: Dict[str, Any], fallback_price: float = 0.0) -> float:
    executed = _as_decimal(order.get("executedQty"))
    quote = _as_decimal(order.get("cummulativeQuoteQty"))
    if executed > 0 and quote > 0:
        return float(quote / executed)
    return float(fallback_price)

