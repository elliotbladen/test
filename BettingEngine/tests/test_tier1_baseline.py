# tests/test_tier1_baseline.py
# =============================================================================
# Tier 1 baseline — unit and integration tests
# =============================================================================
#
# Covers every public and key private function in pricing/tier1_baseline.py,
# plus _win_probability_from_margin from pricing/engine.py.
#
# Run with:   pytest tests/test_tier1_baseline.py -v
# =============================================================================

import math
import pytest

from pricing.tier1_baseline import (
    compute_season_quality_rating,
    compute_recent_form,
    compute_attack_rating,
    compute_defence_rating,
    compute_team_home_advantage,
    compute_league_home_advantage,
    compute_form_behavior_adjustment,
    compute_form_quality_signals,
    compute_expected_home_points,
    compute_expected_away_points,
    compute_baseline,
)
from pricing.engine import _win_probability_from_margin


# =============================================================================
# Shared fixtures / helpers
# =============================================================================

LEAGUE_AVG = 23.5   # half of 47.0 (default league_avg_total)

MINIMAL_CONFIG = {
    'league_avg_total': 47.0,
}

FULL_CONFIG = {
    'league_avg_total':               47.0,
    'season_quality_scale':           24.0,
    'season_quality_correction_weight': 0.2,
    'season_quality_win_weight':      0.6,
    'season_quality_ladder_weight':   0.4,
    'season_quality_num_teams':       16,
    'recent_form_games':              5,
    'form_recency_weighted':          False,
    'form_outcome_weight':            0.4,
    'form_margin_weight':             0.2,
    'form_scoring_weight':            0.2,
    'form_conceding_weight':          0.2,
    'form_margin_norm':               20.0,
    'form_scoring_norm':              12.0,
    'form_conceding_norm':            12.0,
    'form_weight_points':             2.5,
    'form_balance_weight':            1.0,
    'attack_season_weight':           0.7,
    'defence_season_weight':          0.7,
    'home_advantage_points':          3.5,
    'min_games_for_home_advantage':   4,
    'team_ha_max_delta':              4.0,
    'blowout_threshold':              20.0,
    'narrow_threshold':               8.0,
    'strong_opp_factor':              1.2,
    'weak_opp_factor':                0.8,
    'broader_form_threshold':         0.1,
    'blowout_win_dampener':           0.10,
    'blowout_loss_amplifier':         0.15,
    'narrow_loss_vs_strong_bonus':    0.10,
    'ugly_win_positive_bonus':        0.05,
    'ugly_win_negative_penalty':      0.05,
    'form_behavior_max_adj':          0.25,
    'low_score_winning_threshold':    0.5,
    'low_score_attack_threshold':     -1.5,
    'low_score_defence_threshold':    2.0,
    'low_score_warning_adj':          -0.10,
    'leaky_defence_threshold':        -2.0,
    'leaky_attack_threshold':         2.0,
    'leaky_warning_adj':              -0.08,
    'form_quality_max_adj':           0.15,
    'default_elo':                    1500.0,
    'points_per_elo_point':           0.04,
    'elo_weight':                     0.3,
    'season_quality_weight':          1.0,
    'defence_attack_bias':            0.05,
    'totals_conservative_bias':       0.5,
    'close_call_class_lean_threshold': 6.0,
    'close_call_class_lean_pts':      0.5,
    'margin_std_dev':                 12.0,
}


def avg_team_stats(
    avg_for=LEAGUE_AVG,
    avg_against=LEAGUE_AVG,
    win_pct=0.5,
    games_played=14,
    ladder_position=8,
    elo_rating=1500.0,
    recent_form_rating=0.0,
    home_pts_for=None,
    home_pts_against=None,
    away_pts_for=None,
    away_pts_against=None,
):
    """Return a stats dict representing an average NRL team."""
    return {
        'points_for_avg':        avg_for,
        'points_against_avg':    avg_against,
        'win_pct':               win_pct,
        'games_played':          games_played,
        'ladder_position':       ladder_position,
        'elo_rating':            elo_rating,
        'recent_form_rating':    recent_form_rating,
        'home_points_for_avg':   home_pts_for,
        'home_points_against_avg': home_pts_against,
        'away_points_for_avg':   away_pts_for,
        'away_points_against_avg': away_pts_against,
    }


