import { expect, test, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

const positions = ['GK','GK','DEF','DEF','DEF','DEF','DEF','MID','MID','MID','MID','MID','FWD','FWD','FWD'];
const players = [...positions.map((position, i) => ({ id: i + 1, name: `Player ${i + 1}`, position, team: `T${Math.floor(i / 3) + 1}`, team_id: Math.floor(i / 3) + 1,
  price: 50, selling_price: 50, recommended_points: 4, decision_points: 4, opponent: 'OPP (H)', status: 'a', availability: 1 })),
  { id: 16, name: 'Upgrade', position: 'MID', team: 'T6', team_id: 6, price: 50, recommended_points: 10, decision_points: 10, opponent: 'OPP (H)', status: 'a', availability: 1 }];
const context = { revision: 'version-1', forecast_at: '2026-10-10T08:00:00Z', observed_at: '2026-10-10T07:58:00Z', model_family: 'test', source_url: 'https://fantasy.premierleague.com/api/bootstrap-static/' };
const team = { session_id: 'test', entry_id: 1, event: 5, target_event: 6, manager_name: 'Manager', team_name: 'Workspace team', bank: 0, free_transfers: 0, deadline: '2026-10-10T10:00:00Z', horizon: 3, risk_profile: 'balanced', forecast_path: 'snapshot/forecast.csv', forecast_context: context,
  chip_status: {}, squad_source: 'fpl_public', manual_changes: [], squad: players.slice(0, 15), lineup: { formation: '3-4-3', projected_total: 48, expected_total: 48, captain_margin: 0, starters: players.slice(0, 11), bench: players.slice(11, 15) } };
const upsideTeam = { ...team, risk_profile: 'upside', lineup: { ...team.lineup, projected_total: 60,
  starters: team.lineup.starters.map(p => ({ ...p, decision_points: 5.5 })), bench: team.lineup.bench.map(p => ({ ...p, decision_points: 4.5 })) } };
const transfer = { number: 1, outgoing_ids: [], global_optimum: true, plans: [{ out: 'Player 8', in: 'Upgrade', cost: 5, money_left: 0, lineup_gain: 12, expected_gain: 12, hit: 4, net_gain: 8, expected_net_gain: 8, projected_total: 56, is_global_optimum: true }] };
const timelineWeek = (event: number, ids: number[], extra: Record<string, unknown> = {}) => ({
  event, points: 50 + event, total_points: 50 * event, rank: 1000, overall_rank: 5000 - event * 100, rank_change: event === 1 ? null : 100,
  bank: 5, value: 1000, transfers_made: 0, transfer_cost: 0, bench_points: 3, chip: null, automatic_subs: [], transfers: [], final: true,
  picks: ids.map((id, i) => ({ id, name: id === 16 ? 'Upgrade' : `Player ${id}`, team: 'T1', position: positions[i], slot: i + 1,
    multiplier: i === 0 ? 2 : i < 11 ? 1 : 0, is_captain: i === 0, is_vice_captain: i === 1, points: 2, minutes: 90 })),
  ...extra,
});
const squadAfterMove = players.slice(0, 15).map(p => p.id === 8 ? 16 : p.id);
// TIMELINE_FIXTURE=/abs/timeline.json swaps in a real API payload for screenshots.
const timeline = process.env.TIMELINE_FIXTURE ? JSON.parse(readFileSync(process.env.TIMELINE_FIXTURE, 'utf8')) : { entry_id: 1, caveat: 'Player points stay provisional until FPL data-checks the round.', weeks: [
  timelineWeek(1, players.slice(0, 15).map(p => p.id)),
  timelineWeek(2, squadAfterMove, { chip: 'bboost', transfers_made: 1, transfer_cost: 4, rank_change: -50,
    transfers: [{ in: { id: 16, name: 'Upgrade', team: 'T6', position: 'MID', cost: 55 }, out: { id: 8, name: 'Player 8', team: 'T3', position: 'MID', cost: 50 } }] }),
  timelineWeek(3, squadAfterMove, { final: false }),
] };
const loopClosed = { event: 11, deadline: '2026-11-21T11:00:00Z', hours_to_deadline: 300, window_opens_at: '2026-11-20T05:00:00Z', window_open: false,
  locked: false, lock_bundle: null, missed_locks: [], window_hours: 30, command: '.venv/bin/python src/prospective_loop.py auto',
  job: { state: 'idle', error: null, result: null, elapsed_seconds: 0 },
  fpl_data: { checkout: true, latest_snapshot_at: '2026-11-06T03:00:00Z', age_hours: 3, stale: false, exported_rounds: [1, 2], alert_hours: 36 } };
const modelCard = { generated_at: '2026-11-06T15:00:00Z', production: { model_path: 'm', model_family: 'market_hgb', caveat: null },
  rounds: { shown: 2, counted_v1: 1, counted_v2: 0, needed: 8 }, claim: 'No model is declared better until a pre-registered criterion is met.',
  leaderboard: [{ model: 'incumbent', rounds_shown: 2, rounds_counted: 1, team_points_diff_mean: 0, team_points_diff_ci: null, weekly_MAE_mean: 1.14, weekly_MAE_diff_mean: 0, brier_60plus_mean: .102, interval_coverage_mean: .871, criterion_met: false },
    { model: 'refit_20261022', rounds_shown: 1, rounds_counted: 1, team_points_diff_mean: 5, team_points_diff_ci: null, weekly_MAE_mean: 1.15, weekly_MAE_diff_mean: .01, brier_60plus_mean: .108, interval_coverage_mean: .886, criterion_met: false }],
  criterion_v2: [], calibration: { brier_60plus: .102, interval_coverage: .871, interval_nominal: .8, minutes_recalibration: { rounds: 2, needed: 6 } },
  limitations: ['Odds cover only the next one or two Gameweeks; later fixtures use the model without market data.'],
  data_quality: { generated_at: '2026-11-06T15:00:00Z', fpl_data: { checkout: true, latest_snapshot_at: '2026-11-06T14:55:00Z', age_hours: 1, stale: false, exported_rounds: [8, 9], alert_hours: 36 },
    capture: { capture: 'c', age_hours: 1, odds_coverage: { '10': 1, '11': 1, '12': 0 }, market_fallback_share: .75, sources: {} },
    code_coverage: { players: 670, with_history: 534, share: .797 }, understat: 'research only', missed_locks: [9], last_evaluated_round: 8,
    consequences: ['No odds for GW12–12: those forecasts use the model without market information, so later fixtures can look flatter than they are.'] } };
async function setup(page: Page, beforeLoad?: () => Promise<void>) {
  const requests: Array<{ path: string; body: any }> = [];
  let refreshFails = false;
  let transferFails = false;
  let slowTransfer = false;
  let refreshed = false;
  let activeHorizon = 3;
  let horizonFails = false;
  let restorable = false;
  let loop: Record<string, any> = { ...loopClosed };
  const journal: any[] = [];
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !m.text().includes('status of')) errors.push(m.text()); });
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const body = request.postDataJSON();
    requests.push({ path, body });
    const json = (data: unknown, status = 200) => route.fulfill({ status, json: data });
    if (path.endsWith('/import')) return json(body?.risk_profile === 'upside' ? upsideTeam : team);
    if (request.method() === 'GET' && path === '/api/team/test') {
      if (refreshed) return json({ ...team, forecast_context: { ...context, revision: 'version-2', forecast_at: '2026-10-10T09:00:00Z' } });
      return restorable ? json(team) : json({ detail: 'Session expired' }, 404);
    }
    if (path.endsWith('/timeline')) return json(timeline);
    if (path.endsWith('/horizon')) {
      if (horizonFails) return json({ detail: 'Saved forecast is missing this horizon' }, 400);
      activeHorizon = body.horizon;
      return json({ ...team, horizon: activeHorizon, forecast_context: { ...context, revision: `horizon-${activeHorizon}` } });
    }
    if (path.endsWith('/news-assumptions')) return json({ proposals: [
      { player_id: 8, name: 'Player 8', team: 'T3', chance: 0.25, status: 'doubt', return_gw: null, quote: 'a late fitness test', current_chance: 1 }] });
    if (path.endsWith('/this-week')) {
      const upgrade = { ...players[15], role: 'C' };
      return json({
        strategy: { target_event: 6, headline: 'Player 8 → Upgrade',
          transfer: { decision: 'TRANSFER', title: 'Player 8 → Upgrade', reason: 'Multiweek optimization prefers one transfer now.', transfers_out: ['Player 8'], transfers_in: ['Upgrade'],
            hit: 0, free_transfers_before: 1, bank_after: 0.5, horizon: activeHorizon, global_optimum: true, confidence: 'high', warnings: [],
            roll_comparison: { evaluated: true, preferred_roll: false, gain_over_roll: 3.4, minimum_gain: 2, next_gw_lineup_gain: 6, incoming_starts_now: ['Upgrade'], incoming_bench_now: [], displaced_starters: ['Player 8'], candidate_out: ['Player 8'], candidate_in: ['Upgrade'] } },
          captain: { captain: { id: 16, name: 'Upgrade' }, vice_captain: { id: 1, name: 'Player 1' }, alternatives: [], margin: 2.1, confidence: 'strong', reason: 'Clear model margin.' },
          squad_health: { flagged_starters: [], flagged_players: [] },
          price_alerts: { available: true, owned_at_risk: [], targets_rising: [{ id: 16, name: 'Upgrade', price_change_projected_percent: 97 }], caveat: '' },
          plan: { weeks: [{ event: 6, transfers_out: ['Player 8'], transfers_in: ['Upgrade'] }, { event: 7, transfers_out: [], transfers_in: [], chip: null }] } },
        lineup: { formation: '3-4-3', projected_total: 50, expected_total: 50, captain_margin: 2.1,
          starters: players.slice(0, 11).map(p => p.id === 8 ? upgrade : p.id === 1 ? { ...p, role: 'VC' } : p),
          bench: players.slice(11, 15).map((p, i) => ({ ...p, bench_order: ['GK', '1', '2', '3'][i] })) },
        lineup_value: { xi_expected: 50, expected_with_autosubs: 52.5, bench_and_vice_value: 2.5, draws: 300, note: '' },
        chips: { recommendation: 'Save chips for now', best_by_chip: [] },
        robustness: { scenarios: 50, seed: 20261108, chosen_share: { 'Plan A': 0.8, Hold: 0.2 }, mean_points: {}, note: '' },
        sell: [{ id: 8, name: 'Player 8', price: 50 }], buy: [{ id: 16, name: 'Upgrade', price: 55 }],
      });
    }
    if (path.endsWith('/strategy')) return json({
      target_event: 6, headline: 'Roll the free transfer',
      transfer: { decision: 'ROLL', title: 'Roll the free transfer', reason: 'Keep flexibility for later transfers.',
        transfers_out: [], transfers_in: [], hit: 0, free_transfers_before: 1, horizon: activeHorizon,
        global_optimum: false, confidence: 'low', warnings: [],
        roll_comparison: { evaluated: true, preferred_roll: true, gain_over_roll: .3, minimum_gain: 2,
          next_gw_lineup_gain: .6, incoming_starts_now: ['Upgrade'], incoming_bench_now: [],
          displaced_starters: ['Player 8'], candidate_out: ['Player 8'], candidate_in: ['Upgrade'] } },
      captain: { captain: { name: 'Player 1' }, margin: 1, confidence: 'medium', alternatives: [] },
      squad_health: { playable_players: 15, rating: 'healthy' },
      deadline: { hours_remaining: 12, urgency: 'today' }, actions: [],
      price_alerts: { available: false, caveat: 'No prices' },
      watchlists: { top_targets: [], differentials: [], value: [], caveat: '' },
      schedule: [], principles: [], method: '', caveat: 'Uncertain forecasts'
    });
    if (path.endsWith('/squad-options')) return json({ players });
    if (path.endsWith('/changes')) return json({ previous_at: '2026-10-05T10:00:00Z', current_at: context.forecast_at, message: 'Changes to your squad', changes: [{ id: 8, name: 'Player 8', fields: { availability: { before: .75, after: 1 }, recommended_points: { before: 3, after: 4 }, news: { before: 'Knock', after: '' } } }] });
    if (path.includes('/players/')) {
      const p = players.find(p => p.id === Number(path.split('/').at(-1)))!;
      return json({ player: { ...p, news: 'Ankle injury - Expected back 18 Oct' }, weeks: [{ ...p, forecast_event: 6 }], fixtures: [{ GW: 6, kickoff_time: '2026-10-10T14:00:00Z', p_zero_minutes: .1, p_1_59_minutes: .2, p_60plus_minutes: .7, prediction_q10: 0, prediction_q90: 8 }], context, news_added: context.observed_at, injury_scenarios: [{ GW: 7, fixture: 71, kickoff_time: '2026-10-20T15:00:00Z', reported_return: '2026-10-18T00:00:00Z', conservative_points: 0, reported_return_points: 4 }], minutes_note: 'Minutes are predicted as 0, 1–59 or 60+.', uncertainty_note: 'Fixture quantiles before availability adjustment.' });
    }
    if (path.endsWith('/compare')) return json({ out_id: body.out_id, in_id: body.in_id, out: `Player ${body.out_id}`, in: 'Upgrade', hold_points: 48, buy_points: 60, hit: 4, net_gain: 8, bank_after: 0, weeks: [{ event: 6, hold: 48, buy: 60, gain: 12 }], context, caveat: 'Expected XI + captain points.' });
    if (path.endsWith('/transfers')) {
      if (slowTransfer) await new Promise(r => setTimeout(r, 800));
      return transferFails ? json({ detail: 'Temporary solver failure' }, 400) : json(transfer);
    }
    if (path.endsWith('/plan')) return json({ weeks: [{ event: 6, transfers_out: ['Player 8'], transfers_in: ['Upgrade'], free_transfers_before: 0, paid_transfers: 1, hit: 4, bank: 0, captain: 'Upgrade', formation: '3-4-3', starters: ['Upgrade'], projected_points: 56,
      chip: body?.chips ? 'triple_captain' : null, bench: ['Player 2', 'Player 12'], bench_value: .8, autosub: { xi_expected: 56, expected_with_autosubs: 58.4, bench_and_vice_value: 2.4, draws: 150, note: '' } }],
      total_projected_points: 56, discounted_objective_points: 56, global_optimum: true, caveat: 'Static prices.', bench_weights: body?.bench_weights ?? [.03, .12, .06, .03],
      bench_note: 'projected_points is XI + captain only.', chip_calendar: body?.chips ? [{ chip: 'triple_captain', event: 6, alternative_event: 7, gain_over_alternative: 3.2 }] : [],
      requirement_costs: (body?.requirements ?? []).map((r: any) => ({ ...r, cost: 1.3, weeks: 1 })) });
    if (path.endsWith('/scenarios')) return json({ plans: [
        { name: 'Hold', first_week_out: [], first_week_in: [], net_points: 150.1, hits: 0, final_bank: 0.5, free_transfers_after: 3, gain_vs_hold: 0, global_optimum: true },
        { name: 'Plan A', first_week_out: ['Player 8'], first_week_in: ['Upgrade'], net_points: 154.5, hits: 0, final_bank: 0.5, free_transfers_after: 2, gain_vs_hold: 4.4, global_optimum: true }],
      robustness: { scenarios: 50, seed: 20261108, chosen_share: { Hold: 0.2, 'Plan A': 0.8 }, mean_points: {}, note: 'Share of sampled scenarios.' },
      assumptions: Object.fromEntries((body?.overrides ?? []).map((o: any) => [String(o.player_id), o.chance])) });
    if (path.endsWith('/scenarios/breakpoint')) return json({ player_id: body.player_id, name: 'Upgrade', current_chance: 1, threshold: 0.44, above: 'sell Player 8 for Upgrade', below: 'hold',
      message: "The plan changes from 'sell Player 8 for Upgrade' to 'hold' if Upgrade's chance of playing falls below 44% (now 100%)." });
    if (path.endsWith('/journal')) {
      if (request.method() === 'POST') journal.unshift({ event: 6, recorded_at: '2026-10-10T08:00:00Z', deadline: team.deadline, forecast_at: context.forecast_at, counts: true, file: `j${journal.length}`,
        advice: { decision: 'ROLL', title: 'Roll the free transfer', reason: '', out: [], in: [], captain: 'Player 1' }, alternatives: [{ name: 'Hold', first_week_out: [], first_week_in: [], net_points: 150.1, gain_vs_hold: 0 }],
        choice: { kind: body.choice, label: body.choice === 'follow' ? 'Follow the advice' : 'Something else', note: body.note } });
      return json({ entries: journal });
    }
    if (path.endsWith('/lineup-value')) return json({ xi_expected: 48, expected_with_autosubs: 50.5, bench_and_vice_value: 2.5, draws: 300, note: 'Bench and vice-captain value.' });
    if (path.endsWith('/chips')) return json({ recommendation: 'Hold', summary: 'Compare chips', forecast_events: [6], best_by_chip: [{ chip: 'triple_captain', label: 'Triple Captain', event: 6, gain: 8, projected_points: 60, threshold: 10, decision: 'CONSIDER', available: true, reason: 'Strong captain', transfers_needed: 0, squad: [], double_players: 0, blank_players: 0 }], candidates: [] });
    if (path === '/api/loop/status') return json(loop);
    if (path === '/api/model-card') return json(modelCard);
    if (path === '/api/loop/lock') {
      if (loop.locked) return json({ detail: `GW${loop.event} is already locked.` }, 409);
      loop = { ...loop, job: { ...loop.job, state: 'running' } };
      return json(loop);
    }
    if (path.endsWith('/status')) return json(refreshed  // the refresh runs as a 202 job; the app polls this, then reloads the team
      ? { state: 'complete', stage: 'Forecast saved; reloading team', elapsed_seconds: 2, captured: 667, total: 667, error: null }
      : { state: 'running', stage: 'Downloading player histories', elapsed_seconds: 1, captured: 100, total: 667, error: null });
    if (path.endsWith('/refresh')) {
      await new Promise(r => setTimeout(r, 900));
      if (refreshFails) return json({ detail: 'Update failed: network unavailable' }, 400);
      refreshed = true;
      return json({ status: 'started' }, 202);
    }
    return json({ detail: `Unexpected route: ${path}` }, 404);
  });
  await page.goto('/');
  await beforeLoad?.();
  await page.getByLabel('FPL team ID').fill('5139814');
  await page.getByRole('button', { name: 'Load team', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'This week', exact: true })).toBeVisible();
  return { requests, errors, setLoop: (next: Record<string, any>) => { loop = next; }, allowRestore: () => { restorable = true; }, failRefresh: () => { refreshFails = true; }, failHorizon: () => { horizonFails = true; }, failTransfer: () => { transferFails = true; slowTransfer = true; }, refreshed: () => refreshed };
}
test('team ID field extracts the ID from a pasted link, ignores the Gameweek and remembers it', async ({ page }) => {
  const state = await setup(page, async () => {
    const field = page.getByLabel('FPL team ID');
    await expect(field).toHaveValue('');
    await field.fill('https://fantasy.premierleague.com/en/entry/42/event/4');
    await expect(field).toHaveValue('42');
    await page.getByRole('button', { name: 'Load team', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'This week', exact: true })).toBeVisible();
    await page.reload();
    await expect(field).toHaveValue('42');
  });
  expect(state.requests.filter(r => r.path.endsWith('/import')).map(r => r.body.reference)).toEqual(['42', '5139814']);
  expect(state.errors).toEqual([]);
});
const nav = async (page: Page, name: string) => {  // U20: a page under "More" needs the fold opened first
  const sidebar = page.locator('.sidebar nav');
  if (!(await sidebar.getByRole('button', { name, exact: true }).isVisible()))
    await sidebar.locator('details.nav-more', { has: page.locator(`button:text-is("${name}")`) }).locator('summary').click();
  await sidebar.getByRole('button', { name, exact: true }).click();
};

