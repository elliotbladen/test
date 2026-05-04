from scipy.stats import norm

STD_MARGIN = 36.0
STD_TOTAL  = 22.7

mkt = {
    'COL_HAW': {'home_h2h': 3.60, 'away_h2h': 1.30,  'hcap_line': -21.5, 'hcap_price': 1.91, 'total_line': 179.5, 'total_price': 1.91},
    'WBD_FRE': {'home_h2h': 3.50, 'away_h2h': 1.31,  'hcap_line': -20.5, 'hcap_price': 1.91, 'total_line': 183.5, 'total_price': 1.91},
    'ADE_POR': {'home_h2h': None, 'away_h2h': None,   'hcap_line': -11.5, 'hcap_price': 1.91, 'total_line': None,  'total_price': None},
    'ESS_BRI': {'home_h2h': 8.00, 'away_h2h': 1.08,   'hcap_line':  43.5, 'hcap_price': 1.91, 'total_line': None,  'total_price': None},
    'WCE_RIC': {'home_h2h': None, 'away_h2h': 2.90,   'hcap_line': -15.5, 'hcap_price': None, 'total_line': None,  'total_price': None},
    'GEE_NTH': {'home_h2h': 1.20, 'away_h2h': 4.60,   'hcap_line': -28.5, 'hcap_price': 1.91, 'total_line': 189.5, 'total_price': 1.91},
    'CAR_STK': {'home_h2h': 2.80, 'away_h2h': 1.44,   'hcap_line':  14.5, 'hcap_price': 1.91, 'total_line': None,  'total_price': None},
    'SYD_MEL': {'home_h2h': 1.17, 'away_h2h': 5.25,   'hcap_line': -31.5, 'hcap_price': 1.91, 'total_line': 188.5, 'total_price': 1.91},
    'GCS_GWS': {'home_h2h': None, 'away_h2h': 3.10,   'hcap_line':  25.5, 'hcap_price': 1.64, 'total_line': None,  'total_price': None},
}

model = {
    'COL_HAW': {'label': 'Collingwood vs Hawthorn',      'rules_margin': -5.0,  'rules_total': 169.6, 'rules_h': 0.444, 'ml_margin': -3.8,  'ml_total': 166.4, 'ml_h': 0.822},
    'WBD_FRE': {'label': 'Bulldogs vs Fremantle',         'rules_margin': +23.0, 'rules_total': 183.3, 'rules_h': 0.739, 'ml_margin': +12.5, 'ml_total': 152.4, 'ml_h': 0.690},
    'ADE_POR': {'label': 'Adelaide vs Port (Showdown)',   'rules_margin': +42.2, 'rules_total': 168.4, 'rules_h': 0.879, 'ml_margin': +28.2, 'ml_total': 186.6, 'ml_h': 0.812},
    'ESS_BRI': {'label': 'Essendon vs Brisbane',          'rules_margin': -57.1, 'rules_total': 169.9, 'rules_h': 0.056, 'ml_margin': -29.6, 'ml_total': 160.2, 'ml_h': 0.397},
    'WCE_RIC': {'label': 'West Coast vs Richmond',        'rules_margin': +20.3, 'rules_total': 138.9, 'rules_h': 0.713, 'ml_margin': +17.1, 'ml_total': 154.4, 'ml_h': 0.755},
    'GEE_NTH': {'label': 'Geelong vs North Melbourne',   'rules_margin': +52.9, 'rules_total': 187.0, 'rules_h': 0.929, 'ml_margin': +34.3, 'ml_total': 167.2, 'ml_h': 0.676},
    'CAR_STK': {'label': 'Carlton vs St Kilda',           'rules_margin': +12.2, 'rules_total': 165.9, 'rules_h': 0.633, 'ml_margin': +12.1, 'ml_total': 163.8, 'ml_h': 0.660},
    'SYD_MEL': {'label': 'Sydney vs Melbourne',           'rules_margin': +43.4, 'rules_total': 188.6, 'rules_h': 0.886, 'ml_margin': +29.1, 'ml_total': 177.6, 'ml_h': 0.809},
    'GCS_GWS': {'label': 'Gold Coast vs GWS',             'rules_margin': +18.0, 'rules_total': 182.4, 'rules_h': 0.692, 'ml_margin': +12.2, 'ml_total': 152.7, 'ml_h': 0.920},
}

