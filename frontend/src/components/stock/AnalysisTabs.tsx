"use client";

import { useQuery } from "@tanstack/react-query";
import { Tabs, TabPanel } from "@/components/ui/tabs";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, signalToBadgeVariant } from "@/components/ui/badge";
import { FullPageSpinner } from "@/components/ui/spinner";
import { TechnicalIndicatorsChart } from "@/components/charts/TechnicalChart";
import { technicalApi, sentimentApi, predictionsApi } from "@/lib/api";
import { useUIStore } from "@/store/ui";
import { useAuthStore } from "@/store/auth";

const TABS = [
  { id: "overview", label: "개요" },
  { id: "technical", label: "기술적 지표" },
  { id: "sentiment", label: "감성 분석" },
  { id: "prediction", label: "AI 예측" },
  { id: "signals", label: "매매 신호" },
  { id: "support", label: "지지/저항" },
  { id: "indicators", label: "지표 상세" },
];

interface AnalysisTabsProps {
  ticker: string;
}

export function AnalysisTabs({ ticker }: AnalysisTabsProps) {
  const { activeTab, setActiveTab } = useUIStore();
  const { isAuthenticated } = useAuthStore();

  const { data: technical, isLoading: techLoading } = useQuery({
    queryKey: ["technical", ticker],
    queryFn: () => technicalApi.get(ticker),
    enabled: !!ticker,
  });

  const { data: sentiment, isLoading: sentLoading } = useQuery({
    queryKey: ["sentiment", ticker],
    queryFn: () => sentimentApi.get(ticker),
    enabled: !!ticker && activeTab === "sentiment",
  });

  const { data: predictions, isLoading: predLoading } = useQuery({
    queryKey: ["predictions-history", ticker],
    queryFn: () => predictionsApi.get(ticker),
    enabled: !!ticker && activeTab === "prediction" && isAuthenticated,
  });

  const prediction = predictions && predictions.length > 0 ? predictions[0] : undefined;

  return (
    <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab}>
      {/* 개요 탭 */}
      <TabPanel id="overview" activeTab={activeTab}>
        {techLoading ? (
          <FullPageSpinner />
        ) : technical ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <Card>
                <div className="text-xs text-[#718096]">전반적 신호</div>
                <Badge
                  variant={signalToBadgeVariant(technical.overall_signal)}
                  className="mt-2"
                >
                  {technical.overall_signal}
                </Badge>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">MA 추세</div>
                <div className="mt-2 text-sm font-medium capitalize text-[#e2e8f0]">
                  {technical.ma_trend}
                </div>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">분석 기간</div>
                <div className="mt-2 text-sm text-[#e2e8f0]">
                  {technical.period_days}일
                </div>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">데이터 포인트</div>
                <div className="mt-2 text-sm text-[#e2e8f0]">
                  {technical.data_points.toLocaleString()}
                </div>
              </Card>
            </div>
            <TechnicalIndicatorsChart data={technical} />
          </div>
        ) : null}
      </TabPanel>

      {/* 기술적 지표 탭 */}
      <TabPanel id="technical" activeTab={activeTab}>
        {techLoading ? (
          <FullPageSpinner />
        ) : technical ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Object.entries(technical.latest_indicators)
              .filter(([, v]) => v !== null)
              .map(([key, value]) => (
                <Card key={key}>
                  <div className="text-xs text-[#718096] uppercase">{key.replace(/_/g, " ")}</div>
                  <div className="mt-1 text-lg font-semibold text-[#e2e8f0]">
                    {typeof value === "number" ? value.toFixed(4) : "—"}
                  </div>
                </Card>
              ))}
          </div>
        ) : null}
      </TabPanel>

      {/* 감성 분석 탭 */}
      <TabPanel id="sentiment" activeTab={activeTab}>
        {sentLoading ? (
          <FullPageSpinner />
        ) : sentiment ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Card>
                <div className="text-xs text-[#718096]">전반적 감성</div>
                <Badge
                  variant={
                    sentiment.overall_sentiment === "positive"
                      ? "buy"
                      : sentiment.overall_sentiment === "negative"
                        ? "sell"
                        : "hold"
                  }
                  className="mt-2"
                >
                  {sentiment.overall_sentiment}
                </Badge>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">감성 점수</div>
                <div className="mt-2 text-xl font-bold text-[#e2e8f0]">
                  {sentiment.sentiment_score.toFixed(3)}
                </div>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">분석 뉴스 수</div>
                <div className="mt-2 text-xl font-bold text-[#e2e8f0]">
                  {sentiment.news_count}
                </div>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">긍정</div>
                <div className="mt-2 text-xl font-bold text-emerald-400">
                  {sentiment.positive_count}
                </div>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">부정</div>
                <div className="mt-2 text-xl font-bold text-red-400">
                  {sentiment.negative_count}
                </div>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">중립</div>
                <div className="mt-2 text-xl font-bold text-[#a0aec0]">
                  {sentiment.neutral_count}
                </div>
              </Card>
            </div>
          </div>
        ) : (
          <div className="text-[#718096] text-sm">감성 분석 탭을 선택하면 로드됩니다.</div>
        )}
      </TabPanel>

      {/* AI 예측 탭 */}
      <TabPanel id="prediction" activeTab={activeTab}>
        {!isAuthenticated ? (
          <div className="flex flex-col items-center justify-center py-12 text-center border border-dashed border-[#2d3748] rounded-lg p-6 bg-[#1a202c]/30">
            <div className="text-4xl mb-3">🔒</div>
            <h3 className="text-md font-medium text-[#e2e8f0]">AI 예측은 회원 전용 기능입니다</h3>
            <p className="mt-1 text-sm text-[#718096]">로그인하시면 AI 분석과 예측 상승확률을 확인하실 수 있습니다.</p>
          </div>
        ) : predLoading ? (
          <FullPageSpinner />
        ) : prediction ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Card>
                <div className="text-xs text-[#718096]">예측 신호</div>
                <Badge
                  variant={signalToBadgeVariant(prediction.signal)}
                  className="mt-2"
                >
                  {prediction.signal}
                </Badge>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">상승 확률</div>
                <div className="mt-2 text-2xl font-bold text-[#e2e8f0]">
                  {(prediction.up_prob * 100).toFixed(1)}%
                </div>
                <div className="w-full bg-[#2d3748] rounded-full h-2 mt-2">
                  <div
                    className="bg-blue-500 h-2 rounded-full"
                    style={{ width: `${prediction.up_prob * 100}%` }}
                  />
                </div>
              </Card>
              <Card>
                <div className="text-xs text-[#718096]">모델 타입</div>
                <div className="mt-2 text-sm font-medium text-[#e2e8f0] capitalize">
                  {prediction.model_type}
                </div>
              </Card>
              {prediction.xgb_weight !== undefined && (
                <Card>
                  <div className="text-xs text-[#718096]">XGBoost 가중치</div>
                  <div className="mt-2 text-lg font-bold text-[#e2e8f0]">
                    {(prediction.xgb_weight * 100).toFixed(1)}%
                  </div>
                </Card>
              )}
              {prediction.lstm_weight !== undefined && (
                <Card>
                  <div className="text-xs text-[#718096]">LSTM 가중치</div>
                  <div className="mt-2 text-lg font-bold text-[#e2e8f0]">
                    {(prediction.lstm_weight * 100).toFixed(1)}%
                  </div>
                </Card>
              )}
              {prediction.complexity !== undefined && (
                <Card>
                  <div className="text-xs text-[#718096]">복잡도</div>
                  <div className="mt-2 text-lg font-bold text-[#e2e8f0]">
                    {prediction.complexity.toFixed(3)}
                  </div>
                </Card>
              )}
            </div>
          </div>
        ) : (
          <div className="text-[#718096] text-sm">AI 예측 탭을 선택하면 분석이 실행됩니다.</div>
        )}
      </TabPanel>

      {/* 매매 신호 탭 */}
      <TabPanel id="signals" activeTab={activeTab}>
        {techLoading ? (
          <FullPageSpinner />
        ) : technical ? (
          <div className="grid gap-3 sm:grid-cols-2">
            {Object.entries(technical.signals).map(([name, signal]) => (
              <Card key={name} className="flex items-start justify-between">
                <div>
                  <div className="text-sm font-medium text-[#e2e8f0] capitalize">
                    {name.replace(/_/g, " ")}
                  </div>
                  <div className="mt-1 text-xs text-[#718096]">{signal.description}</div>
                </div>
                <Badge variant={signalToBadgeVariant(signal.action)}>
                  {signal.action}
                </Badge>
              </Card>
            ))}
          </div>
        ) : null}
      </TabPanel>

      {/* 지지/저항 탭 */}
      <TabPanel id="support" activeTab={activeTab}>
        {techLoading ? (
          <FullPageSpinner />
        ) : technical ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(technical.support_resistance).map(([key, value]) => (
              <Card key={key}>
                <div className="text-xs text-[#718096] capitalize">
                  {key.replace(/_/g, " ")}
                </div>
                <div className="mt-1 text-lg font-bold text-[#e2e8f0]">
                  ${value.toFixed(2)}
                </div>
              </Card>
            ))}
          </div>
        ) : null}
      </TabPanel>

      {/* 지표 상세 탭 */}
      <TabPanel id="indicators" activeTab={activeTab}>
        {techLoading ? (
          <FullPageSpinner />
        ) : technical ? (
          <Card className="overflow-x-auto">
            <CardHeader>
              <CardTitle>최신 지표 값</CardTitle>
            </CardHeader>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#2d3748]">
                  <th className="py-2 text-left text-[#718096]">지표</th>
                  <th className="py-2 text-right text-[#718096]">값</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(technical.latest_indicators).map(([key, value]) => (
                  <tr key={key} className="border-b border-[#2d3748]/50">
                    <td className="py-2 text-[#a0aec0] uppercase text-xs">{key}</td>
                    <td className="py-2 text-right font-mono text-[#e2e8f0]">
                      {value !== null ? value.toFixed(4) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        ) : null}
      </TabPanel>
    </Tabs>
  );
}
