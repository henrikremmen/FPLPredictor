import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { ApiError } from "@fplmodell/api-client";
import { colors, radii, spacing, typography } from "../theme";

interface QueryLike<T> {
  data: T | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

interface QueryStateProps<T> {
  query: QueryLike<T>;
  children: (data: T) => React.ReactNode;
  isEmpty?: (data: T) => boolean;
  emptyLabel?: string;
}

function errorCopy(error: unknown): { title: string; detail: string } {
  if (error instanceof ApiError) {
    if (error.kind === "network") {
      return { title: "Ingen kontakt med backend", detail: error.message };
    }
    if (error.kind === "timeout") {
      return { title: "Tidsavbrudd", detail: error.message };
    }
    return { title: "Noe gikk galt", detail: error.message };
  }
  return { title: "Noe gikk galt", detail: "Ukjent feil." };
}

/** Uniform loading / error (offline, timeout, HTTP) / empty / data states for a query screen. */
export function QueryState<T>({ query, children, isEmpty, emptyLabel }: QueryStateProps<T>) {
  if (query.isLoading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={colors.accent} />
        <Text style={styles.caption}>Laster…</Text>
      </View>
    );
  }

  if (query.isError) {
    const { title, detail } = errorCopy(query.error);
    return (
      <View style={styles.center}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.caption}>{detail}</Text>
        <Pressable style={styles.retryButton} onPress={() => query.refetch()} accessibilityRole="button">
          <Text style={styles.retryLabel}>Prøv igjen</Text>
        </Pressable>
      </View>
    );
  }

  if (query.data === undefined || (isEmpty && isEmpty(query.data))) {
    return (
      <View style={styles.center}>
        <Text style={styles.caption}>{emptyLabel ?? "Ingen data ennå."}</Text>
      </View>
    );
  }

  return <>{children(query.data)}</>;
}

const styles = StyleSheet.create({
  center: {
    paddingVertical: spacing.xxl,
    alignItems: "center",
    gap: spacing.sm,
  },
  title: { ...typography.heading, textAlign: "center" },
  caption: { ...typography.caption, textAlign: "center", maxWidth: 320 },
  retryButton: {
    marginTop: spacing.sm,
    backgroundColor: colors.surfaceRaised,
    borderColor: colors.border,
    borderWidth: 1,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radii.pill,
  },
  retryLabel: { ...typography.body, fontWeight: "600" },
});