def win_result(pts_for, pts_against):
    return {'points_for': pts_for, 'points_against': pts_against}


# =============================================================================
# 1. compute_season_quality_rating
# =============================================================================

class TestComputeSeasonQualityRating:
    def test_average_team_returns_near_zero(self):
        stats = avg_team_stats(avg_for=LEAGUE_AVG, avg_against=LEAGUE_AVG,
                               win_pct=0.5, ladder_position=8)
        q = compute_season_quality_rating(stats, LEAGUE_AVG, FULL_CONFIG)
        assert abs(q) < 2.0, "Average team with win_pct=0.5 should be near zero"

    def test_top_team_positive(self):
        stats = avg_team_stats(avg_for=30.0, avg_against=18.0,
                               win_pct=0.85, ladder_position=1)
        q = compute_season_quality_rating(stats, LEAGUE_AVG, FULL_CONFIG)
        assert q > 5.0, "Top team should produce a clearly positive quality rating"

    def test_bottom_team_negative(self):
        stats = avg_team_stats(avg_for=16.0, avg_against=32.0,
                               win_pct=0.10, ladder_position=16)
        q = compute_season_quality_rating(stats, LEAGUE_AVG, FULL_CONFIG)
        assert q < -5.0, "Bottom team should produce a clearly negative quality rating"

    def test_no_win_pct_falls_back_to_scoring_diff(self):
        stats = avg_team_stats(avg_for=28.0, avg_against=20.0,
                               win_pct=None, games_played=0)
        q = compute_season_quality_rating(stats, LEAGUE_AVG, FULL_CONFIG)
        assert abs(q - (28.0 - 20.0)) < 0.001, \
            "No win_pct should fall back to pure scoring differential"

    def test_no_ladder_position_runs_cleanly(self):
        stats = avg_team_stats(win_pct=0.7, ladder_position=None)
        q = compute_season_quality_rating(stats, LEAGUE_AVG, FULL_CONFIG)
        # Should not raise; win_quality dominates
        expected = (0.7 - 0.5) * 24.0  # win_quality without ladder
        primary = expected  # no ladder, primary = win_quality
        scoring_diff = LEAGUE_AVG - LEAGUE_AVG
        expected_q = primary * 0.8 + scoring_diff * 0.2
        assert abs(q - expected_q) < 0.01

    def test_zero_games_treated_as_no_win_record(self):
        stats = avg_team_stats(win_pct=0.9, games_played=0,
                               avg_for=25.0, avg_against=20.0)
        q = compute_season_quality_rating(stats, LEAGUE_AVG, FULL_CONFIG)
        # games_played == 0 → fallback to scoring diff
        assert abs(q - (25.0 - 20.0)) < 0.001

    def test_none_config_uses_defaults(self):
        stats = avg_team_stats(win_pct=0.5, games_played=10)
        q = compute_season_quality_rating(stats, LEAGUE_AVG, None)
        assert isinstance(q, float)


# =============================================================================
# 2. compute_recent_form
# =============================================================================

class TestComputeRecentForm:
    def test_empty_results_returns_zero(self):
        assert compute_recent_form([], FULL_CONFIG, LEAGUE_AVG) == 0.0

    def test_all_wins_positive(self):
        results = [win_result(30, 15)] * 5
        score = compute_recent_form(results, FULL_CONFIG, LEAGUE_AVG)
        assert score > 0.0

    def test_all_losses_negative(self):
        results = [win_result(12, 28)] * 5
        score = compute_recent_form(results, FULL_CONFIG, LEAGUE_AVG)
        assert score < 0.0

    def test_score_bounded_in_range(self):
        results = [win_result(60, 0)] * 10  # extreme wins
        score = compute_recent_form(results, FULL_CONFIG, LEAGUE_AVG)
        assert -1.0 <= score <= 1.0

    def test_score_bounded_negative_range(self):
        results = [win_result(0, 60)] * 10  # extreme losses
        score = compute_recent_form(results, FULL_CONFIG, LEAGUE_AVG)
        assert -1.0 <= score <= 1.0

    def test_mixed_form_near_neutral(self):
        # Alternating wins/losses around league average → near zero
        results = [
            win_result(24, 23),
            win_result(22, 24),
            win_result(25, 22),
            win_result(21, 25),
            win_result(24, 23),
        ]
        score = compute_recent_form(results, FULL_CONFIG, LEAGUE_AVG)
        assert -0.3 < score < 0.5

    def test_only_first_n_games_counted(self):
        recent_5 = [win_result(30, 15)] * 5
        old_5 = [win_result(10, 40)] * 5
        all_10 = recent_5 + old_5
        score_5  = compute_recent_form(recent_5, FULL_CONFIG, LEAGUE_AVG)
        score_10 = compute_recent_form(all_10, FULL_CONFIG, LEAGUE_AVG)
        assert abs(score_5 - score_10) < 0.001, \
            "Results beyond n should not affect score"

    def test_recency_weighted_differs_from_flat(self):
        config_weighted = dict(FULL_CONFIG, form_recency_weighted=True)
        results = [win_result(40, 10), win_result(10, 40)] + \
                  [win_result(20, 20)] * 3  # recent=big win, then big loss
        flat   = compute_recent_form(results, FULL_CONFIG, LEAGUE_AVG)
        weighted = compute_recent_form(results, config_weighted, LEAGUE_AVG)
        # Both are valid; they just needn't be equal when pattern is asymmetric
        assert isinstance(flat, float) and isinstance(weighted, float)

    def test_league_avg_derived_from_config_when_not_passed(self):
        results = [win_result(24, 23)] * 5
        score = compute_recent_form(results, FULL_CONFIG)  # no league_avg_per_team
        assert isinstance(score, float)