test('this week: the steps in order, the XI after the transfer, and a checklist to copy', async ({ page }) => {
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write']);
  const state = await setup(page);
  const week = page.getByRole('region', { name: 'This week', exact: true });
  await expect(week.getByRole('heading', { name: 'Player 8 → Upgrade' })).toBeVisible();
  await expect(week).toContainText('Player 8 (£5.0m)');
  await expect(week).toContainText('Plan A 80%');
  await expect(week).toContainText('Upgrade is close to a price rise (97%)');
  await expect(week.getByRole('heading', { name: 'Captain Upgrade' })).toBeVisible();
  await expect(week).toContainText('Including autosubs and the vice-captain: 52.5');
  await expect(week).toContainText('falls below 44%');  // the tipping point loads after the page
  await week.getByRole('checkbox').first().check();
  await week.getByRole('button', { name: 'Copy to FPL' }).click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  expect(copied.split('\n')).toEqual(['Sell: Player 8 (£5.0m)', 'Buy: Upgrade (£5.5m)', expect.stringMatching(/^Starting XI \(3-4-3\): .*Upgrade/),
    'Captain: Upgrade · Vice-captain: Player 1', expect.stringMatching(/^Bench: 1\. /), 'Chip: none']);
  state.allowRestore();
  await page.reload();
  await expect(page.getByRole('region', { name: 'This week', exact: true }).getByRole('checkbox').first()).toBeChecked();
  expect(state.errors).toEqual([]);
});

