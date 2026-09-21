import { useMemo, useState } from "react";
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { router } from "expo-router";
import { ApiError, type Player, type SquadChange } from "@fplmodell/api-client";
import { formatMoney } from "@fplmodell/shared";
import { Screen } from "../src/components/Screen";
import { QueryState } from "../src/components/QueryState";
import { Button, Card, Section } from "../src/components/ui";
import { useResetSquad, useSquadOptions, useTeam, useUpdateSettings, useUpdateSquad } from "../src/hooks/useTeam";
import { colors, radii, spacing, typography } from "../src/theme";

type Mode = "settings" | "synchronize" | "apply_transfers";

export default function Correction() {
  const team = useTeam();
  return (
    <Screen>
      <QueryState query={team}>{(data) => <CorrectionForm bank={data.bank} freeTransfers={data.free_transfers} squad={data.squad} />}</QueryState>
    </Screen>
  );
}

function CorrectionForm({ bank, freeTransfers, squad }: { bank: number; freeTransfers: number; squad: Player[] }) {
  const [mode, setMode] = useState<Mode>("settings");

  return (
    <>
      <Text style={typography.title}>Korriger lag</Text>
      <Text style={styles.lead}>
        Offentlige laglenker viser ikke bytter gjort etter siste deadline. Velg riktig korrigering under.
      </Text>

      <View style={styles.modeRow}>
        <ModeChip label="Bank/FT" active={mode === "settings"} onPress={() => setMode("settings")} />
        <ModeChip label="Allerede gjort" active={mode === "synchronize"} onPress={() => setMode("synchronize")} />
        <ModeChip label="Nye bytter" active={mode === "apply_transfers"} onPress={() => setMode("apply_transfers")} />
      </View>

      {mode === "settings" ? <SettingsForm bank={bank} freeTransfers={freeTransfers} /> : null}
      {mode !== "settings" ? <SquadForm mode={mode} squad={squad} bank={bank} freeTransfers={freeTransfers} /> : null}

      <ResetSection />
    </>
  );
}

function ModeChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      style={[styles.modeChip, active && styles.modeChipActive]}
    >
      <Text style={[styles.modeChipLabel, active && styles.modeChipLabelActive]}>{label}</Text>
    </Pressable>
  );
}

function SettingsForm({ bank, freeTransfers }: { bank: number; freeTransfers: number }) {
  const [bankInput, setBankInput] = useState(String(bank / 10));
  const [ftInput, setFtInput] = useState(String(freeTransfers));
  const updateSettings = useUpdateSettings();

  const onSubmit = () => {
    const bankValue = Math.round(Number(bankInput.replace(",", ".")) * 10);
    const ftValue = Number(ftInput);
    if (!Number.isFinite(bankValue) || bankValue < 0 || bankValue > 200) return;
    if (!Number.isFinite(ftValue) || ftValue < 0 || ftValue > 5) return;
    updateSettings.mutate(
      { bank: bankValue, freeTransfers: ftValue },
      { onSuccess: () => router.back() },
    );
  };

  return (
    <Card>
      <Text style={typography.eyebrow}>Faktisk bank og gratisbytter</Text>
      <View style={styles.fieldRow}>
        <View style={{ flex: 1 }}>
          <Text style={styles.fieldLabel}>Bank (£m)</Text>
          <TextInput
            value={bankInput}
            onChangeText={setBankInput}
            keyboardType="decimal-pad"
            style={styles.input}
          />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.fieldLabel}>Gratisbytter</Text>
          <TextInput value={ftInput} onChangeText={setFtInput} keyboardType="number-pad" style={styles.input} />
        </View>
      </View>
      {updateSettings.isError ? <ErrorLine error={updateSettings.error} /> : null}
      <Button label="Lagre" onPress={onSubmit} loading={updateSettings.isPending} />
    </Card>
  );
}

