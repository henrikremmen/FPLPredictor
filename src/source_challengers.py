"""Experimental source additions to market and no-odds point branches."""
import numpy as np
from threadpoolctl import threadpool_limits

from improved_models import EXTRA
from market_models import ALL_MARKET_FEATURES, market_enrich
from model_experiments import FEATURE_SETS, build_model


class SourceChallenger:
    def __init__(self, incumbent, extra_features):
        self.incumbent = incumbent
        self.extra_features = list(extra_features)

    def fit(self, data):
        data = market_enrich(data)
        requested = FEATURE_SETS["context"] + EXTRA + self.extra_features
        with threadpool_limits(limits=4):
            short = data[data.season.ge("2022-23")]
            self.fallback_hgb, self.fallback_columns, _ = build_model("hgb", short, requested, 7)
            self.fallback_hgb.fit(short[self.fallback_columns], short.target_points)
            self.market, self.market_columns, _ = build_model("hgb", data, requested + ALL_MARKET_FEATURES, 7)
            self.market.fit(data[self.market_columns], data.target_points)
        return self

    def predict(self, data):
        data = market_enrich(data)
        # Preserve ridge and mixture branches; replace only fallback HGB with
        # its source-augmented counterpart. This requires prospective testing.
        parts = self.incumbent.points_model.baseline.models
        if len(parts) != 3 or parts[1].kind != "hgb":
            raise ValueError("Unexpected incumbent fallback architecture")
        with threadpool_limits(limits=4):
            fallback = (parts[0].predict(data) + self.fallback_hgb.predict(data[self.fallback_columns])
                        + parts[2].predict(data)) / 3
            market = self.market.predict(data[self.market_columns])
        available = data[["market_team_expected_goals", "market_opponent_expected_goals",
                          "market_clean_sheet_probability"]].notna().all(axis=1)
        return np.where(available, market, fallback)