def xev(prob, odds):
    return prob * odds - 1

def p_hcap(mean, line):
    return 1 - norm.cdf((line - mean) / STD_MARGIN)

def p_under(mean, line):
    return norm.cdf((line - mean) / STD_TOTAL)

def p_over(mean, line):
    return 1 - norm.cdf((line - mean) / STD_TOTAL)

W = 96
print()
print('=' * W)
print('  AFL R8 2026 — EV MATRIX  |  Model vs Bet365  (lines sourced 2026-05-01)')
print('  Rules = T1-T7 full stack  |  ML = XGBoost shadow  |  std: margin=36.0 / total=22.7')
print('  WARNING: ELO is R6-only — 2 rounds stale.  Verify R7 results before acting.')
print('=' * W)

# ── H2H ────────────────────────────────────────────────────────────────────
print()
print('  H2H MARKET')
print(f'  {"Game":<36} {"Rules H%":>9} {"ML H%":>7}  {"Mkt Home":>9} {"Mkt Away":>9}  {"EV Home":>8} {"EV Away":>8}')
print('  ' + '-' * W)
for k, m in model.items():
    mk = mkt[k]
    rh = m['rules_h']
    mh = mk['home_h2h']
    ma = mk['away_h2h']
    evh_s = f"{xev(rh, mh):+.1%}" if mh else "     —"
    eva_s = f"{xev(1-rh, ma):+.1%}" if ma else "     —"
    mh_s  = f"${mh:.2f}" if mh else "     —"
    ma_s  = f"${ma:.2f}" if ma else "     —"
    star  = "  *" if (mh and xev(rh, mh) >= 0.20) else ""
    print(f'  {m["label"]:<36} {rh:>9.1%} {m["ml_h"]:>7.1%}  {mh_s:>9} {ma_s:>9}  {evh_s:>8} {eva_s:>8}{star}')

# ── HANDICAP ───────────────────────────────────────────────────────────────
print()
print('  HANDICAP MARKET  (line = home-team line; +ve home giving pts, -ve home receiving)')
print(f'  {"Game":<36} {"R Mrg":>6} {"ML Mrg":>7}  {"Mkt Line":>9} {"Price":>6}  {"P(R)":>6} {"P(ML)":>6}  {"EV(R)":>7} {"EV(ML)":>7}')
print('  ' + '-' * W)
for k, m in model.items():
    mk = mkt[k]
    line  = mk['hcap_line']
    price = mk['hcap_price']
    if line is None or price is None:
        continue
    rm  = m['rules_margin']
    mlm = m['ml_margin']
    pr  = p_hcap(rm, line)
    pm  = p_hcap(mlm, line)
    evr = xev(pr, price)
    evm = xev(pm, price)
    both = evr >= 0.20 and evm >= 0.20
    one  = evr >= 0.20
    star = "  **" if both else ("  *" if one else "")
    print(f'  {m["label"]:<36} {rm:>+6.1f} {mlm:>+7.1f}  {line:>+9.1f} ${price:>4.2f}  {pr:>6.1%} {pm:>6.1%}  {evr:>+7.1%} {evm:>+7.1%}{star}')

