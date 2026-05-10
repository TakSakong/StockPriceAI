"use client";

import Link from "next/link";
import { Badge, signalToBadgeVariant } from "@/components/ui/badge";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import type { ScanResultOut } from "@/types/api";

interface ScanResultsProps {
  results: ScanResultOut[];
}

export function ScanResults({ results }: ScanResultsProps) {
  const sorted = [...results].sort(
    (a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0),
  );

  return (
    <Card className="overflow-x-auto p-0">
      <CardHeader className="p-4 pb-0">
        <CardTitle>스캔 결과 ({results.length}종목)</CardTitle>
      </CardHeader>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[#2d3748]">
            <th className="px-4 py-3 text-left text-[#718096]">티커</th>
            <th className="px-4 py-3 text-left text-[#718096]">섹터</th>
            <th className="px-4 py-3 text-right text-[#718096]">신호</th>
            <th className="px-4 py-3 text-right text-[#718096]">상승 확률</th>
            <th className="px-4 py-3 text-right text-[#718096]">목표 상승률</th>
            <th className="px-4 py-3 text-right text-[#718096]">종합 점수</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => (
            <tr
              key={r.id}
              className="border-b border-[#2d3748]/50 hover:bg-[#2d3748]/30 transition-colors"
            >
              <td className="px-4 py-3 font-mono font-medium">
                <Link
                  href={`/?ticker=${r.ticker}`}
                  className="text-blue-400 hover:underline"
                >
                  {r.ticker}
                </Link>
              </td>
              <td className="px-4 py-3 text-[#718096]">{r.sector ?? "—"}</td>
              <td className="px-4 py-3 text-right">
                {r.signal ? (
                  <Badge variant={signalToBadgeVariant(r.signal)}>{r.signal}</Badge>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-4 py-3 text-right text-[#e2e8f0]">
                {r.up_prob !== undefined && r.up_prob !== null
                  ? `${(r.up_prob * 100).toFixed(1)}%`
                  : "—"}
              </td>
              <td className="px-4 py-3 text-right">
                {r.est_upside !== undefined && r.est_upside !== null ? (
                  <span
                    className={r.est_upside >= 0 ? "text-emerald-400" : "text-red-400"}
                  >
                    {r.est_upside >= 0 ? "+" : ""}
                    {r.est_upside.toFixed(1)}%
                  </span>
                ) : (
                  "—"
                )}
              </td>
              <td className="px-4 py-3 text-right font-mono text-[#e2e8f0]">
                {r.composite_score !== undefined && r.composite_score !== null
                  ? r.composite_score.toFixed(3)
                  : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}
