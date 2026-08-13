# pragma pylint: disable=missing-docstring
import talib.abstract as ta
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, DecimalParameter, IntParameter, stoploss_from_open
from pandas import DataFrame


class TrendFollowingStrategy(IStrategy):
    """
    EMA-cross trend-following strategy with ADX/RSI filters, ATR-based
    stoploss, and equity-risk-based position sizing under leverage.

    Designed for medium timeframe (4h) swing trading on Binance USDT-M
    Futures with low-to-medium risk: risk per trade is capped as a
    percentage of total account equity regardless of leverage, and
    trading pauses automatically after drawdown/loss-streak triggers
    (see `protections` below).
    """

    INTERFACE_VERSION = 3
    timeframe = "4h"

    can_short = True
    trading_mode = "futures"
    margin_mode = "isolated"

    # Fraction of total account equity risked on a single trade's stoploss.
    risk_per_trade = 0.015  # 1.5%
    max_leverage = 3.0

    # Hard fallback stoploss (price %); real stop is ATR-based via
    # custom_stoploss, this only bounds worst-case if that fails.
    stoploss = -0.12

    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.03
    trailing_only_offset_is_reached = True

    use_custom_stoploss = True
    # Once a trade's profit reaches this multiple of its initial ATR stop
    # distance, ratchet the stop to breakeven so a winner can no longer
    # round-trip back into a loss (see custom_stoploss below).
    breakeven_at_r_multiple = 1.0
    breakeven_buffer = 0.002  # 0.2% past entry, to cover fees/slippage

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    minimal_roi = {
        "0": 0.20,
        "1440": 0.10,
        "4320": 0.05,
    }

    startup_candle_count = 210

    ema_fast_period = IntParameter(10, 30, default=20, space="buy")
    ema_slow_period = IntParameter(40, 100, default=50, space="buy")
    adx_threshold = IntParameter(15, 35, default=25, space="buy")
    atr_stop_multiplier = DecimalParameter(1.5, 4.0, default=2.5, space="sell")

    protections = [
        {"method": "CooldownPeriod", "stop_duration_candles": 4},
        {
            "method": "StoplossGuard",
            "lookback_period_candles": 24,
            "trade_limit": 3,
            "stop_duration_candles": 12,
            "only_per_pair": False,
        },
        {
            "method": "MaxDrawdown",
            "lookback_period_candles": 48,
            "trade_limit": 10,
            "stop_duration_candles": 24,
            "max_allowed_drawdown": 0.10,
        },
    ]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=self.ema_fast_period.value)
        dataframe["ema_slow"] = ta.EMA(dataframe, timeperiod=self.ema_slow_period.value)
        dataframe["ema_trend"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # "Regime" = sustained trend condition (can hold for many candles),
        # separate from the entry trigger. This lets a single trend produce
        # more than one trade -- fresh breakout, then pullback resumptions
        # -- instead of only firing once at the exact EMA-cross candle.
        uptrend = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["close"] > dataframe["ema_trend"])
            & (dataframe["adx"] > self.adx_threshold.value)
        )
        downtrend = (
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["close"] < dataframe["ema_trend"])
            & (dataframe["adx"] > self.adx_threshold.value)
        )

        fresh_cross_up = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
        )
        pullback_resume_up = (
            uptrend
            & (dataframe["rsi"] > 45)
            & (dataframe["rsi"].shift(1) <= 45)
        )
        long_condition = (
            (fresh_cross_up | pullback_resume_up)
            & uptrend
            & (dataframe["rsi"] < 70)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[long_condition & fresh_cross_up, ["enter_long", "enter_tag"]] = (
            1, "ema_cross_up",
        )
        dataframe.loc[long_condition & ~fresh_cross_up, ["enter_long", "enter_tag"]] = (
            1, "pullback_resume_up",
        )

        fresh_cross_down = (
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
        )
        pullback_resume_down = (
            downtrend
            & (dataframe["rsi"] < 55)
            & (dataframe["rsi"].shift(1) >= 55)
        )
        short_condition = (
            (fresh_cross_down | pullback_resume_down)
            & downtrend
            & (dataframe["rsi"] > 30)
            & (dataframe["volume"] > 0)
        )
        dataframe.loc[short_condition & fresh_cross_down, ["enter_short", "enter_tag"]] = (
            1, "ema_cross_down",
        )
        dataframe.loc[short_condition & ~fresh_cross_down, ["enter_short", "enter_tag"]] = (
            1, "pullback_resume_down",
        )

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        exit_long = (
            (dataframe["ema_fast"] < dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) >= dataframe["ema_slow"].shift(1))
        )
        dataframe.loc[exit_long, "exit_long"] = 1

        exit_short = (
            (dataframe["ema_fast"] > dataframe["ema_slow"])
            & (dataframe["ema_fast"].shift(1) <= dataframe["ema_slow"].shift(1))
        )
        dataframe.loc[exit_short, "exit_short"] = 1

        return dataframe

    def leverage(
        self, pair: str, current_time, current_rate: float, proposed_leverage: float,
        max_leverage: float, entry_tag, side: str, **kwargs,
    ) -> float:
        return min(self.max_leverage, max_leverage)

    def custom_stake_amount(
        self, pair: str, current_time, current_rate: float, proposed_stake: float,
        min_stake, max_stake: float, leverage: float, entry_tag, side: str, **kwargs,
    ) -> float:
        """
        Size the position so that if price hits the ATR-based stoploss,
        the realized loss equals `risk_per_trade` of total account equity
        -- independent of leverage used.
        """
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return min(proposed_stake, max_stake or proposed_stake)

        atr = dataframe["atr"].iloc[-1]
        stop_distance_pct = (atr * self.atr_stop_multiplier.value) / current_rate
        if stop_distance_pct <= 0:
            return min(proposed_stake, max_stake or proposed_stake)

        total_equity = self.wallets.get_total_stake_amount()
        risk_amount = total_equity * self.risk_per_trade
        lev = leverage or 1.0

        stake = risk_amount / (stop_distance_pct * lev)

        stake = max(stake, min_stake or 0)
        if max_stake:
            stake = min(stake, max_stake)
        return stake

    def custom_stoploss(
        self, pair: str, trade: Trade, current_time, current_rate: float,
        current_profit: float, **kwargs,
    ) -> float:
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe is None or dataframe.empty:
            return self.stoploss

        atr = dataframe["atr"].iloc[-1]
        stop_distance_pct = (atr * self.atr_stop_multiplier.value) / trade.open_rate

        # Profit protection: once the trade has moved `breakeven_at_r_multiple`
        # times its initial risk in our favor, ratchet the stop to breakeven
        # (+ small buffer) instead of leaving the original ATR distance in
        # place. Prevents a winning trade from fully reversing into a loss.
        if current_profit >= stop_distance_pct * self.breakeven_at_r_multiple:
            breakeven_sl = stoploss_from_open(
                self.breakeven_buffer, current_profit,
                is_short=trade.is_short, leverage=trade.leverage,
            )
            if breakeven_sl is not None:
                return breakeven_sl

        return -abs(stop_distance_pct)