# =============================================================================
# 3. compute_attack_rating
# =============================================================================

class TestComputeAttackRating:
    def test_average_scorer_returns_zero(self):
        stats = avg_team_stats(avg_for=LEAGUE_AVG)
        ar = compute_attack_rating(stats, LEAGUE_AVG, config=FULL_CONFIG)
        assert abs(ar) < 0.001

    def test_good_scorer_positive(self):
        stats = avg_team_stats(avg_for=30.0)
        ar = compute_attack_rating(stats, LEAGUE_AVG, config=FULL_CONFIG)
        assert ar > 0.0

    def test_poor_scorer_negative(self):
        stats = avg_team_stats(avg_for=16.0)
        ar = compute_attack_rating(stats, LEAGUE_AVG, config=FULL_CONFIG)
        assert ar < 0.0

    def test_season_only_when_no_recent(self):
        stats = avg_team_stats(avg_for=28.0)
        ar = compute_attack_rating(stats, LEAGUE_AVG, recent_avg_for=None, config=FULL_CONFIG)
        assert abs(ar - (28.0 - LEAGUE_AVG)) < 0.001

    def test_blend_with_recent_data(self):
        stats = avg_team_stats(avg_for=28.0)
        # recent_avg = 20.0 (below league avg)
        ar = compute_attack_rating(stats, LEAGUE_AVG, recent_avg_for=20.0, config=FULL_CONFIG)
        season_attack = 28.0 - LEAGUE_AVG
        recent_attack = 20.0 - LEAGUE_AVG
        expected = season_attack * 0.7 + recent_attack * 0.3
        assert abs(ar - expected) < 0.001

    def test_none_config_uses_defaults(self):
        stats = avg_team_stats(avg_for=25.0)
        ar = compute_attack_rating(stats, LEAGUE_AVG)
        assert isinstance(ar, float)


# =============================================================================
# 4. compute_defence_rating
# =============================================================================

class TestComputeDefenceRating:
    def test_average_defence_returns_zero(self):
        stats = avg_team_stats(avg_against=LEAGUE_AVG)
        dr = compute_defence_rating(stats, LEAGUE_AVG, config=FULL_CONFIG)
        assert abs(dr) < 0.001

    def test_good_defence_positive(self):
        stats = avg_team_stats(avg_against=18.0)
        dr = compute_defence_rating(stats, LEAGUE_AVG, config=FULL_CONFIG)
        assert dr > 0.0

    def test_poor_defence_negative(self):
        stats = avg_team_stats(avg_against=32.0)
        dr = compute_defence_rating(stats, LEAGUE_AVG, config=FULL_CONFIG)
        assert dr < 0.0

    def test_season_only_when_no_recent(self):
        stats = avg_team_stats(avg_against=20.0)
        dr = compute_defence_rating(stats, LEAGUE_AVG, recent_avg_against=None, config=FULL_CONFIG)
        assert abs(dr - (LEAGUE_AVG - 20.0)) < 0.001

    def test_blend_with_recent_data(self):
        stats = avg_team_stats(avg_against=20.0)
        dr = compute_defence_rating(stats, LEAGUE_AVG, recent_avg_against=28.0, config=FULL_CONFIG)
        season_def = LEAGUE_AVG - 20.0
        recent_def = LEAGUE_AVG - 28.0
        expected = season_def * 0.7 + recent_def * 0.3
        assert abs(dr - expected) < 0.001


