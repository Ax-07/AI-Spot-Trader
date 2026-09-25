"use client";

import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  createSeriesMarkers,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "next-themes";
import { useEffect, useRef } from "react";

import {
  markerCandleTime,
  toCandlestickData,
  toVolumeData,
  type CandleResponse,
  type MarketFillMarker,
} from "@/lib/market-candles";

type CandlestickSeriesApi = ISeriesApi<"Candlestick">;
type HistogramSeriesApi = ISeriesApi<"Histogram">;

export function MarketChart({
  candles,
  markers,
  onMarkerSelect,
}: {
  candles: CandleResponse[];
  markers: MarketFillMarker[];
  onMarkerSelect: (marker: MarketFillMarker) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const candleSeriesRef = useRef<CandlestickSeriesApi | null>(null);
  const volumeSeriesRef = useRef<HistogramSeriesApi | null>(null);
  const markerApiRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const latestCandles = useRef(candles);
  const latestMarkers = useRef(markers);
  const latestMarkerSelect = useRef(onMarkerSelect);
  const { resolvedTheme } = useTheme();

  useEffect(() => {
    latestCandles.current = candles;
    latestMarkers.current = markers;
    latestMarkerSelect.current = onMarkerSelect;
  }, [candles, markers, onMarkerSelect]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const rootStyle = getComputedStyle(document.documentElement);
    const textColor = rootStyle.getPropertyValue("--muted-foreground").trim() || (resolvedTheme === "dark" ? "#a1a1aa" : "#52525b");
    const gridColor = rootStyle.getPropertyValue("--border").trim() || (resolvedTheme === "dark" ? "#27272a" : "#e4e4e7");

    const chart = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor,
      },
      grid: {
        vertLines: { color: gridColor },
        horzLines: { color: gridColor },
      },
      rightPriceScale: { borderColor: gridColor },
      timeScale: { borderColor: gridColor, timeVisible: true, secondsVisible: false },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#16a34a",
      downColor: "#dc2626",
      borderVisible: false,
      wickUpColor: "#16a34a",
      wickDownColor: "#dc2626",
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.82, bottom: 0 },
    });
    const markerApi = createSeriesMarkers(candleSeries, []);

    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;
    markerApiRef.current = markerApi;

    const handleClick: Parameters<typeof chart.subscribeClick>[0] = (param) => {
      const hoveredId = typeof param.hoveredInfo?.objectId === "string" ? param.hoveredInfo.objectId : null;
      const hoveredMarker = hoveredId
        ? latestMarkers.current.find((marker) => marker.id === hoveredId) ?? null
        : null;
      if (hoveredMarker) {
        latestMarkerSelect.current(hoveredMarker);
        return;
      }
      if (typeof param.time !== "number") return;
      const candidate = latestMarkers.current.find(
        (marker) => markerCandleTime(marker, latestCandles.current) === param.time,
      );
      if (candidate) latestMarkerSelect.current(candidate);
    };
    chart.subscribeClick(handleClick);

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      chart.applyOptions({
        width: Math.max(1, Math.floor(entry.contentRect.width)),
        height: Math.max(280, Math.floor(entry.contentRect.height)),
      });
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.unsubscribeClick(handleClick);
      markerApi.detach();
      chart.remove();
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      markerApiRef.current = null;
    };
  }, [resolvedTheme]);

  useEffect(() => {
    const candleSeries = candleSeriesRef.current;
    const volumeSeries = volumeSeriesRef.current;
    const markerApi = markerApiRef.current;
    if (!candleSeries || !volumeSeries || !markerApi) return;

    candleSeries.setData(
      toCandlestickData(candles).map((item) => ({ ...item, time: item.time as UTCTimestamp })),
    );
    volumeSeries.setData(
      toVolumeData(candles).map((item) => ({
        time: item.time as UTCTimestamp,
        value: item.value,
        color: item.direction === "up" ? "rgba(22, 163, 74, 0.35)" : "rgba(220, 38, 38, 0.35)",
      })),
    );

    const chartMarkers = markers.flatMap((marker): SeriesMarker<Time>[] => {
      const time = markerCandleTime(marker, candles);
      if (time === null) return [];
      return [{
        id: marker.id,
        time: time as UTCTimestamp,
        position: marker.action === "BUY" ? "belowBar" : "aboveBar",
        shape: marker.action === "BUY" ? "arrowUp" : "arrowDown",
        color: marker.action === "BUY" ? "#16a34a" : "#dc2626",
        text: marker.action,
      }];
    });
    markerApi.setMarkers(chartMarkers);
  }, [candles, markers]);

  return (
    <div className="space-y-2">
      <div ref={containerRef} className="h-[360px] w-full sm:h-[480px]" aria-label="Chart chandeliers du marché actif" />
      <p className="text-right text-[10px] text-muted-foreground">
        <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer" className="underline underline-offset-2">
          Charts by TradingView
        </a>
      </p>
    </div>
  );
}
