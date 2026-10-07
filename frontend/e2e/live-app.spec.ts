import { expect, test, type Page } from "@playwright/test";

const consoleErrors: string[] = [];

async function importLiveTeam(page: Page, horizon = "8") {
  page.on("console", message => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  await page.goto("/");
  await page.locator(".load-form select").first().selectOption(horizon);
  const responsePromise = page.waitForResponse(
    response => response.url().includes("/api/team/import"),
  );
  await page.locator(".load-form button.primary").click();
  const response = await responsePromise;
  expect(response.status(), await response.text()).toBe(200);
  await expect(page.locator("main h1").first()).not.toHaveText("Load your team");
}

test.beforeEach(() => consoleErrors.splice(0));

test("real 8-GW import, lineup, market and transfers", async ({ page }) => {
  await importLiveTeam(page);

  await page.locator(".sidebar nav button", { hasText: "Lineup" }).click();
  await expect(page.locator(".pitch-player")).toHaveCount(11);
  await expect(page.locator(".bench-row")).toHaveCount(4);

  await page.locator(".sidebar nav button", { hasText: "Market" }).click();
  const marketResponse = page.waitForResponse(
    response => new URL(response.url()).pathname.endsWith("/market"),
  );
  await page.getByRole("button", { name: "Show candidates" }).click();
  expect((await marketResponse).status()).toBe(200);
  await expect(page.locator(".market-columns section").first().locator(".player-row"))
    .toHaveCount(30);

  await page.locator(".sidebar nav button", { hasText: "Transfers" }).click();
  await page.locator(".number-picker button").first().click();
  const transferResponse = page.waitForResponse(
    response => new URL(response.url()).pathname.endsWith("/transfers"),
  );
  await page.getByRole("button", { name: "Find best plan" }).click();
  expect((await transferResponse).status()).toBe(200);
  await expect(page.locator(".transfer-plan").first()).toBeVisible();

  await page.getByRole("button", { name: "Select outgoing players" }).click();
  await expect(page.locator(".transfer-player-grid button")).toHaveCount(15);
  const selectedName = await page.locator(".transfer-player-grid button strong").first().textContent();
  await page.locator(".transfer-player-grid button").first().click();
  const targetedResponse = page.waitForResponse(
    response => new URL(response.url()).pathname.endsWith("/transfers"),
  );
  await page.getByRole("button", { name: "Find best replacements" }).click();
  const targeted = await targetedResponse;
  expect(targeted.status()).toBe(200);
  const targetedRequest = targeted.request().postDataJSON();
  expect(targetedRequest.outgoing_ids).toHaveLength(1);
  await expect(page.locator(".transfer-plan .moves").first()).toContainText(selectedName ?? "");
  expect(consoleErrors).toEqual([]);
});

test("real 8-GW optimizer renders all eight rounds", async ({ page }) => {
  await importLiveTeam(page);
  await page.locator(".sidebar nav button", { hasText: "Multiweek plan" }).click();
  const planResponse = page.waitForResponse(
    response => new URL(response.url()).pathname.endsWith("/plan"),
  );
  await page.getByRole("button", { name: "Create plan" }).click();
  expect((await planResponse).status()).toBe(200);
  await expect(page.locator(".plan-week")).toHaveCount(8);
  await expect(page.getByText(/global optimum proven|best plan found within time limit/i))
    .toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("real strategy centre renders a prioritized manager brief", async ({ page }) => {
  await importLiveTeam(page, "3");
  await page.locator(".sidebar nav button", { hasText: "Strategy centre" }).click();
  const strategyResponse = page.waitForResponse(
    response => new URL(response.url()).pathname.endsWith("/strategy"),
  );
  await page.getByRole("button", { name: "Create weekly plan" }).click();
  expect((await strategyResponse).status()).toBe(200);
  await expect(page.locator(".strategy-hero")).toBeVisible();
  expect(await page.locator(".action-list button").count()).toBeGreaterThanOrEqual(4);
  await expect(page.getByRole("heading", { name: "Price radar" })).toBeVisible();
  await expect(page.locator(".watchlist-grid section")).toHaveCount(3);
  expect(consoleErrors).toEqual([]);
});

test("manual squad correction loads the active squad and legal replacements", async ({ page }) => {
  const positions = ["GK", "GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"] as const;
  const squad = positions.map((position, index) => ({
    id: index + 1, name: `Player ${index + 1}`, position, team: `T${index + 1}`,
    team_id: index + 1, opponent: "TEST (H)", price: 50, selling_price: 50,
    recommended_points: 3 + index / 10, status: "a",
  }));
  const options = [...squad, {
    id: 99, name: "Replacement", position: "DEF" as const, team: "NEW", team_id: 20,
    opponent: "TEST (A)", price: 45, recommended_points: 4.5, status: "a",
  }];
  const team = {
    session_id: "manual-test", entry_id: 1, event: 4, target_event: 5,
    manager_name: "Test Manager", team_name: "Test XI", bank: 10,
    free_transfers: 2, deadline: "2026-09-19T10:00:00Z", horizon: 3,
    risk_profile: "balanced", forecast_path: "fixture.csv", chip_status: {},
    team_value: 1000, squad_source: "fpl_public", manual_changes: [], squad,
    lineup: { formation: "3-4-3", projected_total: 50, expected_total: 50,
      captain_margin: 1, starters: squad.slice(0, 11), bench: squad.slice(11) },
  };
  await page.route("**/api/team/import", route => route.fulfill({ json: team }));
  await page.route("**/api/team/manual-test/squad-options", route => route.fulfill({
    json: { players: options },
  }));
  await page.goto("/");
  await page.locator(".load-form button.primary").click();
  await page.locator(".sidebar nav button", { hasText: "Edit squad" }).click();
  await expect(page.locator(".current-squad-editor .player-row")).toHaveCount(15);

  const selects = page.locator(".manual-transfer-row select");
  await selects.first().selectOption({ index: 1 });
  await expect(selects.nth(1)).toBeEnabled();
  expect(await selects.nth(1).locator("option").count()).toBeGreaterThan(1);
  await expect(page.getByRole("button", { name: "Sync actual squad" })).toBeVisible();
  expect(consoleErrors).toEqual([]);
});

test("real manager analysis renders season, Gameweek, league and risk views", async ({ page }) => {
  await importLiveTeam(page, "3");
  const analyticsResponse = page.waitForResponse(
    response => new URL(response.url()).pathname.endsWith("/analytics"),
  );
  await page.locator(".sidebar nav button", { hasText: "Analysis" }).click();
  expect((await analyticsResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { name: "Points vs global average" })).toBeVisible();
  await expect(page.locator(".analytics-table tbody tr")).toHaveCount(5);

  await page.getByRole("button", { name: "Gameweek", exact: true }).click();
  await expect(page.locator(".squad-analysis-table tbody tr")).toHaveCount(15);
  await expect(page.getByRole("heading", { name: "What helped your rank" })).toBeVisible();

  await page.getByRole("button", { name: "Mini-league", exact: true }).click();
  await expect(page.getByRole("heading", { name: "A på bachelor boys" })).toBeVisible();
  await expect(page.locator(".ownership-list > div").first()).toBeVisible();

  await page.getByRole("button", { name: "Risk & differentials" }).click();
  await expect(page.getByRole("heading", { name: "Model-backed differentials" })).toBeVisible();
  expect(await page.locator(".decision-row").count()).toBeGreaterThan(0);
  expect(consoleErrors).toEqual([]);
});