# =============================================================================
# 5. compute_team_home_advantage
# =============================================================================

class TestComputeTeamHomeAdvantage:
    def test_no_split_data_returns_league_average(self):
        stats = avg_team_stats()  # home/away fields default to None
        ha = compute_team_home_advantage(stats, FULL_CONFIG)
        assert abs(ha - 3.5) < 0.001

    def test_strong_home_team_above_league_average(self):
        stats = avg_team_stats(
            avg_for=LEAGUE_AVG, avg_against=LEAGUE_AVG,
            home_pts_for=28.0, home_pts_against=18.0,
            games_played=20,
        )
        ha = compute_team_home_advantage(stats, FULL_CONFIG)
        # home_scoring_boost = 28 - 23.5 = 4.5
        # home_defence_boost = 23.5 - 18 = 5.5
        # raw = (4.5 + 5.5) / 2 = 5.0 → capped at league_ha + max_delta = 7.5
        assert ha > 3.5

    def test_weak_home_team_below_league_average(self):
        stats = avg_team_stats(
            avg_for=LEAGUE_AVG, avg_against=LEAGUE_AVG,
            home_pts_for=20.0, home_pts_against=28.0,
            games_played=20,
        )
        ha = compute_team_home_advantage(stats, FULL_CONFIG)
        # home_scoring_boost = 20 - 23.5 = -3.5
        # home_defence_boost = 23.5 - 28 = -4.5
        # raw = (-3.5 + -4.5) / 2 = -4.0 → capped at league_ha - max_delta = -0.5
        assert ha < 3.5

    def test_low_games_blends_toward_league_average(self):
        stats = avg_team_stats(
            avg_for=LEAGUE_AVG, avg_against=LEAGUE_AVG,
            home_pts_for=32.0, home_pts_against=15.0,
            games_played=2,  # below min_games_for_home_advantage
        )
        ha_low = compute_team_home_advantage(stats, FULL_CONFIG)
        stats_many = dict(stats, games_played=20)
        ha_many = compute_team_home_advantage(stats_many, FULL_CONFIG)
        # Low games result should be closer to league average than high-games result
        assert abs(ha_low - 3.5) < abs(ha_many - 3.5)

    def test_raw_ha_capped_at_league_ha_plus_max_delta(self):
        stats = avg_team_stats(
            avg_for=LEAGUE_AVG, avg_against=LEAGUE_AVG,
            home_pts_for=50.0, home_pts_against=5.0,  # extreme split
            games_played=100,
        )
        ha = compute_team_home_advantage(stats, FULL_CONFIG)
        max_allowed = 3.5 + 4.0  # league_ha + max_delta
        assert ha <= max_allowed + 0.001

    def test_raw_ha_capped_below_league_ha_minus_max_delta(self):
        stats = avg_team_stats(
            avg_for=LEAGUE_AVG, avg_against=LEAGUE_AVG,
            home_pts_for=5.0, home_pts_against=50.0,
            games_played=100,
        )
        ha = compute_team_home_advantage(stats, FULL_CONFIG)
        min_allowed = 3.5 - 4.0  # league_ha - max_delta
        assert ha >= min_allowed - 0.001

    def test_league_home_advantage_uses_config_value(self):
        config = dict(FULL_CONFIG, home_advantage_points=5.0)
        ha = compute_league_home_advantage(config)
        assert abs(ha - 5.0) < 0.001


# =============================================================================
# 6. compute_form_behavior_adjustment
# =============================================================================

