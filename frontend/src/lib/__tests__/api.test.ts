import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  authApi,
  stocksApi,
  watchlistApi,
  predictionsApi,
  scannerApi,
  technicalApi,
  sentimentApi,
  mlPredictApi,
} from "../api";

function mockFetch(body: unknown, status = 200) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 401 ? "Unauthorized" : "OK",
    json: async () => body,
  });
}

function mockFetchError(detail: string, status = 400) {
  return vi.fn().mockResolvedValue({
    ok: false,
    status,
    statusText: "Bad Request",
    json: async () => ({ detail }),
  });
}

describe("request helper", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("throws with server detail on non-ok response", async () => {
    vi.stubGlobal("fetch", mockFetchError("Invalid credentials", 401));
    await expect(
      authApi.login({ email: "x@x.com", password: "bad" }),
    ).rejects.toThrow("Invalid credentials");
  });

  it("falls back to statusText when json parse fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: async () => {
          throw new Error("not json");
        },
      }),
    );
    await expect(authApi.me()).rejects.toThrow("Internal Server Error");
  });

  it("returns undefined for 204 No Content", async () => {
    localStorage.setItem("access_token", "tok");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => undefined }),
    );
    const result = await watchlistApi.remove("AAPL");
    expect(result).toBeUndefined();
  });

  it("attaches Bearer token from localStorage when auth=true", async () => {
    localStorage.setItem("access_token", "my-secret-token");
    const spy = mockFetch({ id: "1", email: "u@u.com" });
    vi.stubGlobal("fetch", spy);
    await authApi.me();
    expect(spy).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer my-secret-token" }),
      }),
    );
  });

  it("does not attach Authorization header when auth=false", async () => {
    localStorage.setItem("access_token", "tok");
    const spy = mockFetch({ access_token: "t", refresh_token: "r", token_type: "bearer" });
    vi.stubGlobal("fetch", spy);
    await authApi.login({ email: "a@a.com", password: "pass" });
    const headers = spy.mock.calls[0][1].headers as Record<string, string>;
    expect(headers["Authorization"]).toBeUndefined();
  });
});

describe("authApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("register - sends POST to /auth/register", async () => {
    const spy = mockFetch({ id: "1", email: "new@new.com" });
    vi.stubGlobal("fetch", spy);
    const result = await authApi.register({ email: "new@new.com", password: "pw" });
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/register"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(result).toEqual({ id: "1", email: "new@new.com" });
  });

  it("login - returns TokenResponse", async () => {
    const token = { access_token: "at", refresh_token: "rt", token_type: "bearer" };
    vi.stubGlobal("fetch", mockFetch(token));
    const result = await authApi.login({ email: "u@u.com", password: "pw" });
    expect(result.access_token).toBe("at");
  });

  it("refresh - sends refresh_token in body", async () => {
    const token = { access_token: "new-at", refresh_token: "new-rt", token_type: "bearer" };
    const spy = mockFetch(token);
    vi.stubGlobal("fetch", spy);
    await authApi.refresh("old-rt");
    const body = JSON.parse(spy.mock.calls[0][1].body as string);
    expect(body.refresh_token).toBe("old-rt");
  });

  it("me - sends GET to /auth/me", async () => {
    const spy = mockFetch({ id: "1", email: "me@me.com" });
    vi.stubGlobal("fetch", spy);
    await authApi.me();
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/auth/me"),
      expect.any(Object),
    );
  });
});

describe("stocksApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("get - uppercases ticker and requests /stocks/:ticker", async () => {
    const spy = mockFetch({ ticker: "AAPL", current_price: 185.0 });
    vi.stubGlobal("fetch", spy);
    await stocksApi.get("aapl");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/stocks/AAPL"),
      expect.any(Object),
    );
  });
});

describe("watchlistApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("list - GET /watchlist", async () => {
    const spy = mockFetch([]);
    vi.stubGlobal("fetch", spy);
    const result = await watchlistApi.list();
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/watchlist"),
      expect.any(Object),
    );
    expect(result).toEqual([]);
  });

  it("add - POST /watchlist with body", async () => {
    const item = { id: "1", ticker: "TSLA", added_at: "2026-01-01" };
    const spy = mockFetch(item);
    vi.stubGlobal("fetch", spy);
    const result = await watchlistApi.add({ ticker: "TSLA" });
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/watchlist"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.ticker).toBe("TSLA");
  });

  it("remove - DELETE /watchlist/:ticker (uppercase)", async () => {
    localStorage.setItem("access_token", "tok");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => undefined }),
    );
    const spy = vi.mocked(fetch);
    await watchlistApi.remove("tsla");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/watchlist/TSLA"),
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});

describe("predictionsApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("get - uppercase ticker and requests /predictions/:ticker", async () => {
    const spy = mockFetch({ id: "p1", ticker: "NVDA", signal: "BUY", up_prob: 0.72, created_at: "2026-01-01" });
    vi.stubGlobal("fetch", spy);
    await predictionsApi.get("nvda");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/predictions/NVDA"),
      expect.any(Object),
    );
  });
});

describe("scannerApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("createJob - POST /scanner/jobs", async () => {
    const job = { id: "job1", status: "pending", processed: 0, created_at: "2026-01-01" };
    const spy = mockFetch(job);
    vi.stubGlobal("fetch", spy);
    const result = await scannerApi.createJob({});
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/scanner/jobs"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.id).toBe("job1");
  });

  it("getJob - GET /scanner/jobs/:id", async () => {
    const spy = mockFetch({ id: "job1", status: "running", processed: 5, created_at: "2026-01-01" });
    vi.stubGlobal("fetch", spy);
    await scannerApi.getJob("job1");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/scanner/jobs/job1"),
      expect.any(Object),
    );
  });

  it("listJobs - GET /scanner/jobs", async () => {
    const spy = mockFetch([]);
    vi.stubGlobal("fetch", spy);
    const result = await scannerApi.listJobs();
    expect(result).toEqual([]);
  });

  it("getResults - GET /scanner/jobs/:id/results", async () => {
    const spy = mockFetch([]);
    vi.stubGlobal("fetch", spy);
    await scannerApi.getResults("job1");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/scanner/jobs/job1/results"),
      expect.any(Object),
    );
  });
});

describe("technicalApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("get - requests ML service with uppercase ticker and period_days", async () => {
    const spy = mockFetch({ ticker: "AAPL", period_days: 365, data_points: 250, signals: {}, support_resistance: {}, latest_indicators: {}, ma_trend: "up", overall_signal: "BUY" });
    vi.stubGlobal("fetch", spy);
    await technicalApi.get("aapl", 365);
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/technical/AAPL?period_days=365"),
      expect.any(Object),
    );
  });
});

describe("sentimentApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("get - requests ML service sentiment endpoint", async () => {
    const spy = mockFetch({ ticker: "MSFT", overall_sentiment: "positive", sentiment_score: 0.8, news_count: 10, positive_count: 7, negative_count: 1, neutral_count: 2 });
    vi.stubGlobal("fetch", spy);
    await sentimentApi.get("msft");
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/sentiment/MSFT"),
      expect.any(Object),
    );
  });
});

describe("mlPredictApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("predict - POST to ML service /predict", async () => {
    const response = { ticker: "AAPL", signal: "BUY", up_prob: 0.75, model_type: "ensemble" };
    const spy = mockFetch(response);
    vi.stubGlobal("fetch", spy);
    const result = await mlPredictApi.predict({ ticker: "AAPL" });
    expect(spy).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/predict"),
      expect.objectContaining({ method: "POST" }),
    );
    expect(result.signal).toBe("BUY");
  });
});
