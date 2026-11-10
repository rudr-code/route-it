import { useEffect, useRef, useCallback } from 'react';
import type { WsMessage } from './types';

type WsHandler = (msg: WsMessage) => void;

export function getWsBaseUrl(): string {
  if (import.meta.env.VITE_WS_BASE_URL) {
    return import.meta.env.VITE_WS_BASE_URL.replace(/\/$/, '');
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  const host = window.location.hostname === 'localhost' ? 'localhost:8000' : window.location.host;
  return `${proto}://${host}`;
}

export function useWebSocket(problemId: string | null, onMessage: WsHandler) {
  const wsRef = useRef<WebSocket | null>(null);
  const handlerRef = useRef<WsHandler>(onMessage);
  handlerRef.current = onMessage;

  const connect = useCallback(() => {
    if (!problemId) return;
    const url = `${getWsBaseUrl()}/ws/problems/${problemId}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as WsMessage;
        handlerRef.current(msg);
      } catch {}
    };

    ws.onerror = () => console.warn('[WS] connection error');
    ws.onclose = () => {
      wsRef.current = null;
    };
  }, [problemId]);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [connect]);
}