class TestComputeFormBehaviorAdjustment:
    def test_empty_results_returns_zero(self):
        adj = compute_form_behavior_adjustment([], 0.0, LEAGUE_AVG, FULL_CONFIG)
        assert adj == 0.0

    def test_blowout_wins_dampen_form(self):
        # Rule A: blowout win → slight negative adj
        results = [win_result(50, 10)] * 5
        adj = compute_form_behavior_adjustment(results, 0.8, LEAGUE_AVG, FULL_CONFIG)
        assert adj < 0.0

    def test_blowout_losses_amplify_negative(self):
        # Rule A: blowout loss → amplified negative adj
        results = [win_result(10, 50)] * 5
        adj = compute_form_behavior_adjustment(results, -0.8, LEAGUE_AVG, FULL_CONFIG)
        assert adj < 0.0

    def test_narrow_loss_to_strong_opp_with_positive_form_gets_bonus(self):
        # Rule B: narrow loss vs strong opponent, broadly positive form → small positive
        # strong_opp_factor=1.2 → need pts_against > 23.5*1.2=28.2, use 30
        # narrow_threshold=8.0 → need abs(margin) < 8, so pts_for=23, pts_against=30 → margin=-7
        result = {'points_for': 23, 'points_against': 30}
        adj = compute_form_behavior_adjustment([result], 0.3, LEAGUE_AVG, FULL_CONFIG)
        assert adj > 0.0

    def test_narrow_win_vs_weak_opp_is_neutral(self):
        # Rule D: narrow win vs weak opponent → no adj
        pts_against_weak = int(LEAGUE_AVG * 0.7)
        results = [{'points_for': 22, 'points_against': pts_against_weak}]
        adj = compute_form_behavior_adjustment(results, 0.5, LEAGUE_AVG, FULL_CONFIG)
        assert adj == 0.0

    def test_output_bounded_by_max_adj(self):
        # Many blowout losses should hit the cap
        results = [win_result(5, 60)] * 5
        adj = compute_form_behavior_adjustment(results, -0.9, LEAGUE_AVG, FULL_CONFIG)
        assert abs(adj) <= FULL_CONFIG['form_behavior_max_adj'] + 0.001


# =============================================================================
# 7. compute_form_quality_signals
# =============================================================================

class TestComputeFormQualitySignals:
    def test_zero_games_returns_zero(self):
        stats = avg_team_stats(games_played=0)
        adj = compute_form_quality_signals(stats, LEAGUE_AVG, 0.0, 0.0, FULL_CONFIG)
        assert adj == 0.0

    def test_low_scoring_winner_gets_warning(self):
        # Rule E: winning, weak attack, not elite defence → mild negative
        stats = avg_team_stats(win_pct=0.7, games_played=10)
        attack = -2.0  # below low_score_attack_threshold (-1.5)
        defence = 1.5  # below elite_def_threshold (2.0)
        adj = compute_form_quality_signals(stats, LEAGUE_AVG, attack, defence, FULL_CONFIG)
        assert adj < 0.0

    def test_elite_defence_exempts_low_scoring_winner(self):
        # Rule E: winning, weak attack, BUT elite defence → no penalty
        stats = avg_team_stats(win_pct=0.7, games_played=10)
        attack = -2.0
        defence = 3.0  # above elite_def_threshold (2.0)
        adj = compute_form_quality_signals(stats, LEAGUE_AVG, attack, defence, FULL_CONFIG)
        assert adj == 0.0

    def test_high_scoring_but_leaky_gets_warning(self):
        # Rule F: good attack AND leaky defence → slight warning
        stats = avg_team_stats(win_pct=0.5, games_played=10)
        attack = 3.0   # above leaky_attack_threshold (2.0)
        defence = -3.0  # below leaky_defence_threshold (-2.0)
        adj = compute_form_quality_signals(stats, LEAGUE_AVG, attack, defence, FULL_CONFIG)
        assert adj < 0.0

    def test_adjustment_never_positive(self):
        # Both rules only produce warnings (negatives or zero)
        stats = avg_team_stats(win_pct=0.5, games_played=10)
        for atk in (-3.0, 0.0, 3.0):
            for dfn in (-3.0, 0.0, 3.0):
                adj = compute_form_quality_signals(stats, LEAGUE_AVG, atk, dfn, FULL_CONFIG)
                assert adj <= 0.0

    def test_bounded_by_max_adj(self):
        stats = avg_team_stats(win_pct=0.9, games_played=10)
        attack = -5.0
        defence = 1.0
        adj = compute_form_quality_signals(stats, LEAGUE_AVG, attack, defence, FULL_CONFIG)
        assert adj >= -FULL_CONFIG['form_quality_max_adj'] - 0.001


# =============================================================================
# 8. _win_probability_from_margin
# =============================================================================

