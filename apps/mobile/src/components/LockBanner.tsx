import { useState } from "react";
import { StyleSheet, Text } from "react-native";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@fplmodell/api-client";
import { formatDeadline, loopBanner } from "@fplmodell/shared";
import { api } from "../lib/api";
import { Button, Card } from "./ui";
import { colors, typography } from "../theme";

/** Plan O2: same banner as the web app. Polls slowly, faster while a lock runs. */
export function LockBanner() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const status = useQuery({
    queryKey: ["loop-status"],
    queryFn: () => api.loopStatus(),
    refetchInterval: (query) => (query.state.data?.job.state === "running" ? 3000 : 60000),
  });
  const lock = useMutation({
    mutationFn: () => api.lockRound(),
    onSuccess: (next) => queryClient.setQueryData(["loop-status"], next),
    onError: (e) => setError(e instanceof ApiError ? e.message : "Could not start the lock."),
  });
  const data = status.data;
  const banner = data ? loopBanner(data) : null;
  if (!banner && !error) return null;
  return (
    <Card style={[styles.card, banner?.tone === "info" && styles.info]}>
      {banner?.headline ? <Text style={typography.heading}>{banner.headline}</Text> : null}
      {banner?.notes.map((note) => <Text key={note} style={styles.note}>{note}</Text>)}
      {banner?.canLock ? (
        <>
          <Button label={`Lock GW${data?.event}`} loading={lock.isPending} onPress={() => { setError(null); lock.mutate(); }} />
          <Text style={styles.note}>Runs the prospective loop on the computer running the API. {data?.deadline ? `Deadline ${formatDeadline(data.deadline)}.` : null}</Text>
        </>
      ) : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { borderColor: colors.warning, borderWidth: 1 },
  info: { borderColor: colors.border },
  note: { ...typography.caption },
  error: { ...typography.caption, color: colors.danger },
});