test('horizon changes keep the current strategy page, preferences and session, and recalculate advice', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Player preferences');
  await page.locator('.preference-list > div').filter({ has: page.getByRole('button', { name: 'Player 8', exact: true }) }).getByRole('button', { name: 'Lock', exact: true }).click();
  await nav(page, 'Strategy centre');
  // U10: the strategy page calculates on opening.
  await expect(page.locator('.strategy-stamp')).toContainText('3 GW');
  await page.getByLabel('Planning horizon', { exact: true }).selectOption('8');
  await expect(page.getByRole('heading', { name: 'Strategy centre', exact: true })).toBeVisible();
  await expect(page.locator('.strategy-stamp')).toContainText('8 GW');
  await expect(page.locator('.roll-comparison')).toContainText('Replaces in the XI: Player 8');
  expect(state.requests.filter(r => r.path.endsWith('/import'))).toHaveLength(1);
  // U9/U10: the overview card and the strategy page both ask; the cache makes repeats cheap.
  expect(state.requests.filter(r => r.path.endsWith('/strategy')).length).toBeGreaterThanOrEqual(2);
  expect(state.requests.filter(r => r.path.endsWith('/strategy')).at(-1)?.body.locked_ids).toEqual([8]);
  expect(state.requests.find(r => r.path.endsWith('/horizon'))?.path).toBe('/api/team/test/horizon');
  state.failHorizon();
  await page.getByLabel('Planning horizon', { exact: true }).selectOption('7');
  await expect(page.getByText('Saved forecast is missing this horizon')).toBeVisible();
  await expect(page.getByLabel('Planning horizon', { exact: true })).toHaveValue('8');
  await expect(page.locator('.strategy-stamp')).toContainText('8 GW');
  expect(state.errors).toEqual([]);
});