# ── TOTALS ─────────────────────────────────────────────────────────────────
print()
print('  TOTALS MARKET')
print(f'  {"Game":<36} {"R Tot":>6} {"ML Tot":>7}  {"Mkt Line":>9} {"Price":>6} {"Bet":>6}  {"P(R)":>6} {"P(ML)":>6}  {"EV(R)":>7} {"EV(ML)":>7}')
print('  ' + '-' * W)
for k, m in model.items():
    mk = mkt[k]
    tl = mk['total_line']
    tp = mk['total_price']
    if tl is None or tp is None:
        continue
    rt  = m['rules_total']
    mlt = m['ml_total']
    if rt < tl:
        bet = 'UNDER'
        pr  = p_under(rt,  tl)
        pm  = p_under(mlt, tl)
    else:
        bet = 'OVER'
        pr  = p_over(rt,  tl)
        pm  = p_over(mlt, tl)
    evr = xev(pr, tp)
    evm = xev(pm, tp)
    both = evr >= 0.20 and evm >= 0.20
    one  = evr >= 0.20
    star = "  **" if both else ("  *" if one else "")
    print(f'  {m["label"]:<36} {rt:>6.1f} {mlt:>7.1f}  {tl:>9.1f} ${tp:>4.2f} {bet:>6}  {pr:>6.1%} {pm:>6.1%}  {evr:>+7.1%} {evm:>+7.1%}{star}')

print()
print('  *  EV >= 20% rules model only     **  BOTH models >= 20% (highest confidence)')
print('=' * W)

# ── TOP 3 ──────────────────────────────────────────────────────────────────
print()
print('  TOP 3 EDGES')
print('  ' + '=' * (W - 2))

edges = []

# Adelaide handicap
rm, mlm, line, price = 42.2, 28.2, -11.5, 1.91
pr = p_hcap(rm, line); pm = p_hcap(mlm, line)
edges.append(('Adelaide -11.5 HANDICAP', 'HANDICAP', 'Adelaide vs Port (Showdown)', rm, mlm, line, price, pr, pm, xev(pr,price), xev(pm,price),
    'Both models: Adelaide wins big (rules +42.2 / ML +28.2). Market only -11.5.\n      Showdown rivalry — market discounts form; our model does not (watch-out).'))

# Collingwood +21.5 handicap
rm, mlm, line, price = -5.0, -3.8, -21.5, 1.91
pr = p_hcap(rm, line); pm = p_hcap(mlm, line)
edges.append(('Collingwood +21.5 HANDICAP', 'HANDICAP', 'Collingwood vs Hawthorn', rm, mlm, line, price, pr, pm, xev(pr,price), xev(pm,price),
    'Both models: Hawthorn by 4-5pts. Market says Hawthorn by 21.5 — 16pt gap.\n      ELO stale: Hawthorn may have moved after R7 ANZAC Day result.'))

# COL/HAW under totals
rt, mlt, tl, tp = 169.6, 166.4, 179.5, 1.91
pr = p_under(rt, tl); pm = p_under(mlt, tl)
edges.append(('UNDER 179.5 TOTALS', 'TOTALS', 'Collingwood vs Hawthorn', rt, mlt, tl, tp, pr, pm, xev(pr,tp), xev(pm,tp),
    'Both models: 166-170 combined. Market line 179.5 is 10-13pts above our models.\n      Note: edges #2 and #3 are the same game, different markets (correlated risk).'))

for i, (name, mtype, game, rm, mlm, line, price, pr, pm, evr, evm, notes) in enumerate(edges, 1):
    print(f'''
  #{i}  {name}  @  ${price:.2f}
      Game:  {game}
      Rules: {rm:+.1f}   ML: {mlm:+.1f}   Mkt line: {line:+.1f}
      P(covers):  {pr:.1%} (rules)  /  {pm:.1%} (ML)
      EV:         {evr:+.1%} (rules)  /  {evm:+.1%} (ML)
      {notes}''')

print()
print('  Odds sourced via web search 2026-05-01. Verify at Bet365 before acting.')
print('  Model ELOs are R6-only — R7 results not ingested. Two rounds of drift.')
print('=' * W)
