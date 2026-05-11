"use client";

import type { ScanProgressMessage } from "@/types/api";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";

type MessageHandler = (msg: ScanProgressMessage) => void;
type ErrorHandler = (event: Event) => void;
type CloseHandler = () => void;

export class ScannerWebSocket {
  private ws: WebSocket | null = null;
  private onMessage: MessageHandler;
  private onError?: ErrorHandler;
  private onClose?: CloseHandler;
  private jobId: string;

  constructor(
    jobId: string,
    onMessage: MessageHandler,
    options?: { onError?: ErrorHandler; onClose?: CloseHandler },
  ) {
    this.jobId = jobId;
    this.onMessage = onMessage;
    this.onError = options?.onError;
    this.onClose = options?.onClose;
  }

  connect() {
    const url = `${WS_BASE}/ws/scanner/${this.jobId}`;
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log(`WebSocket connected: ${url}`);
    };

    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as ScanProgressMessage;
        this.onMessage(msg);
      } catch {
        console.error("Failed to parse WS message", event.data);
      }
    };

    this.ws.onerror = (event) => {
      this.onError?.(event);
    };

    this.ws.onclose = () => {
      this.onClose?.();
    };
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }

  get isConnected() {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
