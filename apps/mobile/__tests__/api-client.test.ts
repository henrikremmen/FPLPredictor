import { ApiClient, ApiError } from "@fplmodell/api-client";

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

describe("ApiClient", () => {
  it("resolves with the parsed payload on success", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(200, { status: "ok", uptime_seconds: 1, active_sessions: 0 }));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });

    await expect(client.health()).resolves.toEqual({ status: "ok", uptime_seconds: 1, active_sessions: 0 });
    expect(fetchImpl).toHaveBeenCalledWith("http://example.test/api/health", expect.any(Object));
  });

  it("maps a non-ok response to an ApiError with kind 'http' and the backend's detail", async () => {
    const fetchImpl = jest.fn().mockResolvedValue(jsonResponse(404, { detail: "Lagøkten finnes ikke." }));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });

    await expect(client.getTeam("missing")).rejects.toMatchObject({
      kind: "http",
      status: 404,
      message: "Lagøkten finnes ikke.",
    });
  });

  it("maps a rejected fetch (device offline / backend unreachable) to kind 'network'", async () => {
    const fetchImpl = jest.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    const client = new ApiClient({ baseUrl: "http://example.test", fetchImpl });

    await expect(client.health()).rejects.toBeInstanceOf(ApiError);
    await expect(client.health()).rejects.toMatchObject({ kind: "network" });
  });

  it("maps an aborted request to kind 'timeout' once the per-call timeout elapses", async () => {
    const fetchImpl = jest.fn().mockImplementation(
      (_url: string, options: RequestInit) =>
        new Promise((_resolve, reject) => {
          options.signal?.addEventListener("abort", () => {
            const error = new Error("Aborted");
            error.name = "AbortError";
            reject(error);
          });
        }),
    );
    const client = new ApiClient({ baseUrl: "http://example.test", timeoutMs: 20, fetchImpl });

    await expect(client.health()).rejects.toMatchObject({ kind: "timeout" });
  });
});
