import { Pressable, StyleSheet, Text, View } from "react-native";
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
      return { title: "Cannot connect to backend", detail: error.message };
    }
    if (error.kind === "timeout") {
      return { title: "Timeout", detail: error.message };
    }
    return { title: "Something went wrong", detail: error.message };
  }
  return { title: "Something went wrong", detail: "Unknown error." };
}

/** Uniform loading / error (offline, timeout, HTTP) / empty / data states for a query screen. */
export function QueryState<T>({ query, children, isEmpty, emptyLabel }: QueryStateProps<T>) {
  if (query.isLoading) {
    // Skeleton rows in the shape of the content, so the layout does not jump when data arrives.
    return (
      <View style={styles.skeleton} accessibilityRole="progressbar" accessibilityLabel="Loading">
        {[0.9, 0.7, 0.8].map((width, index) => (
          <View key={index} style={styles.skeletonCard}>
            <View style={[styles.skeletonLine, { width: `${width * 60}%` }]} />
            <View style={[styles.skeletonLine, styles.skeletonThin, { width: `${width * 100}%` }]} />
          </View>
        ))}
        <Text style={styles.caption}>Loading…</Text>
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
          <Text style={styles.retryLabel}>Try again</Text>
        </Pressable>
      </View>
    );
  }

  if (query.data === undefined || (isEmpty && isEmpty(query.data))) {
    return (
      <View style={styles.center}>
        <Text style={styles.caption}>{emptyLabel ?? "No data yet."}</Text>
      </View>
    );
  }

  return <>{children(query.data)}</>;
}

const styles = StyleSheet.create({
  skeleton: { gap: spacing.sm, paddingVertical: spacing.sm },
  skeletonCard: { backgroundColor: colors.surface, borderRadius: radii.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.sm },
  skeletonLine: { height: 14, borderRadius: radii.sm, backgroundColor: colors.surfaceRaised },
  skeletonThin: { height: 10 },
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
