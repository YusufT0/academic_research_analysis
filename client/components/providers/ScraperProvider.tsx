'use client';

import React, { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo } from 'react';
import type { ScraperEvent } from '@/lib/types';
import type { ConnectionStatus } from '@/lib/useScraperEvents';

// Orijinal useScraperEvents hook'unun içeriğini taşıyoruz
// Tüm sayfalarda tek bir websocket bağlantısı kullanılması için Context yapıldı

interface ScraperContextType {
    connectionStatus: ConnectionStatus;
    lastEvent: ScraperEvent | null;
    events: ScraperEvent[];
    reconnectCount: number;
    connect: () => void;
    disconnect: () => void;
    clearEvents: () => void;
    isConnected: boolean;
}

const ScraperContext = createContext<ScraperContextType | null>(null);

export function ScraperProvider({ children, url }: { children: React.ReactNode, url?: string }) {
    const autoReconnect = true;
    const reconnectInterval = 3000;
    const maxReconnectAttempts = 10;

    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
    const [lastEvent, setLastEvent] = useState<ScraperEvent | null>(null);
    const [events, setEvents] = useState<ScraperEvent[]>([]);
    const [reconnectCount, setReconnectCount] = useState(0);

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
    const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);

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

                // Heartbeat başlat: Her 15 saniyede bir ping gönder
                pingIntervalRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send('ping');
                    }
                }, 15000);
            };

            ws.onmessage = (e) => {
                try {
                    const event: ScraperEvent = JSON.parse(e.data);

                    // Ignore pong responses silenty
                    if (event.type === 'pong') return;

                    setLastEvent(event);
                    setEvents((prev) => {
                        const next = [event, ...prev];
                        return next.slice(0, 100); // Son 100 event
                    });
                } catch {
                    // Invalid JSON — ignore
                }
            };

            ws.onclose = () => {
                setConnectionStatus('disconnected');
                wsRef.current = null;

                if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);

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
            if (pingIntervalRef.current) {
                clearInterval(pingIntervalRef.current);
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
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
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

    const value = {
        connectionStatus,
        lastEvent,
        events,
        reconnectCount,
        connect,
        disconnect,
        clearEvents,
        isConnected: connectionStatus === 'connected',
    };

    return (
        <ScraperContext.Provider value={value}>
            {children}
        </ScraperContext.Provider>
    );
}

// Global olarak websocket'i dinlemek için yeni hook
export function useGlobalScraperEvents(options?: { onEvent?: (event: ScraperEvent) => void }) {
    const context = useContext(ScraperContext);

    if (!context) {
        throw new Error('useGlobalScraperEvents must be used within a ScraperProvider');
    }

    const { onEvent } = options || {};

    // Sadece componenti render eden yer son event değiştiğinde onEvent'i tetiklesin
    useEffect(() => {
        if (onEvent && context.lastEvent) {
            onEvent(context.lastEvent);
        }
    }, [context.lastEvent]);

    return context;
}
