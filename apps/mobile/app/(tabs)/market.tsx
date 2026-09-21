import { useEffect, useState } from "react";
import { Text } from "react-native";
import type { Position } from "@fplmodell/api-client";
import { formatMoney } from "@fplmodell/shared";
import { Screen } from "../../src/components/Screen";
import { QueryState } from "../../src/components/QueryState";
import { Segmented } from "../../src/components/Segmented";
import { Card, Section } from "../../src/components/ui";
import { PlayerRow } from "../../src/components/PlayerRow";
import { useMarket, useSellCandidates } from "../../src/hooks/useFeatures";
import { loadPreferences, savePreferences, type StoredPreferences } from "../../src/lib/storage";
import { typography } from "../../src/theme";

const POSITION_OPTIONS: { value: Position | "ALL"; label: string }[] = [
  { value: "ALL", label: "Alle" },
  { value: "GK", label: "Keeper" },
  { value: "DEF", label: "Forsvar" },
  { value: "MID", label: "Midtbane" },
  { value: "FWD", label: "Spiss" },
];

const PRICE_OPTIONS = [50, 70, 90, 110, 130, 150];

export default function Market() {
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

  if (!prefs) return <Screen />;

  return (
    <Screen>
      <Text style={typography.title}>Marked</Text>

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

      <Section title="Kjøpskandidater">
        <QueryState query={market} isEmpty={(data) => data.players.length === 0} emptyLabel="Ingen spillere matcher filteret.">
          {(data) => (
            <Card>
              {data.players.map((player) => (
                <PlayerRow key={player.id} player={player} />
              ))}
            </Card>
          )}
        </QueryState>
      </Section>

      <Section title="Salgskandidater" subtitle="Rangert fra ditt lag">
        <QueryState query={sells} isEmpty={(data) => data.players.length === 0} emptyLabel="Ingen salgskandidater akkurat nå.">
          {(data) => (
            <Card>
              {data.players.map((player) => (
                <PlayerRow key={player.id} player={player} />
              ))}
            </Card>
          )}
        </QueryState>
      </Section>
    </Screen>
  );
}
