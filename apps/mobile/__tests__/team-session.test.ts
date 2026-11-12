import { ApiError } from "@fplmodell/api-client";
import { loadTeam } from "../src/lib/team-session";

const saved = { fplId: "5139814", horizon: 3, riskProfile: "balanced" as const };
const team = { session_id: "new" } as never;

describe("loadTeam", () => {
  it("imports the team again when the server lost the session", async () => {
    const client = {
      getTeam: jest.fn().mockRejectedValue(new ApiError("http", "The team session does not exist.", 404)),
      importTeam: jest.fn().mockResolvedValue(team),
    };
    await expect(loadTeam(client, "old", saved)).resolves.toEqual({ team, replaced: true });
    expect(client.importTeam).toHaveBeenCalledWith("5139814", 3, "balanced");
  });

  it("passes other failures through and never imports without a saved team ID", async () => {
    const down = new ApiError("network", "Could not contact the API.");
    const client = { getTeam: jest.fn().mockRejectedValue(down), importTeam: jest.fn() };
    await expect(loadTeam(client, "old", saved)).rejects.toBe(down);
    client.getTeam.mockRejectedValue(new ApiError("http", "gone", 404));
    await expect(loadTeam(client, "old", { ...saved, fplId: null })).rejects.toThrow("gone");
    expect(client.importTeam).not.toHaveBeenCalled();
  });
});