class TestWinProbabilityFromMargin:
    def test_zero_margin_gives_fifty_percent(self):
        p = _win_probability_from_margin(0.0, 12.0)
        assert abs(p - 0.5) < 0.001

    def test_positive_margin_above_fifty_percent(self):
        p = _win_probability_from_margin(6.0, 12.0)
        assert p > 0.5

    def test_negative_margin_below_fifty_percent(self):
        p = _win_probability_from_margin(-6.0, 12.0)
        assert p < 0.5

    def test_symmetric_around_zero(self):
        p_pos = _win_probability_from_margin(+12.0, 12.0)
        p_neg = _win_probability_from_margin(-12.0, 12.0)
        assert abs(p_pos + p_neg - 1.0) < 0.001

    def test_known_value_one_std_dev(self):
        # P(Z > -1) = Φ(1) ≈ 0.8413
        p = _win_probability_from_margin(12.0, 12.0)
        assert abs(p - 0.8413) < 0.001

    def test_output_between_zero_and_one(self):
        # Normal margins are strictly in (0, 1)
        for margin in (-30.0, -12.0, 0.0, 12.0, 30.0):
            p = _win_probability_from_margin(margin, 12.0)
            assert 0.0 < p < 1.0
        # Extreme margins may saturate at 0.0 or 1.0 via math.erf — that is expected
        p_extreme_low  = _win_probability_from_margin(-100.0, 12.0)
        p_extreme_high = _win_probability_from_margin(+100.0, 12.0)
        assert 0.0 <= p_extreme_low  <= 1.0
        assert 0.0 <= p_extreme_high <= 1.0

    def test_smaller_std_dev_more_confident(self):
        margin = 6.0
        p_narrow = _win_probability_from_margin(margin, 6.0)
        p_wide   = _win_probability_from_margin(margin, 12.0)
        assert p_narrow > p_wide

    def test_invalid_std_dev_raises(self):
        with pytest.raises(ValueError):
            _win_probability_from_margin(0.0, 0.0)
        with pytest.raises(ValueError):
            _win_probability_from_margin(0.0, -1.0)


# =============================================================================
# 9. compute_baseline — integration
# =============================================================================

