import math
import os
import sys
import threading
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from src.candles import CandleService
from src.config import Settings, get_settings
from src.database import normalize_ticker, parse_iso
from src.repositories import Repository


MIN_LOOKBACK = 90
CHART_HISTORY_POINTS = 80


class PredictionError(RuntimeError):
    pass


class Forecaster(Protocol):
    provider: str
    model_name: str

    def forecast(
        self,
        candles: list[dict[str, Any]],
        interval: str,
        horizon: int,
    ) -> list[dict[str, Any]]:
        ...


class KronosForecaster:
    provider = "kronos"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.model_name = settings.kronos_model_name
        self._lock = threading.Lock()
        self._predictor: Any | None = None

    def forecast(
        self,
        candles: list[dict[str, Any]],
        interval: str,
        horizon: int,
    ) -> list[dict[str, Any]]:
        predictor = self._load_predictor()
        try:
            import pandas as pd
        except Exception as exc:
            raise PredictionError(f"pandas is required for Kronos predictions: {exc}") from exc

        context = candles[-self.settings.kronos_max_context :]
        frame = pd.DataFrame(
            [
                {
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "volume": candle.get("volume") or 0.0,
                    "amount": candle.get("amount") or 0.0,
                }
                for candle in context
            ]
        )
        x_timestamp = pd.Series([pd.Timestamp(candle["timestamp"]) for candle in context])
        y_timestamp = pd.Series(
            [pd.Timestamp(timestamp) for timestamp in future_timestamps(context[-1]["timestamp"], interval, horizon)]
        )
        predicted = predictor.predict(
            df=frame,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=horizon,
            T=self.settings.kronos_temperature,
            top_p=self.settings.kronos_top_p,
            sample_count=max(1, self.settings.kronos_sample_count),
            verbose=False,
        )
        return normalize_forecast_rows(
            [
                {
                    "timestamp": timestamp.isoformat(),
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row.get("volume", 0.0),
                    "amount": row.get("amount", 0.0),
                }
                for timestamp, row in predicted.iterrows()
            ]
        )

    def _load_predictor(self) -> Any:
        if self._predictor is not None:
            return self._predictor
        with self._lock:
            if self._predictor is not None:
                return self._predictor
            repo_path = self.settings.kronos_repo_path
            if repo_path:
                repo_path = os.path.abspath(os.path.expanduser(repo_path))
                if repo_path not in sys.path:
                    sys.path.insert(0, repo_path)
            try:
                from model import Kronos, KronosPredictor, KronosTokenizer
            except Exception as exc:
                raise PredictionError(f"Kronos repository is not importable: {exc}") from exc

            try:
                tokenizer = KronosTokenizer.from_pretrained(self.settings.kronos_tokenizer_name)
                model = Kronos.from_pretrained(self.settings.kronos_model_name)
                self._predictor = KronosPredictor(
                    model,
                    tokenizer,
                    device=self.settings.kronos_device,
                    max_context=self.settings.kronos_max_context,
                )
            except Exception as exc:
                raise PredictionError(f"Kronos model could not be loaded: {exc}") from exc
            return self._predictor