test('news, keyboard-accessible player detail, comparison after hits and persistent A/B drafts', async ({ page }) => {
  const state = await setup(page);
  await page.goto('/#/overview');
  await expect(page.getByRole('heading', { name: 'Since last time' })).toBeVisible();
  await expect(page.locator('.since-last')).toContainText('75% → 100%');
  await page.locator('.squad-groups').first().getByRole('button', { name: 'Player 8', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('70%');
  await expect(page.getByRole('dialog')).toContainText('Expected back 18 Oct');
  await expect(page.getByRole('region', { name: 'Return-date scenario' })).toContainText('not a calibrated recovery probability');
  await expect(page.getByRole('region', { name: 'Return-date scenario' })).toContainText('If back as reported');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await nav(page, 'Compare players');
  await page.getByLabel('Player to keep / sell').selectOption('8');
  await page.getByLabel('Player to buy').selectOption('16');
  await page.getByRole('button', { name: 'Compare after hits' }).click();
  await expect(page.locator('.comparison-result')).toContainText('Net expected gain');
  await expect(page.locator('.comparison-result')).toContainText('8.0');
  await page.getByLabel('Name for Comparison plan').fill('Plan A');
  await page.getByRole('button', { name: 'Save plan', exact: true }).click();
  await page.getByLabel('Name for Comparison plan').fill('Plan B');
  await page.getByRole('button', { name: 'Save plan', exact: true }).click();
  await nav(page, 'Saved plans');
  await page.getByRole('button', { name: 'Compare A/B' }).first().click();
  await page.getByRole('button', { name: 'Compare A/B' }).click();
  await expect(page.getByRole('columnheader', { name: 'B − A' })).toBeVisible();
  await page.reload();
  await page.getByRole('button', { name: 'Load team', exact: true }).click();
  await nav(page, 'Saved plans');
  await expect(page.getByLabel('Plan name', { exact: true })).toHaveCount(2);
  await expect(page.getByLabel('Plan name', { exact: true }).first()).toHaveValue('Plan A');
  expect(state.errors).toEqual([]);
});

test('preferences flow into transfers, multiweek and chips; refresh preserves and marks results', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Player preferences');
  await page.locator('.preference-list > div').filter({ has: page.getByRole('button', { name: 'Player 8', exact: true }) }).getByRole('button', { name: 'Lock', exact: true }).click();
  await page.getByLabel('Find a player to lock or exclude').fill('Upgrade');
  await page.getByRole('button', { name: 'Exclude', exact: true }).click();
  await nav(page, 'Transfers');
  await page.locator('.number-picker button').first().click();
  await page.getByRole('button', { name: 'Find best plan', exact: true }).click();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  expect(state.requests.find(r => r.path.endsWith('/transfers'))?.body).toMatchObject({ locked_ids: [8], excluded_ids: [16] });
  await nav(page, 'Multiweek plan');  // U10: the plan opens calculated
  await expect(page.locator('.plan-week')).toBeVisible();
  expect(state.requests.find(r => r.path.endsWith('/plan'))?.body).toMatchObject({ locked_ids: [8], excluded_ids: [16] });
  await nav(page, 'Chips');
  await page.getByRole('button', { name: 'Analyse chips' }).click();
  await expect(page.locator('.chip-card')).toBeVisible();
  expect(state.requests.find(r => r.path.endsWith('/chips'))?.body).toMatchObject({ locked_ids: [8], excluded_ids: [16] });
  await page.getByLabel('Name for Chip GW6 plan').fill('Captain chip');
  await page.locator('.chip-card').getByRole('button', { name: 'Save plan', exact: true }).click();
  await nav(page, 'Transfers');
  await expect(page.locator('.transfer-plan')).toBeVisible();
  await page.getByRole('button', { name: 'Refresh forecast', exact: true }).click();
  await expect(page.locator('.forecast-status')).toContainText('Downloading player histories');
  await expect(page.locator('.transfer-plan')).toBeVisible();
  await expect(page.locator('main > div:not([hidden]) .workspace-warning').filter({ hasText: 'Outdated result' }).first()).toBeVisible();
  await expect(page.locator('.transfer-plan').getByRole('button', { name: 'Save plan', exact: true })).toBeDisabled();
  expect(state.refreshed()).toBe(true);
  expect(state.errors).toEqual([]);
});

test('failed refresh and recalculation keep the previous results visible', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Transfers');
  await page.locator('.number-picker button').first().click();
  await page.getByRole('button', { name: 'Find best plan', exact: true }).click();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  state.failTransfer();
  await page.getByRole('button', { name: 'Find best plan', exact: true }).click();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('Temporary solver failure');
  state.failRefresh();
  await page.getByRole('button', { name: 'Refresh forecast', exact: true }).click();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  await expect(page.getByRole('alert').filter({ hasText: 'Update failed' })).toBeVisible();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  expect(state.errors).toEqual([]);
});