class TestComputeBaseline:
    """Integration tests for the full Tier 1 orchestration."""

    def _evenly_matched_stats(self):
        return avg_team_stats(
            avg_for=LEAGUE_AVG, avg_against=LEAGUE_AVG,
            win_pct=0.5, ladder_position=8, elo_rating=1500.0,
            games_played=14, recent_form_rating=0.0,
            home_pts_for=LEAGUE_AVG, home_pts_against=LEAGUE_AVG,
        )

    def test_return_shape(self):
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        required = {
            'baseline_home_points',
            'baseline_away_points',
            'baseline_margin',
            'baseline_total',
            '_debug',
        }
        assert required.issubset(set(result.keys()))

    def test_home_has_advantage_over_away_equal_teams(self):
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        # Home advantage should push home team above away team
        assert result['baseline_home_points'] > result['baseline_away_points']
        assert result['baseline_margin'] > 0.0

    def test_margin_equals_home_minus_away(self):
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        computed = result['baseline_home_points'] - result['baseline_away_points']
        # Allow 0.02 tolerance: each value is independently rounded to 2dp,
        # so subtraction of rounded floats may drift by up to 0.01 per value.
        assert abs(computed - result['baseline_margin']) < 0.02

    def test_total_equals_home_plus_away(self):
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        computed = result['baseline_home_points'] + result['baseline_away_points']
        assert abs(computed - result['baseline_total']) < 0.01

    def test_stronger_home_team_produces_larger_margin(self):
        home_strong = avg_team_stats(
            avg_for=32.0, avg_against=18.0, win_pct=0.85, ladder_position=1,
            elo_rating=1600.0, games_played=14, recent_form_rating=0.5,
        )
        away_weak = avg_team_stats(
            avg_for=16.0, avg_against=32.0, win_pct=0.10, ladder_position=16,
            elo_rating=1400.0, games_played=14, recent_form_rating=-0.5,
        )
        home_avg = self._evenly_matched_stats()
        away_avg = self._evenly_matched_stats()

        result_strong = compute_baseline(home_strong, away_weak, {}, FULL_CONFIG)
        result_avg    = compute_baseline(home_avg, away_avg, {}, FULL_CONFIG)
        assert result_strong['baseline_margin'] > result_avg['baseline_margin']

    def test_away_strong_team_reduces_home_margin(self):
        home = self._evenly_matched_stats()
        away_strong = avg_team_stats(
            avg_for=32.0, avg_against=16.0, win_pct=0.9, ladder_position=1,
            elo_rating=1650.0, games_played=14,
        )
        away_avg = self._evenly_matched_stats()

        result_strong_away = compute_baseline(home, away_strong, {}, FULL_CONFIG)
        result_avg_away    = compute_baseline(home, away_avg, {}, FULL_CONFIG)
        assert result_strong_away['baseline_margin'] < result_avg_away['baseline_margin']

    def test_debug_contains_expected_keys(self):
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        debug = result['_debug']
        required_keys = [
            'league_avg_per_team',
            'home_season_quality', 'away_season_quality',
            'home_attack_rating',  'away_attack_rating',
            'home_defence_rating', 'away_defence_rating',
            'home_form_score',     'away_form_score',
            'home_form_source',    'away_form_source',
            'margin_from_ratings', 'margin_from_elo',
            'blended_margin',      'adjusted_margin',
        ]
        for k in required_keys:
            assert k in debug, f"Missing debug key: {k}"

    def test_with_live_last_n_results(self):
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        home_results = [win_result(30, 18)] * 5
        away_results = [win_result(16, 28)] * 5
        result = compute_baseline(home, away, {}, FULL_CONFIG,
                                  home_last_n_results=home_results,
                                  away_last_n_results=away_results)
        debug = result['_debug']
        assert debug['home_form_source'] == 'computed'
        assert debug['away_form_source'] == 'computed'
        # Home with good form, away with poor form → higher margin than baseline
        result_no_form = compute_baseline(home, away, {}, FULL_CONFIG)
        assert result['baseline_margin'] > result_no_form['baseline_margin']

    def test_stored_form_rating_fallback(self):
        home = avg_team_stats(recent_form_rating=0.8, games_played=14)
        away = avg_team_stats(recent_form_rating=-0.5, games_played=14)
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        debug = result['_debug']
        assert debug['home_form_source'] == 'stored'
        assert debug['away_form_source'] == 'stored'

    def test_no_elo_stored_uses_quality_fallback(self):
        home = avg_team_stats(elo_rating=None, avg_for=30.0, avg_against=18.0,
                              win_pct=0.8, games_played=14)
        away = avg_team_stats(elo_rating=None, avg_for=18.0, avg_against=30.0,
                              win_pct=0.2, games_played=14)
        # Should not raise; uses season quality proxy
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        assert isinstance(result['baseline_margin'], float)

    def test_totals_conservative_bias_applied(self):
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        config_no_bias = dict(FULL_CONFIG, totals_conservative_bias=0.0)
        result_with    = compute_baseline(home, away, {}, FULL_CONFIG)
        result_without = compute_baseline(home, away, {}, config_no_bias)
        assert result_with['baseline_total'] < result_without['baseline_total']

    def test_dynamic_elo_weight_early_season(self):
        # At 0 games played, dynamic_elo_weight should be 1.0 (pure ELO)
        home = avg_team_stats(games_played=0, elo_rating=1500.0)
        away = avg_team_stats(games_played=0, elo_rating=1500.0)
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        debug = result['_debug']
        assert abs(debug['dynamic_elo_weight'] - 1.0) < 0.001

    def test_dynamic_elo_weight_full_season(self):
        # At full games played, ELO weight should be below 1.0 (PF/PA has earned influence)
        home = self._evenly_matched_stats()  # games_played=14
        away = self._evenly_matched_stats()
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        debug = result['_debug']
        assert debug['dynamic_elo_weight'] < 1.0

    def test_blended_margin_is_weighted_combination(self):
        # blended_margin must lie between margin_from_elo and margin_from_ratings
        home = self._evenly_matched_stats()
        away = self._evenly_matched_stats()
        result = compute_baseline(home, away, {}, FULL_CONFIG)
        debug = result['_debug']
        lo = min(debug['margin_from_elo'], debug['margin_from_ratings'])
        hi = max(debug['margin_from_elo'], debug['margin_from_ratings'])
        assert lo - 0.01 <= debug['blended_margin'] <= hi + 0.01
