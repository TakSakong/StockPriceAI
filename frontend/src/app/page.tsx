"use client";

import { useState, useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { StockSearch } from "@/components/stock/StockSearch";
import { StockOverview } from "@/components/stock/StockOverview";
import { AnalysisTabs } from "@/components/stock/AnalysisTabs";
import { AuthModal } from "@/components/layout/AuthModal";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FullPageSpinner } from "@/components/ui/spinner";
import { stocksApi, predictionsApi } from "@/lib/api";
import { useUIStore } from "@/store/ui";
import { useAuthStore } from "@/store/auth";

function DashboardContent() {
  const { selectedTicker, setSelectedTicker } = useUIStore();
  const { isAuthenticated } = useAuthStore();
  const [showAuthModal, setShowAuthModal] = useState(false);

  const searchParams = useSearchParams();
  const tickerParam = searchParams.get("ticker");

  useEffect(() => {
    if (tickerParam) {
      setSelectedTicker(tickerParam.toUpperCase());
    }
  }, [tickerParam, setSelectedTicker]);

  const { data: stockInfo, isLoading: stockLoading, error: stockError } = useQuery({
    queryKey: ["stock", selectedTicker],
    queryFn: () => stocksApi.get(selectedTicker),
    enabled: !!selectedTicker,
  });

  const { data: predictions } = useQuery({
    queryKey: ["predictions-history", selectedTicker],
    queryFn: () => predictionsApi.get(selectedTicker),
    enabled: !!selectedTicker && isAuthenticated,
  });

  const prediction = predictions && predictions.length > 0 ? predictions[0] : undefined;

  function handleSearch(ticker: string) {
    setSelectedTicker(ticker);
  }

  return (
    <div className="space-y-6">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[#e2e8f0]">주식 분석 대시보드</h1>
          <p className="mt-1 text-sm text-[#718096]">
            AI 기반 예측 · 기술적 지표 · 감성 분석
          </p>
        </div>
        {!isAuthenticated && (
          <Button variant="secondary" size="sm" onClick={() => setShowAuthModal(true)}>
            로그인
          </Button>
        )}
      </div>

      {/* 검색 */}
      <Card>
        <StockSearch onSearch={handleSearch} loading={stockLoading} />
      </Card>

      {/* 에러 상태 */}
      {stockError && (
        <div className="rounded-md border border-red-800 bg-red-900/20 px-4 py-3 text-sm text-red-400">
          종목을 찾을 수 없습니다: {selectedTicker}
        </div>
      )}

      {/* 분석 결과 */}
      {selectedTicker && !stockError && (
        <>
          {/* 종목 헤더 */}
          <div className="flex items-baseline gap-3">
            <h2 className="text-xl font-bold text-[#e2e8f0]">{selectedTicker}</h2>
            {stockInfo?.name && (
              <span className="text-[#718096]">{stockInfo.name}</span>
            )}
          </div>

          {/* 개요 카드 */}
          {stockInfo && (
            <StockOverview stockInfo={stockInfo} prediction={prediction} />
          )}

          {/* 분석 탭 (7탭) */}
          <Card className="p-0 overflow-hidden">
            <div className="p-4">
              <AnalysisTabs ticker={selectedTicker} />
            </div>
          </Card>
        </>
      )}

      {/* 빈 상태 */}
      {!selectedTicker && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <div className="text-5xl mb-4">📈</div>
          <h3 className="text-lg font-medium text-[#a0aec0]">
            종목 티커를 입력하여 분석을 시작하세요
          </h3>
          <p className="mt-2 text-sm text-[#718096]">
            S&P 500 종목 스캔은{" "}
            <a href="/scanner" className="text-blue-400 hover:underline">
              스캐너 페이지
            </a>
            에서 이용할 수 있습니다.
          </p>
        </div>
      )}

      {/* 인증 모달 */}
      {showAuthModal && <AuthModal onClose={() => setShowAuthModal(false)} />}
    </div>
  );
}

export default function DashboardPage() {
  return (
    <Suspense fallback={<FullPageSpinner />}>
      <DashboardContent />
    </Suspense>
  );
}