function SquadForm({
  mode,
  squad,
  bank,
  freeTransfers,
}: {
  mode: "synchronize" | "apply_transfers";
  squad: Player[];
  bank: number;
  freeTransfers: number;
}) {
  const options = useSquadOptions();
  const updateSquad = useUpdateSquad();
  const [changes, setChanges] = useState<SquadChange[]>([]);
  const [pendingOutId, setPendingOutId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [syncBank, setSyncBank] = useState(String(bank / 10));
  const [syncFt, setSyncFt] = useState(String(freeTransfers));

  const usedOutIds = new Set(changes.map((change) => change.out_id));
  const availableOut = squad.filter((player) => !usedOutIds.has(player.id));
  const pendingOutPlayer = squad.find((player) => player.id === pendingOutId) ?? null;

  const inCandidates = useMemo(() => {
    if (!pendingOutPlayer || !options.data) return [];
    const usedInIds = new Set(changes.map((change) => change.in_id));
    const query = search.trim().toLowerCase();
    return options.data.players.filter(
      (candidate) =>
        candidate.position === pendingOutPlayer.position &&
        !usedInIds.has(candidate.id) &&
        candidate.id !== pendingOutPlayer.id &&
        (query === "" || candidate.name.toLowerCase().includes(query)),
    );
  }, [options.data, pendingOutPlayer, search, changes]);

  const addChange = (inId: number) => {
    if (pendingOutId == null) return;
    setChanges((previous) => [...previous, { out_id: pendingOutId, in_id: inId }]);
    setPendingOutId(null);
    setSearch("");
  };

  const removeChange = (index: number) => {
    setChanges((previous) => previous.filter((_, i) => i !== index));
  };

  const nameFor = (id: number) =>
    squad.find((player) => player.id === id)?.name ?? options.data?.players.find((player) => player.id === id)?.name ?? `#${id}`;

  const onSubmit = () => {
    if (changes.length === 0) return;
    const bankValue = mode === "synchronize" ? Math.round(Number(syncBank.replace(",", ".")) * 10) : undefined;
    const ftValue = mode === "synchronize" ? Number(syncFt) : undefined;
    updateSquad.mutate(
      { mode, changes, bank: bankValue, freeTransfers: ftValue },
      { onSuccess: () => router.back() },
    );
  };

  if (pendingOutId != null) {
    return (
      <Card>
        <Text style={typography.eyebrow}>Inn for {pendingOutPlayer?.name}</Text>
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Søk spiller…"
          placeholderTextColor={colors.textMuted}
          style={styles.input}
        />
        <QueryState query={options}>
          {() => (
            <View style={{ maxHeight: 360 }}>
              {inCandidates.slice(0, 30).map((candidate) => (
                <Pressable key={candidate.id} onPress={() => addChange(candidate.id)} style={styles.pickRow}>
                  <Text style={styles.pickName}>{candidate.name}</Text>
                  <Text style={styles.pickMeta}>
                    {candidate.team} · {formatMoney(candidate.price)}
                  </Text>
                </Pressable>
              ))}
              {inCandidates.length === 0 ? <Text style={styles.lead}>Ingen treff.</Text> : null}
            </View>
          )}
        </QueryState>
        <Button label="Avbryt" variant="secondary" onPress={() => setPendingOutId(null)} />
      </Card>
    );
  }

  return (
    <>
      <Card>
        <Text style={typography.eyebrow}>{mode === "synchronize" ? "Erstatt spillere" : "Simuler nye bytter"} (1–5)</Text>
        {changes.map((change, index) => (
          <View key={`${change.out_id}-${change.in_id}`} style={styles.changeRow}>
            <Text style={styles.changeText}>
              {nameFor(change.out_id)} → {nameFor(change.in_id)}
            </Text>
            <Pressable onPress={() => removeChange(index)} accessibilityRole="button">
              <Text style={styles.removeLabel}>Fjern</Text>
            </Pressable>
          </View>
        ))}
        {changes.length < 5 ? (
          <View style={{ maxHeight: 260 }}>
            {availableOut.map((player) => (
              <Pressable key={player.id} onPress={() => setPendingOutId(player.id)} style={styles.pickRow}>
                <Text style={styles.pickName}>{player.name}</Text>
                <Text style={styles.pickMeta}>{player.position}</Text>
              </Pressable>
            ))}
          </View>
        ) : null}
      </Card>

      {mode === "synchronize" ? (
        <Card>
          <Text style={typography.eyebrow}>Faktisk bank og gratisbytter etter byttene</Text>
          <View style={styles.fieldRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>Bank (£m)</Text>
              <TextInput value={syncBank} onChangeText={setSyncBank} keyboardType="decimal-pad" style={styles.input} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>Gratisbytter</Text>
              <TextInput value={syncFt} onChangeText={setSyncFt} keyboardType="number-pad" style={styles.input} />
            </View>
          </View>
        </Card>
      ) : null}

      {updateSquad.isError ? <ErrorLine error={updateSquad.error} /> : null}
      <Button label="Lagre bytter" onPress={onSubmit} disabled={changes.length === 0} loading={updateSquad.isPending} />
    </>
  );
}

function ResetSection() {
  const reset = useResetSquad();
  const onReset = () => {
    Alert.alert("Tilbakestill til FPL", "Fjerner lokale korrigeringer og laster laget på nytt fra FPL.", [
      { text: "Avbryt", style: "cancel" },
      {
        text: "Tilbakestill",
        style: "destructive",
        onPress: () => reset.mutate(undefined, { onSuccess: () => router.back() }),
      },
    ]);
  };
  return (
    <Section title="Tilbakestilling">
      <Button label="Tilbakestill til FPL" variant="danger" onPress={onReset} loading={reset.isPending} />
    </Section>
  );
}

function ErrorLine({ error }: { error: unknown }) {
  return <Text style={styles.error}>{error instanceof ApiError ? error.message : "Noe gikk galt."}</Text>;
}

const styles = StyleSheet.create({
  lead: { ...typography.caption },
  modeRow: { flexDirection: "row", gap: spacing.sm },
  modeChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radii.pill,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modeChipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  modeChipLabel: { ...typography.caption, fontWeight: "700" },
  modeChipLabelActive: { color: "#06231A" },
  fieldRow: { flexDirection: "row", gap: spacing.md },
  fieldLabel: { ...typography.caption, marginBottom: 4 },
  input: {
    backgroundColor: colors.surfaceRaised,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    color: colors.textPrimary,
    fontSize: 15,
  },
  pickRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  pickName: { ...typography.body },
  pickMeta: { ...typography.caption },
  changeRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  changeText: { ...typography.body },
  removeLabel: { ...typography.caption, color: colors.danger, fontWeight: "700" },
  error: { ...typography.caption, color: colors.danger },
});