test('mobile comparison and player panel fit viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await setup(page);
  await page.goto('/#/overview');
  await page.locator('.squad-groups').first().getByRole('button', { name: 'Player 8', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Playing time');
  const size = await page.getByRole('dialog').boundingBox();
  expect(size!.width).toBeLessThanOrEqual(390);
  await page.getByRole('button', { name: 'Close player details' }).click();
  await page.locator('.mobile-nav').getByRole('button', { name: 'Players', exact: true }).click();
  await page.locator('.group-sheet').getByRole('button', { name: 'Compare players', exact: true }).click();
  await page.getByLabel('Player to keep / sell').selectOption('8');
  await page.getByLabel('Player to buy').selectOption('16');
  await page.getByRole('button', { name: 'Compare after hits' }).click();
  await expect(page.locator('.comparison-result')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/workspace-mobile.png', fullPage: true });
  await page.locator('.mobile-nav').getByRole('button', { name: 'Transfers & plan', exact: true }).click();
  await page.locator('.group-sheet').getByRole('button', { name: 'Transfers', exact: true }).click();
  await page.locator('.number-picker button').first().click();
  await page.getByRole('button', { name: 'Find best plan', exact: true }).click();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/workspace-mobile-transfers.png', fullPage: true });
  expect(state.errors).toEqual([]);
});

test('saved chip and transfer plans retain assumptions and warn on incompatible comparisons', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Transfers');
  await page.locator('.number-picker button').first().click();
  await page.getByRole('button', { name: 'Find best plan', exact: true }).click();
  await page.getByLabel('Name for Transfer plan').fill('Transfer A');
  await page.locator('.transfer-plan').getByRole('button', { name: 'Save plan', exact: true }).click();
  await nav(page, 'Chips');
  await page.getByRole('button', { name: 'Analyse chips' }).click();
  await page.getByLabel('Name for Chip GW6 plan').fill('Chip B');
  await page.locator('.chip-card').getByRole('button', { name: 'Save plan', exact: true }).click();
  await nav(page, 'Saved plans');
  await page.getByRole('button', { name: 'Compare A/B' }).first().click();
  await page.getByRole('button', { name: 'Compare A/B' }).click();
  await expect(page.getByText('These plans use different inputs or analysis types.', { exact: false })).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'B − A' })).toHaveCount(0);
  await page.getByText('Saved plan and assumptions', { exact: true }).first().click();
  await expect(page.getByText('Original squad:', { exact: false }).first()).toContainText('Player 8');
  await page.getByLabel('Plan name', { exact: true }).first().fill('Renamed plan');
  await page.getByRole('button', { name: 'Delete', exact: true }).last().click();
  await expect(page.getByLabel('Plan name', { exact: true })).toHaveCount(1);
  await expect(page.getByLabel('Plan name', { exact: true })).toHaveValue('Renamed plan');
  expect(state.errors).toEqual([]);
});