class StatisticalForecaster:
    provider = "statistical"
    model_name = "ewma-trend-fallback"

    def forecast(
        self,
        candles: list[dict[str, Any]],
        interval: str,
        horizon: int,
    ) -> list[dict[str, Any]]:
        closes = [float(candle["close"]) for candle in candles]
        highs = [float(candle["high"]) for candle in candles]
        lows = [float(candle["low"]) for candle in candles]
        volumes = [float(candle.get("volume") or 0.0) for candle in candles[-30:]]
        returns = log_returns(closes[-90:])
        if not returns:
            raise PredictionError("not enough close prices for fallback forecast")

        recent_returns = returns[-20:]
        drift = weighted_average(recent_returns)
        volatility = standard_deviation(recent_returns) or standard_deviation(returns) or 0.01
        short_ma = mean(closes[-10:])
        long_ma = mean(closes[-40:]) if len(closes) >= 40 else mean(closes)
        trend_adjustment = clamp((short_ma - long_ma) / max(long_ma, 0.0001), -0.015, 0.015) / 5
        drift = clamp(drift + trend_adjustment, -volatility * 1.25, volatility * 1.25)

        average_volume = mean(volumes) if volumes else 0.0
        intraday_spread = mean(
            [
                (high - low) / close
                for high, low, close in zip(highs[-30:], lows[-30:], closes[-30:], strict=False)
                if close > 0
            ]
        )
        spread = max(intraday_spread, volatility * 1.35, 0.005)

        rows: list[dict[str, Any]] = []
        previous_close = closes[-1]
        for timestamp in future_timestamps(candles[-1]["timestamp"], interval, horizon):
            step_return = drift * 0.85
            close = previous_close * math.exp(step_return)
            open_price = previous_close
            high = max(open_price, close) * (1 + spread / 2)
            low = min(open_price, close) * (1 - spread / 2)
            volume = max(0.0, average_volume)
            amount = volume * ((open_price + high + low + close) / 4)
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "amount": amount,
                }
            )
            previous_close = close
        return normalize_forecast_rows(rows)


