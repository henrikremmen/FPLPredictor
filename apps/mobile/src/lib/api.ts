import { ApiClient } from "@fplmodell/api-client";
import { apiBaseUrl } from "./env";

export const api = new ApiClient({ baseUrl: apiBaseUrl() });
