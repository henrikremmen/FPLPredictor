import { StyleSheet, Text, View } from "react-native";
import type { Player, Position } from "@fplmodell/api-client";
import { formatPoints } from "@fplmodell/shared";
import { colors, radii, spacing, typography } from "../theme";

const ROW_ORDER: Position[] = ["GK", "DEF", "MID", "FWD"];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const last = parts[parts.length - 1] ?? name;
  return last.slice(0, 2).toUpperCase();
}

function PlayerChip({ player }: { player: Player }) {
  return (
    <View style={styles.chipWrap}>
      {player.role ? (
        <View style={[styles.roleBadge, player.role === "C" && styles.roleBadgeCaptain]}>
          <Text style={styles.roleBadgeLabel}>{player.role}</Text>
        </View>
      ) : null}
      <View style={styles.avatar}>
        <Text style={styles.avatarLabel}>{initials(player.name)}</Text>
      </View>
      <Text style={styles.chipName} numberOfLines={1}>
        {player.name}
      </Text>
      <Text style={styles.chipPoints}>{formatPoints(player.decision_points ?? player.recommended_points, 1)}</Text>
    </View>
  );
}

export function PitchView({ starters }: { starters: Player[] }) {
  const rows = ROW_ORDER.map((position) => starters.filter((player) => player.position === position)).filter(
    (row) => row.length > 0,
  );

  return (
    <View style={styles.pitch}>
      <View style={styles.centerLine} />
      <View style={styles.centerCircle} />
      {rows.map((row, index) => (
        <View key={index} style={styles.row}>
          {row.map((player) => (
            <PlayerChip key={player.id} player={player} />
          ))}
        </View>
      ))}
    </View>
  );
}

export function BenchStrip({ bench }: { bench: Player[] }) {
  const ordered = [...bench].sort((a, b) => Number(a.bench_order ?? 0) - Number(b.bench_order ?? 0));
  return (
    <View style={styles.benchStrip}>
      <Text style={typography.eyebrow}>Benk</Text>
      <View style={styles.benchRow}>
        {ordered.map((player, index) => (
          <View key={player.id} style={styles.benchChip}>
            <Text style={styles.benchOrder}>{index + 1}</Text>
            <Text style={styles.benchName} numberOfLines={1}>
              {player.name}
            </Text>
            <Text style={styles.benchMeta}>{player.position}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pitch: {
    backgroundColor: "#0E3B23",
    borderRadius: radii.lg,
    borderWidth: 2,
    borderColor: "#1D5C3A",
    paddingVertical: spacing.lg,
    paddingHorizontal: spacing.sm,
    gap: spacing.lg,
    overflow: "hidden",
  },
  centerLine: {
    position: "absolute",
    top: "50%",
    left: 0,
    right: 0,
    height: 1,
    backgroundColor: "#1D5C3A",
  },
  centerCircle: {
    position: "absolute",
    top: "50%",
    left: "50%",
    width: 70,
    height: 70,
    marginTop: -35,
    marginLeft: -35,
    borderRadius: 35,
    borderWidth: 1,
    borderColor: "#1D5C3A",
  },
  row: { flexDirection: "row", justifyContent: "space-evenly" },
  chipWrap: { alignItems: "center", width: 70, gap: 2 },
  roleBadge: {
    position: "absolute",
    top: -6,
    right: 6,
    zIndex: 1,
    backgroundColor: colors.viceCaptain,
    borderRadius: radii.sm,
    paddingHorizontal: 4,
    paddingVertical: 1,
  },
  roleBadgeCaptain: { backgroundColor: colors.captain },
  roleBadgeLabel: { fontSize: 10, fontWeight: "800", color: "#141A22" },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarLabel: { fontSize: 13, fontWeight: "700", color: colors.textPrimary },
  chipName: { fontSize: 11, fontWeight: "600", color: "#EAF0F6", textAlign: "center" },
  chipPoints: { fontSize: 11, fontWeight: "700", color: colors.accent },
  benchStrip: { gap: spacing.sm },
  benchRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  benchChip: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    width: 96,
    gap: 2,
  },
  benchOrder: { fontSize: 10, fontWeight: "800", color: colors.textMuted },
  benchName: { fontSize: 12, fontWeight: "600", color: colors.textPrimary },
  benchMeta: { fontSize: 11, color: colors.textSecondary },
});
