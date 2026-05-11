"use client";

import { useEffect, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { ScannerWebSocket } from "@/lib/websocket";
import type { ScanJobOut, ScanProgressMessage } from "@/types/api";

interface ScannerProgressProps {
  job: ScanJobOut;
  onProgress: (msg: ScanProgressMessage) => void;
  onComplete: () => void;
}

export function ScannerProgress({ job, onProgress, onComplete }: ScannerProgressProps) {
  const wsRef = useRef<ScannerWebSocket | null>(null);

  useEffect(() => {
    if (job.status !== "running" && job.status !== "pending") return;

    const ws = new ScannerWebSocket(job.id, (msg) => {
      onProgress(msg);
      if (msg.type === "complete") {
        onComplete();
        ws.disconnect();
      }
    });

    wsRef.current = ws;
    ws.connect();

    return () => {
      ws.disconnect();
    };
  }, [job.id, job.status, onProgress, onComplete]);

  const pct =
    job.total && job.total > 0
      ? Math.round((job.processed / job.total) * 100)
      : 0;

  return (
    <Card className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Spinner size="sm" />
          <span className="text-sm font-medium text-[#e2e8f0]">스캔 진행 중...</span>
        </div>
        <span className="text-sm text-[#718096]">
          {job.processed} / {job.total ?? "?"}
        </span>
      </div>

      <div className="w-full bg-[#2d3748] rounded-full h-2.5">
        <div
          className="bg-blue-500 h-2.5 rounded-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>

      <div className="flex justify-between text-xs text-[#718096]">
        <span>작업 ID: {job.id.slice(0, 8)}...</span>
        <span>{pct}%</span>
      </div>
    </Card>
  );
}
