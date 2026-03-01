'use client';

import { useEffect, useRef, useState, useCallback, useMemo } from 'react';

// ==================== Types ====================

export interface ScraperEvent {
    type: 'status_update' | 'progress' | 'log' | 'error' | 'completed' | 'started' | 'stopped' | 'pong';
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
    /** Reconnect interval in ms (default: 3000) */
    reconnectInterval?: number;
    /** Max reconnect attempts (default: 10) */
    maxReconnectAttempts?: number;
    /** Event callback */
    onEvent?: (event: ScraperEvent) => void;
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

        // Close existing connection
        if (wsRef.current) {
            wsRef.current.close();
        }

        setConnectionStatus('connecting');

        try {
            const ws = new WebSocket(wsUrl);
            wsRef.current = ws;

            ws.onopen = () => {
                setConnectionStatus('connected');
                setReconnectCount(0);
            };

            ws.onmessage = (e) => {
                try {
                    const event: ScraperEvent = JSON.parse(e.data);
                    setLastEvent(event);
                    setEvents((prev) => {
                        const next = [event, ...prev];
                        return next.slice(0, 100); // Son 100 event
                    });
                    onEventRef.current?.(event);
                } catch {
                    // Invalid JSON — ignore
                }
            };

            ws.onclose = () => {
                setConnectionStatus('disconnected');
                wsRef.current = null;

                // Auto-reconnect
                if (autoReconnect && reconnectCount < maxReconnectAttempts) {
                    setConnectionStatus('reconnecting');
                    reconnectTimerRef.current = setTimeout(() => {
                        setReconnectCount((c) => c + 1);
                        connect();
                    }, reconnectInterval);
                }
            };

            ws.onerror = () => {
                // onclose will fire after this
            };
        } catch {
            setConnectionStatus('disconnected');
        }
    }, [wsUrl, autoReconnect, reconnectInterval, maxReconnectAttempts, reconnectCount]);

    // Connect on mount
    useEffect(() => {
        connect();

        return () => {
            if (reconnectTimerRef.current) {
                clearTimeout(reconnectTimerRef.current);
            }
            if (wsRef.current) {
                wsRef.current.close();
            }
        };
    }, [connect]);

    const disconnect = useCallback(() => {
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
        }
        if (wsRef.current) {
            wsRef.current.close();
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
