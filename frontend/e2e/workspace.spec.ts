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
async function setup(page: Page, beforeLoad?: () => Promise<void>) {
  const requests: Array<{ path: string; body: any }> = [];
  let refreshFails = false;
  let transferFails = false;
  let slowTransfer = false;
  let refreshed = false;
  let activeHorizon = 3;
  let horizonFails = false;
  let restorable = false;
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
    if (request.method() === 'GET' && path === '/api/team/test') return restorable ? json(team) : json({ detail: 'Session expired' }, 404);
    if (path.endsWith('/timeline')) return json(timeline);
    if (path.endsWith('/horizon')) {
      if (horizonFails) return json({ detail: 'Saved forecast is missing this horizon' }, 400);
      activeHorizon = body.horizon;
      return json({ ...team, horizon: activeHorizon, forecast_context: { ...context, revision: `horizon-${activeHorizon}` } });
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
    if (path.endsWith('/plan')) return json({ weeks: [{ event: 6, transfers_out: ['Player 8'], transfers_in: ['Upgrade'], free_transfers_before: 0, paid_transfers: 1, hit: 4, bank: 0, captain: 'Upgrade', formation: '3-4-3', starters: ['Upgrade'], projected_points: 56 }], total_projected_points: 56, discounted_objective_points: 56, global_optimum: true, caveat: 'Static prices.' });
    if (path.endsWith('/chips')) return json({ recommendation: 'Hold', summary: 'Compare chips', forecast_events: [6], best_by_chip: [{ chip: 'triple_captain', label: 'Triple Captain', event: 6, gain: 8, projected_points: 60, threshold: 10, decision: 'CONSIDER', available: true, reason: 'Strong captain', transfers_needed: 0, squad: [], double_players: 0, blank_players: 0 }], candidates: [] });
    if (path.endsWith('/status')) return json({ state: 'running', stage: 'Downloading player histories', elapsed_seconds: 1, captured: 100, total: 667, error: null });
    if (path.endsWith('/refresh')) {
      await new Promise(r => setTimeout(r, 900));
      if (refreshFails) return json({ detail: 'Update failed: network unavailable' }, 400);
      refreshed = true;
      return json({ ...team, forecast_context: { ...context, revision: 'version-2', forecast_at: '2026-10-10T09:00:00Z' } });
    }
    return json({ detail: `Unexpected route: ${path}` }, 404);
  });
  await page.goto('/');
  await beforeLoad?.();
  await page.getByLabel('FPL team ID').fill('5139814');
  await page.getByRole('button', { name: 'Load team', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Workspace team' })).toBeVisible();
  return { requests, errors, allowRestore: () => { restorable = true; }, failRefresh: () => { refreshFails = true; }, failHorizon: () => { horizonFails = true; }, failTransfer: () => { transferFails = true; slowTransfer = true; }, refreshed: () => refreshed };
}
test('team ID field extracts the ID from a pasted link, ignores the Gameweek and remembers it', async ({ page }) => {
  const state = await setup(page, async () => {
    const field = page.getByLabel('FPL team ID');
    await expect(field).toHaveValue('');
    await field.fill('https://fantasy.premierleague.com/en/entry/42/event/4');
    await expect(field).toHaveValue('42');
    await page.getByRole('button', { name: 'Load team', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Workspace team' })).toBeVisible();
    await page.reload();
    await expect(field).toHaveValue('42');
  });
  expect(state.requests.filter(r => r.path.endsWith('/import')).map(r => r.body.reference)).toEqual(['42', '5139814']);
  expect(state.errors).toEqual([]);
});
const nav = (page: Page, name: string) => page.locator('.sidebar nav').getByRole('button', { name, exact: true }).click();

test('horizon changes keep the current strategy page, preferences and session, and recalculate advice', async ({ page }) => {
  const state = await setup(page);
  await nav(page, 'Player preferences');
  await page.locator('.preference-list > div').filter({ has: page.getByRole('button', { name: 'Player 8', exact: true }) }).getByRole('button', { name: 'Lock', exact: true }).click();
  await nav(page, 'Strategy centre');
  await page.getByRole('button', { name: 'Create weekly plan' }).click();
  await expect(page.locator('.strategy-stamp')).toContainText('3 GW');
  await page.getByLabel('Planning horizon', { exact: true }).selectOption('8');
  await expect(page.getByRole('heading', { name: 'Strategy centre', exact: true })).toBeVisible();
  await expect(page.locator('.strategy-stamp')).toContainText('8 GW');
  await expect(page.locator('.roll-comparison')).toContainText('Replaces in the XI: Player 8');
  expect(state.requests.filter(r => r.path.endsWith('/import'))).toHaveLength(1);
  expect(state.requests.filter(r => r.path.endsWith('/strategy'))).toHaveLength(2);
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
  await expect(page.locator('.comparison-result')).toContainText('8.00');
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
  await nav(page, 'Multiweek plan');
  await page.getByRole('button', { name: 'Create plan' }).click();
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
  await page.locator('.squad-groups').first().getByRole('button', { name: 'Player 8', exact: true }).click();
  await expect(page.getByRole('dialog')).toContainText('Playing time');
  const size = await page.getByRole('dialog').boundingBox();
  expect(size!.width).toBeLessThanOrEqual(390);
  await page.getByRole('button', { name: 'Close player details' }).click();
  await page.locator('.mobile-nav').getByRole('button', { name: 'Players', exact: true }).click();
  await page.locator('.sub-nav').getByRole('button', { name: 'Compare players', exact: true }).click();
  await page.getByLabel('Player to keep / sell').selectOption('8');
  await page.getByLabel('Player to buy').selectOption('16');
  await page.getByRole('button', { name: 'Compare after hits' }).click();
  await expect(page.locator('.comparison-result')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/workspace-mobile.png', fullPage: true });
  await page.locator('.mobile-nav').getByRole('button', { name: 'Transfers & plan', exact: true }).click();
  await page.locator('.sub-nav').getByRole('button', { name: 'Transfers', exact: true }).click();
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
  await page.locator('.sub-nav').getByRole('button', { name: 'Timeline', exact: true }).click();
  await expect(page.locator('.timeline-stepper')).toContainText('GW3');
  await page.getByRole('button', { name: 'Show GW2' }).click();
  await expect(page.locator('.timeline-stepper')).toContainText('GW2');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
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
  for (const id of ['overview', 'lineup', 'strategy', 'transfers', 'plan', 'chips', 'squads', 'market', 'comparison',
    'preferences', 'analysis', 'timeline', 'squad', 'saved']) {
    await page.evaluate(hash => { window.location.hash = `/${hash}`; }, id);
    await page.waitForTimeout(100);
    const unnamed = await page.evaluate(() => [...document.querySelectorAll('button')]
      .filter(b => b.offsetParent !== null && !(b.innerText.trim() || b.getAttribute('aria-label') || b.getAttribute('title')))
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
  await expect(page.locator('.pitch-player').first()).toContainText('4.00');
  await page.getByRole('button', { name: 'Change', exact: true }).click();
  await page.getByLabel('Profile').selectOption('upside');
  await page.getByRole('button', { name: 'Reload team', exact: true }).click();
  await expect(page.locator('.profile-note')).toContainText('0.7 × expected points + 0.3 × Q90');
  await expect(page.locator('.pitch-player').first()).toContainText('5.50');
  await expect(page.locator('.bench-row').first()).toContainText('4.00 expected');
  await expect(page.getByRole('heading', { name: 'Lineup', exact: true })).toBeVisible();
  expect(state.requests.filter(r => r.path.endsWith('/import')).at(-1)?.body.risk_profile).toBe('upside');
  for (const viewport of shotDir ? [{ width: 1440, height: 900 }, { width: 390, height: 844 }] : []) {
    await page.setViewportSize(viewport);
    await page.screenshot({ path: `${shotDir}/lineup-upside-${viewport.width}.png`, fullPage: true });
  }
  expect(state.errors).toEqual([]);
});

// Visual review only: SCREENSHOT_DIR=/abs/dir npm run test:e2e:workspace --prefix frontend
const shotDir = process.env.SCREENSHOT_DIR;
for (const [size, viewport] of [['390x844', { width: 390, height: 844 }], ['1440x900', { width: 1440, height: 900 }]] as const) {
  test(`screenshots of every page at ${size}`, async ({ page }) => {
    test.skip(!shotDir, 'Set SCREENSHOT_DIR to capture screenshots');
    await page.setViewportSize(viewport);
    await setup(page, () => page.screenshot({ path: `${shotDir}/${size}/00-load.png`, fullPage: true }));
    const pages = ['overview', 'lineup', 'strategy', 'transfers', 'plan', 'chips', 'squads', 'market', 'comparison',
      'preferences', 'analysis', 'timeline', 'squad', 'saved'];
    for (const [index, id] of pages.entries()) {
      await page.evaluate(hash => { window.location.hash = `/${hash}`; }, id);
      await page.waitForTimeout(250);
      await page.screenshot({ path: `${shotDir}/${size}/${String(index + 1).padStart(2, '0')}-${id}.png`, fullPage: true });
    }
  });
}
