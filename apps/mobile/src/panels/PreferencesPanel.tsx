import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import type { Player } from "@fplmodell/api-client";
import { formatMoney } from "@fplmodell/shared";
import { QueryState } from "../components/QueryState";
import { Button, Card, Section } from "../components/ui";
import { useWorkspace } from "../context/workspace-context";
import { useSquadOptions, useTeam } from "../hooks/useTeam";
import { colors, radii, spacing, typography } from "../theme";

/** Lock owned players or exclude anyone; every optimiser on this device respects it. */
export function PreferencesPanel() {
  const team = useTeam();
  const options = useSquadOptions();
  const workspace = useWorkspace();
  const [query, setQuery] = useState("");
  const { locked_ids, excluded_ids } = workspace.constraints;

  return (
    <>
      <Text style={styles.caption}>
        {locked_ids.length} locked · {excluded_ids.length} excluded. Applies to transfers, multiweek plan, chips and strategy.
      </Text>
      <Section title="Your squad" subtitle="Locked players are never sold">
        <QueryState query={team}>
          {(data) => (
            <Card>
              {data.squad.map((player) => (
                <Row key={player.id} player={player}
                  action={<Toggle label="Lock" activeLabel="Locked" active={locked_ids.includes(player.id)} onPress={() => workspace.toggleLock(player.id)} name={player.name} />} />
              ))}
            </Card>
          )}
        </QueryState>
      </Section>
      <Section title="Exclude a player" subtitle="Never bought; an owned player is sold">
        <TextInput value={query} onChangeText={setQuery} placeholder="Search by name" placeholderTextColor={colors.textMuted}
          accessibilityLabel="Find a player to exclude" autoCorrect={false} style={styles.input} />
        <QueryState query={options}>
          {({ players }) => {
            const term = query.trim().toLowerCase();
            const shown = players.filter((player) => excluded_ids.includes(player.id)
              || (term.length >= 2 && player.name.toLowerCase().includes(term))).slice(0, 20);
            return shown.length ? (
              <Card>
                {shown.map((player) => (
                  <Row key={player.id} player={player}
                    action={<Toggle label="Exclude" activeLabel="Excluded" active={excluded_ids.includes(player.id)} onPress={() => workspace.toggleExclude(player.id)} name={player.name} />} />
                ))}
              </Card>
            ) : <Text style={styles.caption}>Type at least two letters of a name.</Text>;
          }}
        </QueryState>
      </Section>
      <Button label="Clear preferences" variant="secondary" disabled={!locked_ids.length && !excluded_ids.length}
        onPress={workspace.clearConstraints} />
    </>
  );
}

function Row({ player, action }: { player: Player; action: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <View style={{ flex: 1 }}>
        <Text style={typography.body}>{player.name}</Text>
        <Text style={styles.caption}>{player.position} · {player.team} · {formatMoney(player.price)}</Text>
      </View>
      {action}
    </View>
  );
}

function Toggle({ label, activeLabel, active, onPress, name }: {
  label: string; activeLabel: string; active: boolean; onPress: () => void; name: string;
}) {
  return (
    <Pressable onPress={onPress} accessibilityRole="switch" accessibilityState={{ checked: active }}
      accessibilityLabel={`${label} ${name}`} style={[styles.toggle, active && styles.toggleActive]}>
      <Text style={[styles.toggleLabel, active && { color: colors.onAccent }]}>{active ? activeLabel : label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  caption: typography.caption,
  row: { minHeight: 52, flexDirection: "row", alignItems: "center", gap: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border },
  toggle: { minHeight: 44, minWidth: 88, paddingHorizontal: spacing.md, borderRadius: radii.pill, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  toggleActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  toggleLabel: { color: colors.textPrimary, fontWeight: "600" },
  input: { minHeight: 44, backgroundColor: colors.field, borderRadius: radii.md, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, color: colors.textPrimary },
});
