import { ScrollView, StyleSheet, View, type ScrollViewProps } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, spacing } from "../theme";

interface ScreenProps extends ScrollViewProps {
  scroll?: boolean;
  padded?: boolean;
}

/** Consistent dark background + safe-area handling for every tab screen. */
export function Screen({ children, scroll = true, padded = true, contentContainerStyle, ...rest }: ScreenProps) {
  if (!scroll) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
        <View style={[padded && styles.padded, { flex: 1 }]}>{children}</View>
      </SafeAreaView>
    );
  }
  return (
    <SafeAreaView style={styles.safe} edges={["top", "left", "right"]}>
      <ScrollView
        contentContainerStyle={[padded && styles.padded, styles.content, contentContainerStyle]}
        keyboardShouldPersistTaps="handled"
        {...rest}
      >
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  padded: { paddingHorizontal: spacing.lg },
  content: { paddingBottom: spacing.xxl, gap: spacing.md },
});
