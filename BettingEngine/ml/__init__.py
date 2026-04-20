# ml/
# Machine learning layer for the NRL pricing engine.
#
# Architecture:
#   - Runs entirely separate from the production tier model
#   - Trained on historical data (2011-2025), validated on holdout seasons
#   - Runs in shadow mode alongside prepare_round.py from Phase 3 onwards
#   - Never overwrites tier model prices until proven over a meaningful sample
#
# Phases:
#   Phase 1 — Structure only (current)
#   Phase 2 — Feature engineering + training on 15-season historical dataset
#   Phase 3 — Shadow mode: ML prediction logged alongside tier model each round
#   Phase 4 — Blend layer introduced if ML demonstrably adds value
