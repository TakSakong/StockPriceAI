"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import type { TechnicalResponse } from "@/types/api";
import { FullPageSpinner } from "@/components/ui/spinner";

const Plot = dynamic(() => import("react-plotly.js"), {
  ssr: false,
  loading: () => <FullPageSpinner />,
});

interface TechnicalChartProps {
  data: TechnicalResponse;
}

export function TechnicalIndicatorsChart({ data }: TechnicalChartProps) {
  const ind = data.latest_indicators;

  const gaugeTraces = useMemo(() => {
    const rsi = ind.rsi14 ?? 50;
    return [
      {
        type: "indicator" as const,
        mode: "gauge+number" as const,
        value: rsi,
        title: { text: "RSI (14)", font: { color: "#a0aec0", size: 14 } },
        gauge: {
          axis: { range: [0, 100], tickcolor: "#718096", tickfont: { color: "#718096" } },
          bar: { color: rsi > 70 ? "#ef4444" : rsi < 30 ? "#10b981" : "#3b82f6" },
          bgcolor: "#2d3748",
          bordercolor: "#4a5568",
          steps: [
            { range: [0, 30], color: "#064e3b" },
            { range: [70, 100], color: "#7f1d1d" },
          ],
          threshold: {
            line: { color: "#ffffff", width: 2 },
            thickness: 0.75,
            value: rsi,
          },
        },
        domain: { x: [0, 0.5], y: [0, 1] },
        number: { font: { color: "#e2e8f0" } },
      },
      {
        type: "indicator" as const,
        mode: "gauge+number" as const,
        value: ((ind.stoch_k ?? 50)),
        title: { text: "Stoch %K", font: { color: "#a0aec0", size: 14 } },
        gauge: {
          axis: { range: [0, 100], tickcolor: "#718096", tickfont: { color: "#718096" } },
          bar: {
            color:
              (ind.stoch_k ?? 50) > 80
                ? "#ef4444"
                : (ind.stoch_k ?? 50) < 20
                  ? "#10b981"
                  : "#3b82f6",
          },
          bgcolor: "#2d3748",
          bordercolor: "#4a5568",
          steps: [
            { range: [0, 20], color: "#064e3b" },
            { range: [80, 100], color: "#7f1d1d" },
          ],
        },
        domain: { x: [0.5, 1], y: [0, 1] },
        number: { font: { color: "#e2e8f0" } },
      },
    ];
  }, [ind]);

  const layout = useMemo(
    () => ({
      paper_bgcolor: "#1a1f2e",
      plot_bgcolor: "#1a1f2e",
      font: { color: "#a0aec0" },
      margin: { t: 60, r: 20, b: 20, l: 20 },
      height: 250,
    }),
    [],
  );

  return (
    <Plot
      data={gaugeTraces}
      layout={layout}
      config={{ responsive: true, displayModeBar: false }}
      style={{ width: "100%" }}
    />
  );
}
