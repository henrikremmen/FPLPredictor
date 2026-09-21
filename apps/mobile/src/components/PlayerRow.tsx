import { StyleSheet, Text, View } from "react-native";
import type { Player } from "@fplmodell/api-client";
import { formatMoney, formatPoints } from "@fplmodell/shared";
import { colors, radii, spacing, typography } from "../theme";
import { Badge } from "./ui";

function statusTone(status: string): "default" | "warning" | "negative" {
  if (status === "a") return "default";
  if (status === "d") return "warning";
  return "negative";
}

function statusLabel(status: string): string | null {
  if (status === "a") return null;
  if (status === "d") return "Tvil";
  if (status === "i") return "Skadet";
  if (status === "s") return "Suspendert";
  if (status === "u") return "Forlatt klubb";
  return status;
}

interface PlayerRowProps {
  player: Player;
  right?: React.ReactNode;
  onPress?: () => void;
}

export function PlayerRow({ player, right }: PlayerRowProps) {
  const flag = statusLabel(player.status);
  return (
    <View style={styles.row}>
      <View style={styles.identity}>
        <View style={styles.nameLine}>
          {player.role ? (
            <View style={styles.roleChip}>
              <Text style={styles.roleChipLabel}>{player.role}</Text>
            </View>
          ) : null}
          <Text style={styles.name} numberOfLines={1}>
            {player.name}
          </Text>
        </View>
        <Text style={styles.meta}>
          {player.position} · {player.team} · {player.opponent}
        </Text>
        {flag ? <Badge label={flag} tone={statusTone(player.status)} /> : null}
      </View>
      {right ?? (
        <View style={styles.numbers}>
          <Text style={styles.points}>{formatPoints(player.decision_points ?? player.recommended_points)}p</Text>
          <Text style={styles.price}>{formatMoney(player.price)}</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
    gap: spacing.sm,
  },
  identity: { flex: 1, gap: 2 },
  nameLine: { flexDirection: "row", alignItems: "center", gap: 6 },
  name: { ...typography.body, fontWeight: "600", flexShrink: 1 },
  meta: { ...typography.caption },
  roleChip: {
    backgroundColor: colors.captain,
    borderRadius: radii.sm,
    paddingHorizontal: 5,
    paddingVertical: 1,
  },
  roleChipLabel: { fontSize: 10, fontWeight: "800", color: "#241900" },
  numbers: { alignItems: "flex-end" },
  points: { ...typography.body, fontWeight: "700" },
  price: { ...typography.caption },
});
