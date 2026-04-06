'use client';

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';

// ==================== Types ====================

export interface ScraperEvent {
    type: 'status_update' | 'progress' | 'log' | 'error' | 'completed' | 'started' | 'stopped' | 'pong' | 'connected' | 'subscribed';
    scraper_type: string;
    timestamp: string;
    data: Record<string, unknown>;
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'reconnecting';

interface UseScraperEventsOptions {
    /** WebSocket URL (default: ws://localhost:8000/ws/scrapers/events) */
    url?: string;
    /** Auto-reconnect on disconnect (default: true) */
    autoReconnect?: boolean;
    /** Base reconnect interval in ms, doubles with each attempt (default: 3000) */
    reconnectInterval?: number;
    /** Max reconnect attempts (default: 10) */
    maxReconnectAttempts?: number;
    /** Event callback */
    onEvent?: (event: ScraperEvent) => void;
}

const MAX_RECONNECT_INTERVAL = 30000;

function getBackoffDelay(base: number, attempt: number): number {
    return Math.min(base * Math.pow(1.5, attempt), MAX_RECONNECT_INTERVAL);
}

// ==================== Hook ====================

export function useScraperEvents(options: UseScraperEventsOptions = {}) {
    const {
        url,
        autoReconnect = true,
        reconnectInterval = 3000,
        maxReconnectAttempts = 10,
        onEvent,
    } = options;

    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
    const [lastEvent, setLastEvent] = useState<ScraperEvent | null>(null);
    const [events, setEvents] = useState<ScraperEvent[]>([]);
    const [reconnectCount, setReconnectCount] = useState(0);

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
    const onEventRef = useRef(onEvent);
    onEventRef.current = onEvent;
    // Ref-based counter avoids stale closure without recreating connect()
    const reconnectCountRef = useRef(0);
    const intentionalCloseRef = useRef(false);

    // Build WS URL
    const wsUrl = useMemo(() => {
        if (url) return url;
        if (typeof window === 'undefined') return '';
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
        const baseUrl = apiUrl.replace('/api/v1', '').replace('http://', 'ws://').replace('https://', 'wss://');
        return `${baseUrl}/ws/scrapers/events`;
    }, [url]);

    const connect = useCallback(() => {
        if (!wsUrl || typeof window === 'undefined') return;

        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }

        if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
            wsRef.current.onclose = null;
            wsRef.current.close();
        }

        intentionalCloseRef.current = false;
        setConnectionStatus('connecting');

        try {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                setConnectionStatus('connected');
                reconnectCountRef.current = 0;
                setReconnectCount(0);
            };

            ws.onmessage = (e) => {
                try {
                    const event: ScraperEvent = JSON.parse(e.data);
                    setLastEvent(event);
                    setEvents((prev) => [event, ...prev].slice(0, 100));
                    onEventRef.current?.(event);
                } catch {
                    // Invalid JSON — ignore
                }
            };

            ws.onclose = () => {
                setConnectionStatus('disconnected');
                wsRef.current = null;

                if (intentionalCloseRef.current) return;

                const attempt = reconnectCountRef.current;
                if (autoReconnect && attempt < maxReconnectAttempts) {
                    setConnectionStatus('reconnecting');
                    const delay = getBackoffDelay(reconnectInterval, attempt);
                    reconnectTimerRef.current = setTimeout(() => {
                        reconnectCountRef.current += 1;
                        setReconnectCount(reconnectCountRef.current);
                        connect();
                    }, delay);
                }
            };

            ws.onerror = () => {
                // onclose fires after onerror
            };
        } catch {
            setConnectionStatus('disconnected');
        }
    }, [wsUrl, autoReconnect, reconnectInterval, maxReconnectAttempts]);

    // Connect on mount
    useEffect(() => {
        connect();
        return () => {
            intentionalCloseRef.current = true;
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            if (wsRef.current) wsRef.current.close();
        };
    }, [connect]);

    const disconnect = useCallback(() => {
        intentionalCloseRef.current = true;
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }
        setConnectionStatus('disconnected');
    }, []);

    const clearEvents = useCallback(() => {
        setEvents([]);
        setLastEvent(null);
    }, []);

    return {
        connectionStatus,
        lastEvent,
        events,
        reconnectCount,
        connect,
        disconnect,
        clearEvents,
        isConnected: connectionStatus === 'connected',
    };
}