test('preferences persist and invalidate existing advice without discarding it', async ({ page }) => {
  await setup(page);
  await nav(page, 'Transfers');
  await page.locator('.number-picker button').first().click();
  await page.getByRole('button', { name: 'Find best plan', exact: true }).click();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  await nav(page, 'Player preferences');
  await page.locator('.preference-list > div').filter({ has: page.getByRole('button', { name: 'Player 8', exact: true }) }).getByRole('button', { name: 'Lock', exact: true }).click();
  await nav(page, 'Transfers');
  await expect(page.getByText('Outdated result:', { exact: false })).toBeVisible();
  await expect(page.locator('.transfer-plan')).toBeVisible();
  await page.getByRole('button', { name: 'Select outgoing players' }).click();
  await expect(page.locator('.transfer-player-grid').getByRole('button', { name: /Player 8 / })).toBeDisabled();
  await page.reload();
  await page.getByRole('button', { name: 'Load team', exact: true }).click();
  await nav(page, 'Player preferences');
  await expect(page.getByRole('button', { name: 'Locked: Player 8 ×' })).toBeVisible();
  await page.getByRole('button', { name: 'Clear preferences' }).click();
  await expect(page.getByRole('button', { name: 'Locked: Player 8 ×' })).toHaveCount(0);
});

test('timeline opens on the latest Gameweek and steps back with keys, buttons and the season ribbon', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Timeline');
  const stepper = page.locator('.timeline-stepper');
  await expect(stepper).toContainText('GW3');
  await expect(stepper).toContainText('provisional');
  await expect(page.locator('.round-changes')).toContainText('Same squad as GW2');
  const loads = state.requests.filter(r => r.path.endsWith('/timeline')).length;
  await page.keyboard.press('ArrowLeft');
  await expect(stepper).toContainText('GW2');
  await expect(stepper).toContainText('Bench Boost');
  await expect(page.locator('.round-changes')).toContainText('↑ Upgrade £5.5m');
  await expect(page.locator('.round-changes')).toContainText('↓ Player 8 £5.0m');
  await expect(page.locator('.round-changes')).toContainText('Hit: −4 points');
  await expect(page.locator('.pitch .joined-badge')).toHaveCount(1);
  await page.getByRole('button', { name: 'Show GW1' }).click();
  await expect(page.locator('.round-changes')).toContainText('First Gameweek of the season');
  await page.getByRole('button', { name: /^GW3: 53 points/ }).click();
  await expect(stepper).toContainText('GW3');
  expect(state.requests.filter(r => r.path.endsWith('/timeline'))).toHaveLength(loads); // stepping never refetches
  expect(state.errors).toEqual([]);
});

test('timeline fits a phone screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await setup(page);
  await page.locator('.mobile-nav').getByRole('button', { name: 'History', exact: true }).click();
  await page.locator('.group-sheet').getByRole('button', { name: 'Timeline', exact: true }).click();
  await expect(page.locator('.group-sheet')).toHaveCount(0);  // U17: the sheet closes after choosing
  await expect(page.locator('.sub-nav')).toHaveCount(0);      // and there is no second navigation
  await expect(page.locator('.timeline-stepper')).toContainText('GW3');
  await page.getByRole('button', { name: 'Show GW2' }).click();
  await expect(page.locator('.timeline-stepper')).toContainText('GW2');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(state.errors).toEqual([]);
});

test('paste team news: Claude proposes a chance of playing and Accept adds it to your assumptions', async ({ page }) => {
  const state = await setup(page);
  const week = page.getByRole('region', { name: 'This week', exact: true });
  await week.getByText('Paste team news').click();
  await week.getByLabel('Team news').fill('Player 8 faces a late fitness test.');
  await week.getByRole('button', { name: 'Read with Claude' }).click();
  await expect(week).toContainText('Player 8: 25% chance of playing (doubt) · FPL now 100% · “a late fitness test”');
  await week.getByRole('button', { name: 'Accept Player 8 at 25%' }).click();
  await expect(page.locator('.assumptions-notice')).toContainText('Your assumptions are on (1 player)');
  expect(state.requests.find(r => r.path.endsWith('/news-assumptions'))?.body).toEqual({ text: 'Player 8 faces a late fitness test.' });
  await expect.poll(() => state.requests.filter(r => r.path.endsWith('/this-week')).at(-1)?.body.overrides).toEqual([{ player_id: 8, chance: 0.25 }]);
  expect(state.errors).toEqual([]);
});

