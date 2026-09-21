import { ActivityIndicator, View } from "react-native";
import { Redirect } from "expo-router";
import { useSession } from "../src/context/session-context";
import { colors } from "../src/theme";

export default function Gate() {
  const { isLoading, isOnboarded } = useSession();

  if (isLoading) {
    return (
      <View style={{ flex: 1, backgroundColor: colors.background, alignItems: "center", justifyContent: "center" }}>
        <ActivityIndicator color={colors.accent} />
      </View>
    );
  }

  return <Redirect href={isOnboarded ? "/(tabs)" : "/onboarding"} />;
}
