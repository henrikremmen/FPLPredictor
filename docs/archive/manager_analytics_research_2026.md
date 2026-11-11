# Manager analytics, mini-leagues and rank risk

Updated 18 September 2026. The aim is to support ambitious FPL managers using
public endpoints, without login or access to private account data.

## Separate outcomes from decision quality

1. **Outcome:** actual points, overall rank, league rank and team value.
2. **Process:** captaincy, bench decisions, hits and immediate transfer swings.
3. **Relative impact:** the value of a player's points against the relevant field.
4. **Future decisions:** model expectations, league/top-rank EO, availability,
   price and planning horizon.

A strong decision can have a bad outcome and vice versa. The app therefore shows
historical results alongside forward-looking expectations.

## Effective ownership

The [Premier League glossary](https://www.premierleague.com/en/news/2683145)
defines a differential as a player below 10% ownership and EO as starting share
plus captain share. The app uses the general multiplier formulation:

```text
EO = 100 × sum(points multipliers) / number of analysed managers
relative player contribution = player points × (your multiplier − EO / 100)
```

This handles the bench, captaincy, Triple Captain and Bench Boost. Summed across
players, relative contribution approximates gains/losses against the league's
average scoring lineup, before individual transfer hits.

EO must describe the relevant field.
[LiveFPL's explanation](https://www.livefpl.com/blog/fpl-effective-ownership)
shows why top-rank EO differs from overall ownership. The app displays:

- Overall FPL ownership.
- Exact mini-league EO, or a labelled sample for leagues above 100 members.
- A stratified sample of 25 public teams around ranks 1, 2,500, 5,000, 7,500 and
  10,000. This is an indicator, not a census of the top 10,000.

## Captaincy and risk

[FPL winner Ali Jahangirov](https://www.premierleague.com/en/news/3527473)
discusses captaincy when protecting a position or chasing. A popular captain
reduces relative variance; a model-backed alternative can help close a gap.

- **Protect:** league leader; prioritise expected points and major EO threats.
- **Balanced:** early/mid-season or a manageable gap; expected points first,
  differentials only when supported by the model.
- **Chase:** at least 20 points behind with eight or fewer rounds remaining;
  consider model-backed differentials and an alternative captain.

The captain matrix's isolated rank advantage is
`model points × (2 − league EO/100)`. It does not subtract the opportunity cost
of not captaining the second-best candidate, so it cannot determine captaincy alone.

## Public data

- `entry/{id}/history/`: points, rank, hits, bench and value by Gameweek.
- `entry/{id}/event/{gw}/picks/`: locked squad, bench and captain.
- `event/{gw}/live/`: actual player points and minutes.
- `entry/{id}/transfers/`: incoming and outgoing players.
- `leagues-classic/{id}/standings/`: league standings and overall-rank sample.
- `bootstrap-static/`: ownership, Gameweek averages and player metadata.

Endpoint reference: [FPL API documentation](https://github.com/jakesmith1997-sfc/fpl-api).
Public picks appear only after the deadline. Exact authenticated bank, free
transfers and pending moves remain outside the analysis.

## App tabs

**Season:** points against the global average, cumulative difference, overall
rank and percentile, best/worst round, value, positional contributions,
captain bonus/opportunity, bench points, hits, gross transfer swings and
comparison with the stratified sample.

**Gameweek:** the actual 15-player historical squad, minutes, raw/counting
points, global ownership and league EO; largest positive and negative relative
contributions, including players the manager did not own.

**Mini-league:** standings, gap, rank history, league template, starting/captain
shares, EO and explicit protect/balanced/chase mode.

**Risk & differentials:** model-backed unowned players with low league EO,
high-projection unowned threats, owned-player leverage and the captain matrix,
using both league and sampled top-rank EO.

## Performance and interpretation

Responses are cached for five minutes. Independent histories/picks use at most
eight concurrent requests. A missing rival endpoint reduces the sample rather
than failing the entire report. Large leagues are capped at 100 managers and
labelled as samples.

Transfer swing is the same-round gross points difference between incoming and
outgoing players. It is not causal and excludes future points. Captain
opportunity compares against the best player in the scoring XI; it is a
retrospective opportunity cost, not a measure of pre-deadline information quality.
