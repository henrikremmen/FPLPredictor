import { useEffect, useState } from "react";
import type { Position } from "@fplmodell/api-client";
import { formatMoney } from "@fplmodell/shared";
import { QueryState } from "../components/QueryState";
import { Segmented } from "../components/Segmented";
import { Card, Section } from "../components/ui";
import { PlayerRow } from "../components/PlayerRow";
import { useMarket, useSellCandidates } from "../hooks/useFeatures";
import { loadPreferences, savePreferences, type StoredPreferences } from "../lib/storage";

const POSITION_OPTIONS: { value: Position | "ALL"; label: string }[] = [
  { value: "ALL", label: "All" },
  { value: "GK", label: "Goalkeeper" },
  { value: "DEF", label: "Defence" },
  { value: "MID", label: "Midfield" },
  { value: "FWD", label: "Forward" },
];

const PRICE_OPTIONS = [50, 70, 90, 110, 130, 150];

/** Buy and sell candidates filtered by position and price; respects exclusions. */
export function MarketPanel() {
  const [prefs, setPrefs] = useState<StoredPreferences | null>(null);

  useEffect(() => {
    loadPreferences().then(setPrefs);
  }, []);

  const position = prefs?.marketPosition ?? "ALL";
  const maxPrice = prefs?.marketMaxPrice ?? 150;

  const update = (next: Partial<StoredPreferences>) => {
    const merged = { marketPosition: position, marketMaxPrice: maxPrice, ...next };
    setPrefs(merged);
    savePreferences(merged);
  };

  const market = useMarket(position, maxPrice);
  const sells = useSellCandidates();

  if (!prefs) return null;

  return (
    <>
      <Segmented
        value={position}
        onChange={(value) => update({ marketPosition: value as Position | "ALL" })}
        options={POSITION_OPTIONS}
      />
      <Segmented
        value={String(maxPrice)}
        onChange={(value) => update({ marketMaxPrice: Number(value) })}
        options={PRICE_OPTIONS.map((value) => ({ value: String(value), label: formatMoney(value) }))}
      />

      <Section title="Buy candidates">
        <QueryState query={market} isEmpty={(data) => data.players.length === 0} emptyLabel="No players match the filter.">
          {(data) => (
            <Card>
              {data.players.map((player) => (
                <PlayerRow key={player.id} player={player} />
              ))}
            </Card>
          )}
        </QueryState>
      </Section>

      <Section title="Sell candidates" subtitle="Ranked from your squad">
        <QueryState query={sells} isEmpty={(data) => data.players.length === 0} emptyLabel="No sell candidates right now.">
          {(data) => (
            <Card>
              {data.players.map((player) => (
                <PlayerRow key={player.id} player={player} />
              ))}
            </Card>
          )}
        </QueryState>
      </Section>
    </>
  );
}