class DecisionSupportService:
    def __init__(
        self,
        repository: Repository | None = None,
        settings: Settings | None = None,
        candle_service: CandleService | None = None,
        kronos_forecaster: Forecaster | None = None,
        fallback_forecaster: Forecaster | None = None,
    ):
        self.settings = settings or get_settings()
        self.repository = repository or Repository(self.settings)
        self.candle_service = candle_service or CandleService(self.repository, self.settings)
        self.kronos_forecaster = kronos_forecaster or KronosForecaster(self.settings)
        self.fallback_forecaster = fallback_forecaster or StatisticalForecaster()

    def analysis(
        self,
        ticker: str,
        interval: str = "1d",
        range_name: str = "2y",
        horizon: int = 10,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        normalized = normalize_ticker(ticker)
        horizon = max(1, min(horizon, 60))
        lookback = max(MIN_LOOKBACK, min(self.settings.kronos_max_context, 512))
        cache_model_name = self.settings.kronos_model_name if self.settings.kronos_enabled else self.fallback_forecaster.model_name
        if not force_refresh:
            cached = self.repository.get_prediction_cache(
                normalized,
                interval,
                horizon,
                lookback,
                cache_model_name,
            )
            if cached:
                return cached

        candles = self.candle_service.history(
            normalized,
            interval=interval,
            range_name=range_name,
            limit=lookback,
            force_refresh=force_refresh,
        )
        if len(candles) < MIN_LOOKBACK:
            raise PredictionError(f"at least {MIN_LOOKBACK} candles are required")

        warnings = [
            "Forecasts are probabilistic and can be wrong.",
            "This is decision support, not investment advice.",
            "Yahoo chart data may be delayed or incomplete.",
        ]
        forecaster = self.fallback_forecaster
        if self.settings.kronos_enabled:
            try:
                forecast = self.kronos_forecaster.forecast(candles, interval, horizon)
                forecaster = self.kronos_forecaster
            except PredictionError as exc:
                if self.settings.kronos_required:
                    raise
                warnings.append(f"Kronos unavailable; using statistical fallback: {exc}")
                forecast = self.fallback_forecaster.forecast(candles, interval, horizon)
        else:
            forecast = self.fallback_forecaster.forecast(candles, interval, horizon)

        response = self._decision_payload(
            normalized,
            interval,
            horizon,
            lookback,
            candles,
            forecast,
            forecaster,
            warnings,
        )
        self.repository.save_prediction_cache(
            normalized,
            interval,
            horizon,
            lookback,
            cache_model_name,
            response,
            ttl_seconds=self.settings.prediction_cache_ttl_seconds,
        )
        return response

    def _decision_payload(
        self,
        ticker: str,
        interval: str,
        horizon: int,
        lookback: int,
        candles: list[dict[str, Any]],
        forecast: list[dict[str, Any]],
        forecaster: Forecaster,
        warnings: list[str],
    ) -> dict[str, Any]:
        closes = [float(candle["close"]) for candle in candles]
        highs = [float(candle["high"]) for candle in candles]
        lows = [float(candle["low"]) for candle in candles]
        last_close = closes[-1]
        target_price = float(forecast[-1]["close"])
        forecast_lows = [float(point["low"]) for point in forecast]
        forecast_highs = [float(point["high"]) for point in forecast]
        expected_change = percent_change(last_close, target_price)
        forecast_low_percent = percent_change(last_close, min(forecast_lows))
        forecast_high_percent = percent_change(last_close, max(forecast_highs))
        support_price = min(lows[-60:])
        resistance_price = max(highs[-60:])
        daily_volatility = standard_deviation(log_returns(closes[-60:])) * 100
        realized_volatility = daily_volatility * math.sqrt(252)
        range_width = forecast_high_percent - forecast_low_percent
        rsi_value = rsi(closes)
        sma20 = mean(closes[-20:])
        sma50 = mean(closes[-50:]) if len(closes) >= 50 else mean(closes)

        threshold = max(0.75, daily_volatility * math.sqrt(horizon) * 0.35)
        trend_confirmed_up = last_close >= sma20 >= sma50
        trend_confirmed_down = last_close <= sma20 <= sma50
        if expected_change >= threshold:
            outlook = "bullish"
        elif expected_change <= -threshold:
            outlook = "bearish"
        else:
            outlook = "neutral"

        if range_width >= 12 or realized_volatility >= 50:
            risk_level = "high"
        elif range_width >= 6 or realized_volatility >= 28:
            risk_level = "medium"
        else:
            risk_level = "low"

        signal_strength = min(abs(expected_change) / max(threshold, 0.01), 3.0)
        confidence = 0.42 + signal_strength * 0.1
        if outlook == "bullish" and trend_confirmed_up:
            confidence += 0.08
        if outlook == "bearish" and trend_confirmed_down:
            confidence += 0.08
        if risk_level == "high":
            confidence -= 0.08
        if risk_level == "low":
            confidence += 0.04
        confidence = round(clamp(confidence, 0.35, 0.82), 2)

        if outlook == "bullish":
            action = f"Watch for continuation above {resistance_price:.2f}; avoid chasing inside the forecast range."
            summary = f"{ticker} has an upside-biased forecast over the next {horizon} {interval} candles."
            stop_price = support_price * 0.99
            take_profit_price = max(target_price, resistance_price * 1.01)
        elif outlook == "bearish":
            action = f"Protect downside below {support_price:.2f}; wait for stabilization before adding exposure."
            summary = f"{ticker} has a downside-biased forecast over the next {horizon} {interval} candles."
            stop_price = support_price * 0.985
            take_profit_price = None
        else:
            action = f"Wait for a break outside {support_price:.2f}-{resistance_price:.2f} before acting."
            summary = f"{ticker} is range-bound in the current forecast window."
            stop_price = None
            take_profit_price = None

        drivers = [
            f"{forecaster.model_name} projects {expected_change:+.2f}% over {horizon} {interval} candles.",
            f"Forecast band runs from {forecast_low_percent:+.2f}% to {forecast_high_percent:+.2f}% versus last close.",
            f"Recent support is {support_price:.2f} and resistance is {resistance_price:.2f}.",
            f"20-period average is {sma20:.2f}; 50-period average is {sma50:.2f}.",
            f"RSI is {rsi_value:.1f}, with realized volatility near {realized_volatility:.1f}% annualized.",
        ]

        return {
            "ticker": ticker,
            "interval": interval,
            "horizon": horizon,
            "lookback": min(lookback, len(candles)),
            "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "source": "yahoo",
            "model_name": forecaster.model_name,
            "provider": forecaster.provider,
            "outlook": outlook,
            "risk_level": risk_level,
            "confidence": confidence,
            "last_close": round(last_close, 6),
            "target_price": round(target_price, 6),
            "expected_change_percent": round(expected_change, 4),
            "forecast_low_percent": round(forecast_low_percent, 4),
            "forecast_high_percent": round(forecast_high_percent, 4),
            "support_price": round(support_price, 6),
            "resistance_price": round(resistance_price, 6),
            "stop_price": round(stop_price, 6) if stop_price else None,
            "take_profit_price": round(take_profit_price, 6) if take_profit_price else None,
            "summary": summary,
            "action": action,
            "drivers": drivers,
            "warnings": warnings,
            "historical": candles[-CHART_HISTORY_POINTS:],
            "forecast": forecast,
        }


def normalize_forecast_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for row in rows:
        open_price = positive_float(row["open"])
        close_price = positive_float(row["close"])
        high_price = positive_float(row["high"])
        low_price = positive_float(row["low"])
        high_price = max(open_price, high_price, low_price, close_price)
        low_price = min(open_price, high_price, low_price, close_price)
        volume = max(0.0, float(row.get("volume") or 0.0))
        amount = max(0.0, float(row.get("amount") or 0.0))
        normalized.append(
            {
                "timestamp": iso_timestamp(row["timestamp"]),
                "open": round(open_price, 6),
                "high": round(high_price, 6),
                "low": round(low_price, 6),
                "close": round(close_price, 6),
                "volume": round(volume, 6),
                "amount": round(amount, 6),
            }
        )
    return normalized


def future_timestamps(last_timestamp: str, interval: str, horizon: int) -> list[str]:
    current = parse_iso(last_timestamp)
    if current is None:
        raise PredictionError("invalid last candle timestamp")
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC).replace(microsecond=0)

    result: list[str] = []
    for _ in range(horizon):
        if interval == "1wk":
            current = current + timedelta(days=7)
        elif interval == "1mo":
            current = add_month(current)
        else:
            current = next_business_day(current)
        result.append(current.isoformat())
    return result


