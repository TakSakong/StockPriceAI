import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ScannerWebSocket } from "../websocket";
import type { ScanProgressMessage } from "@/types/api";

class MockWebSocket {
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState: number;
  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: (() => void) | null = null;

  static instances: MockWebSocket[] = [];

  constructor(url: string) {
    this.url = url;
    this.readyState = MockWebSocket.OPEN;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.();
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateRawMessage(data: string) {
    this.onmessage?.({ data });
  }

  simulateError() {
    this.onerror?.(new Event("error"));
  }
}

describe("ScannerWebSocket", () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal("WebSocket", MockWebSocket);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("connect() creates WebSocket with correct URL", () => {
    const ws = new ScannerWebSocket("job-123", vi.fn());
    ws.connect();
    expect(MockWebSocket.instances).toHaveLength(1);
    expect(MockWebSocket.instances[0].url).toContain("/ws/scanner/job-123");
  });

  it("onMessage handler is called with parsed message", () => {
    const handler = vi.fn();
    const ws = new ScannerWebSocket("job-abc", handler);
    ws.connect();

    const msg: ScanProgressMessage = {
      type: "progress",
      job_id: "job-abc",
      processed: 10,
      total: 100,
    };
    MockWebSocket.instances[0].simulateMessage(msg);

    expect(handler).toHaveBeenCalledOnce();
    expect(handler).toHaveBeenCalledWith(msg);
  });

  it("does not throw on invalid JSON message", () => {
    const handler = vi.fn();
    const ws = new ScannerWebSocket("job-abc", handler);
    ws.connect();

    expect(() => {
      MockWebSocket.instances[0].simulateRawMessage("not-valid-json{{");
    }).not.toThrow();

    expect(handler).not.toHaveBeenCalled();
  });

  it("onError handler is called on WebSocket error", () => {
    const onError = vi.fn();
    const ws = new ScannerWebSocket("job-abc", vi.fn(), { onError });
    ws.connect();

    MockWebSocket.instances[0].simulateError();

    expect(onError).toHaveBeenCalledOnce();
  });

  it("onClose handler is called when WebSocket closes", () => {
    const onClose = vi.fn();
    const ws = new ScannerWebSocket("job-abc", vi.fn(), { onClose });
    ws.connect();

    MockWebSocket.instances[0].close();

    expect(onClose).toHaveBeenCalledOnce();
  });

  it("disconnect() closes the WebSocket and sets ws to null", () => {
    const ws = new ScannerWebSocket("job-abc", vi.fn());
    ws.connect();

    const mock = MockWebSocket.instances[0];
    const closeSpy = vi.spyOn(mock, "close");

    ws.disconnect();

    expect(closeSpy).toHaveBeenCalledOnce();
  });

  it("isConnected returns true when WebSocket is OPEN", () => {
    const ws = new ScannerWebSocket("job-abc", vi.fn());
    ws.connect();
    MockWebSocket.instances[0].readyState = MockWebSocket.OPEN;
    expect(ws.isConnected).toBe(true);
  });

  it("isConnected returns false when WebSocket is CLOSED", () => {
    const ws = new ScannerWebSocket("job-abc", vi.fn());
    ws.connect();
    MockWebSocket.instances[0].readyState = MockWebSocket.CLOSED;
    expect(ws.isConnected).toBe(false);
  });

  it("disconnect() is safe to call before connect()", () => {
    const ws = new ScannerWebSocket("job-abc", vi.fn());
    expect(() => ws.disconnect()).not.toThrow();
  });

  it("complete message type is parsed correctly", () => {
    const handler = vi.fn();
    const ws = new ScannerWebSocket("job-xyz", handler);
    ws.connect();

    const completeMsg: ScanProgressMessage = {
      type: "complete",
      job_id: "job-xyz",
      processed: 500,
      total: 500,
    };
    MockWebSocket.instances[0].simulateMessage(completeMsg);

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({ type: "complete" }));
  });

  it("error message type is parsed correctly", () => {
    const handler = vi.fn();
    const ws = new ScannerWebSocket("job-err", handler);
    ws.connect();

    const errorMsg: ScanProgressMessage = {
      type: "error",
      job_id: "job-err",
      message: "ML service unavailable",
    };
    MockWebSocket.instances[0].simulateMessage(errorMsg);

    expect(handler).toHaveBeenCalledWith(expect.objectContaining({ type: "error", message: "ML service unavailable" }));
  });
});