test('every page has a deep link; back and refresh keep the page without a new import', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Timeline');
  await expect(page).toHaveURL(/#\/timeline$/);
  await nav(page, 'Chips');
  await expect(page).toHaveURL(/#\/chips$/);
  await page.goBack();
  await expect(page.locator('.timeline-stepper')).toBeVisible();
  await expect(page.locator('.sidebar nav').getByRole('button', { name: 'Timeline', exact: true })).toHaveAttribute('aria-current', 'page');
  state.allowRestore();
  await page.reload();
  await expect(page.locator('.timeline-stepper')).toBeVisible();
  expect(state.requests.filter(r => r.path.endsWith('/import'))).toHaveLength(1);
  expect(state.errors).toEqual([]);
});

test('every page: buttons have accessible names and the menu works from the keyboard', async ({ page }) => {
  const state = await setup(page);
  for (const id of ['week', 'overview', 'lineup', 'strategy', 'transfers', 'plan', 'chips', 'squads', 'market', 'comparison',
    'preferences', 'analysis', 'timeline', 'model', 'scenarios', 'journal', 'squad', 'saved']) {
    await page.evaluate(hash => { window.location.hash = `/${hash}`; }, id);
    await page.waitForTimeout(100);
    const unnamed = await page.evaluate(() => [...document.querySelectorAll('button')]
      .filter(b => b.offsetParent !== null && !b.closest('details:not([open])') && !(b.innerText.trim() || b.getAttribute('aria-label') || b.getAttribute('title')))
      .map(b => b.outerHTML.slice(0, 80)));
    expect(unnamed, id).toEqual([]);
  }
  await page.locator('.sidebar nav').getByRole('button', { name: 'Lineup', exact: true }).focus();
  await page.keyboard.press('Enter');
  await expect(page).toHaveURL(/#\/lineup$/);
  await page.keyboard.press('Tab');
  await expect(page.locator('.sidebar nav').getByRole('button', { name: 'Strategy centre', exact: true })).toBeFocused();
  expect(state.errors).toEqual([]);
});

test('lineup shows the score the risk profile ranks by, with expected points alongside', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Lineup');
  await expect(page.locator('.profile-note')).toHaveCount(0);
  await expect(page.locator('.pitch-player').first()).toContainText('4.0');
  await page.getByRole('button', { name: 'Change', exact: true }).click();
  await page.getByLabel('Profile').selectOption('upside');
  await page.getByRole('button', { name: 'Reload team', exact: true }).click();
  await expect(page.locator('.profile-note')).toContainText('0.7 × expected points + 0.3 × Q90');
  await expect(page.locator('.pitch-player').first()).toContainText('5.5');
  await expect(page.locator('.bench-row').first()).toContainText('4.0 expected');
  await expect(page.getByRole('heading', { name: 'Lineup', exact: true })).toBeVisible();
  expect(state.requests.filter(r => r.path.endsWith('/import')).at(-1)?.body.risk_profile).toBe('upside');
  for (const viewport of shotDir ? [{ width: 1440, height: 900 }, { width: 390, height: 844 }] : []) {
    await page.setViewportSize(viewport);
    await page.screenshot({ path: `${shotDir}/lineup-upside-${viewport.width}.png`, fullPage: true });
  }
  expect(state.errors).toEqual([]);
});

test('lock banner: hidden between windows, lock button in the window, missed rounds and stale fpl-data noted', async ({ page }) => {
  const app = await setup(page);
  await expect(page.locator('.lock-banner')).toHaveCount(0);
  app.setLoop({ ...loopClosed, window_open: true, hours_to_deadline: 20, missed_locks: [9], fpl_data: { ...loopClosed.fpl_data, age_hours: 340, stale: true } });
  await page.reload();
  const banner = page.locator('.lock-banner');
  await expect(banner.getByText('Lock window open for GW11 – lock now')).toBeVisible();
  await expect(banner.getByText('Never locked: GW9. These rounds cannot count for the model comparison.')).toBeVisible();
  await expect(banner.getByText('fpl-data: last snapshot 340 h ago. Run src/fpl_collect.py --data-root fpl-data auto.')).toBeVisible();
  await banner.getByRole('button', { name: 'Lock GW11' }).click();
  await expect(banner.getByText('Locking GW11…')).toBeVisible();
  await expect(banner.getByRole('button', { name: 'Lock GW11' })).toHaveCount(0);
  expect(app.requests.filter(r => r.path === '/api/loop/lock')).toHaveLength(1);
  expect(app.errors).toEqual([]);
});

test('model card: data quality first, locked rounds with counts, no claim of superiority', async ({ page }) => {
  const app = await setup(page);
  await page.goto('/#/model');
  const card = page.getByRole('region', { name: 'Model card' });
  await expect(card.getByRole('heading', { name: 'Model and data' })).toBeVisible();
  await expect(card.getByText('No model is declared better until a pre-registered criterion is met.')).toBeVisible();
  await expect(card.getByText(/No odds for GW12/)).toBeVisible();
  await expect(card.getByText('GW10 100% · GW11 100% · GW12 0%')).toBeVisible();
  await expect(card.getByText('1 of 8 counted (v1) · 0 of 8 (v2)')).toBeVisible();
  await expect(card.getByRole('row', { name: /Production \(incumbent\)/ })).toContainText('87%');
  await expect(card.getByText(/never locked: GW9/)).toBeVisible();
  expect(app.errors).toEqual([]);
});

test('planner: bench weights travel with every plan, chips and requirements are priced, autosub value shown', async ({ page }) => {
  const app = await setup(page);
  await page.goto('/#/preferences');
  await page.getByLabel('Bench 1').fill('0.2');
  await page.goto('/#/plan');
  await page.getByLabel(/Plan chips too/).check();
  await page.getByRole('combobox', { name: 'Requirement' }).selectOption('sell_in');
  await page.getByRole('combobox', { name: 'Player', exact: true }).selectOption('8');
  await page.getByRole('button', { name: 'Add requirement' }).click();
  await expect(page.getByText('Sell Player 8 in GW6')).toBeVisible();
  await page.getByRole('button', { name: 'Recalculate' }).click();
  await expect(page.getByText('Triple Captain in GW6')).toBeVisible();
  await expect(page.getByText(/nearest alternative GW7/)).toBeVisible();
  await expect(page.getByText(/costs/)).toContainText('1.3 points');
  await expect(page.getByText(/With autosubs and vice-captain: 58.4/)).toBeVisible();
  const sent = app.requests.filter(r => r.path.endsWith('/plan')).at(-1)!.body;
  expect(sent.chips).toBe(true);
  expect(sent.bench_weights).toEqual([0.03, 0.2, 0.06, 0.03]);
  expect(sent.requirements).toEqual([{ kind: 'sell_in', player_id: 8, event: 6 }]);
  await page.goto('/#/lineup');
  await expect(page.getByText(/with autosubs and vice-captain/)).toContainText('50.5');
  expect(app.errors).toEqual([]);
});

test('phone: every visible control on every page is at least 44 px high and the section sheet closes with Escape', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);
  for (const id of ['week', 'overview', 'lineup', 'strategy', 'transfers', 'plan', 'chips', 'squads', 'market', 'fixtures', 'comparison',
    'preferences', 'analysis', 'timeline', 'model', 'scenarios', 'journal', 'squad', 'saved']) {
    await page.evaluate(hash => { window.location.hash = `/${hash}`; }, id);
    await page.waitForTimeout(150);
    const small = await page.evaluate(() => [...document.querySelectorAll('main button, main select, main input:not([type=checkbox]), main summary')]
      .filter(el => (el as HTMLElement).offsetParent !== null && !el.closest('table') && !el.matches('.link-button, .player-link'))
      .filter(el => el.getBoundingClientRect().height < 43.5).map(el => `${el.tagName} ${(el as HTMLElement).innerText.slice(0, 30)}`));
    expect(small, id).toEqual([]);
  }
  await page.locator('.mobile-nav').getByRole('button', { name: 'Players', exact: true }).click();
  await expect(page.locator('.group-sheet')).toBeVisible();
  await page.locator('.group-sheet button').first().focus();
  await page.keyboard.press('Escape');
  await expect(page.locator('.group-sheet')).toHaveCount(0);
});