def next_business_day(value: datetime) -> datetime:
    value = value + timedelta(days=1)
    while value.weekday() >= 5:
        value = value + timedelta(days=1)
    return value


def add_month(value: datetime) -> datetime:
    month = value.month + 1
    year = value.year
    if month == 13:
        month = 1
        year += 1
    max_days = [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    day = min(value.day, max_days[month - 1])
    return value.replace(year=year, month=month, day=day)


def iso_timestamp(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).replace(microsecond=0).isoformat()
    text = str(value)
    parsed = parse_iso(text)
    if parsed is None:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def positive_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise PredictionError("forecast produced invalid price")
    return number


def percent_change(base: float, value: float) -> float:
    if base == 0:
        return 0.0
    return ((value - base) / base) * 100


def log_returns(values: list[float]) -> list[float]:
    result: list[float] = []
    for previous, current in zip(values, values[1:], strict=False):
        if previous > 0 and current > 0:
            result.append(math.log(current / previous))
    return result


def rsi(closes: list[float], period: int = 14) -> float:
    returns = [current - previous for previous, current in zip(closes, closes[1:], strict=False)]
    recent = returns[-period:]
    if not recent:
        return 50.0
    gains = [value for value in recent if value > 0]
    losses = [-value for value in recent if value < 0]
    average_gain = mean(gains) if gains else 0.0
    average_loss = mean(losses) if losses else 0.0
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return round(100 - (100 / (1 + relative_strength)), 1)


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def weighted_average(values: list[float]) -> float:
    if not values:
        return 0.0
    total_weight = sum(range(1, len(values) + 1))
    return sum(value * weight for weight, value in enumerate(values, start=1)) / total_weight


def standard_deviation(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