test('scenarios: plan A/B against holding, your assumptions with reset, tipping point, and the decision journal', async ({ page }) => {
  const app = await setup(page);
  await page.goto('/#/scenarios');
  const scenarios = page.getByRole('region', { name: 'Scenarios' });
  await expect(scenarios.getByRole('row', { name: /Plan A/ })).toContainText('80% of scenarios');
  await expect(scenarios.getByRole('row', { name: /Hold/ })).toContainText('No transfer');
  await expect(scenarios).toContainText('seed 20261108');
  const assumptions = page.getByRole('region', { name: 'Your assumptions' });
  await assumptions.getByRole('combobox', { name: 'Player', exact: true }).selectOption('8');
  await assumptions.getByLabel('Chance of playing (%)').fill('25');
  await assumptions.getByRole('button', { name: 'Set assumption' }).click();
  await expect(page.locator('.assumptions-notice')).toContainText('Your assumptions are on (1 player)');
  await expect.poll(() => app.requests.filter(r => r.path.endsWith('/scenarios')).at(-1)?.body.overrides).toEqual([{ player_id: 8, chance: 0.25 }]);
  await page.getByRole('region', { name: 'Tipping point' }).getByRole('combobox', { name: 'Player', exact: true }).selectOption('16');
  await page.getByRole('button', { name: 'Find the tipping point' }).click();
  await expect(page.locator('.tipping-point')).toContainText('falls below 44%');
  await page.locator('.assumptions-notice').getByRole('button', { name: 'Reset' }).click();
  await expect(page.locator('.assumptions-notice')).toHaveCount(0);
  await page.goto('/#/week');
  await page.getByText('Record my decision').click();
  await page.getByLabel('My decision').selectOption('follow');
  await page.getByLabel('Note').fill('trust the model');
  await page.getByRole('button', { name: 'Save to journal' }).click();
  await expect(page.getByText('Recorded in your decision journal.')).toBeVisible();
  await page.goto('/#/journal');
  await expect(page.getByRole('region', { name: 'Decision journal' })).toContainText('Follow the advice');
  await expect(page.getByRole('region', { name: 'Decision journal' })).toContainText('“trust the model”');
  expect(app.errors).toEqual([]);
});

// Visual review only: SCREENSHOT_DIR=/abs/dir npm run test:e2e:workspace --prefix frontend
const shotDir = process.env.SCREENSHOT_DIR;
for (const [size, viewport] of [['390x844', { width: 390, height: 844 }], ['1440x900', { width: 1440, height: 900 }]] as const) {
  test(`screenshots of every page at ${size}`, async ({ page }) => {
    test.skip(!shotDir, 'Set SCREENSHOT_DIR to capture screenshots');
    await page.setViewportSize(viewport);
    await setup(page, () => page.screenshot({ path: `${shotDir}/${size}/00-load.png`, fullPage: true }));
    const pages = ['week', 'overview', 'lineup', 'strategy', 'transfers', 'plan', 'chips', 'squads', 'market', 'comparison',
      'preferences', 'analysis', 'timeline', 'model', 'squad', 'saved', 'fixtures', 'scenarios', 'journal'];
    for (const [index, id] of pages.entries()) {
      await page.evaluate(hash => { window.location.hash = `/${hash}`; }, id);
      await page.waitForTimeout(250);
      await page.screenshot({ path: `${shotDir}/${size}/${String(index + 1).padStart(2, '0')}-${id}.png`, fullPage: true });
    }
  });
}
