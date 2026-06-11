'use client';

import React, { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo } from 'react';
import type { ScraperEvent } from '@/lib/types';
import type { ConnectionStatus } from '@/lib/useScraperEvents';

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
    subscribedScrapers: string[];
    subscribe: (scrapers: string[]) => void;
}

const ScraperContext = createContext<ScraperContextType | null>(null);

const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_INTERVAL = 3000;
const MAX_RECONNECT_INTERVAL = 30000;
const PING_INTERVAL = 15000;
const GHOST_TIMEOUT = 45000; // must match server-side (45s)

function getBackoffDelay(attempt: number): number {
    return Math.min(BASE_RECONNECT_INTERVAL * Math.pow(1.5, attempt), MAX_RECONNECT_INTERVAL);
}

export function ScraperProvider({ children, url }: { children: React.ReactNode; url?: string }) {
    const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('disconnected');
    const [lastEvent, setLastEvent] = useState<ScraperEvent | null>(null);
    const [events, setEvents] = useState<ScraperEvent[]>([]);
    const [reconnectCount, setReconnectCount] = useState(0);
    const [subscribedScrapers, setSubscribedScrapers] = useState<string[]>(['ieee', 'sciencedirect', 'acm', 'wiley', 'springer']);

    const wsRef = useRef<WebSocket | null>(null);
    const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
    const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);
    // Ref-based counter avoids stale closure in ws.onclose without recreating connect()
    const reconnectCountRef = useRef(0);
    // Prevent reconnect after intentional disconnect()
    const intentionalCloseRef = useRef(false);

    const wsUrl = useMemo(() => {
        if (url) return url;
        if (typeof window === 'undefined') return '';
        const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
        const baseUrl = apiUrl
            .replace('/api/v1', '')
            .replace('http://', 'ws://')
            .replace('https://', 'wss://');
        return `${baseUrl}/ws/scrapers/events`;
    }, [url]);

    const connect = useCallback(() => {
        if (!wsUrl || typeof window === 'undefined') return;

        // Clear any pending reconnect timer
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }

        // Clear any existing ping interval before creating a new one
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
        }

        // Close existing socket gracefully
        if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
            wsRef.current.onclose = null; // prevent onclose from triggering reconnect
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

                // Heartbeat: keeps the server ghost-connection pruner from closing us
                pingIntervalRef.current = setInterval(() => {
                    if (ws.readyState === WebSocket.OPEN) {
                        ws.send('ping');
                    }
                }, PING_INTERVAL);
            };

            ws.onmessage = (e) => {
                try {
                    const event: ScraperEvent = JSON.parse(e.data);
                    if (event.type === 'pong') return; // heartbeat ack — ignore
                    setLastEvent(event);
                    setEvents((prev) => [event, ...prev].slice(0, 1000));
                } catch {
                    // Invalid JSON — ignore
                }
            };

            ws.onclose = () => {
                setConnectionStatus('disconnected');
                wsRef.current = null;

                if (pingIntervalRef.current) {
                    clearInterval(pingIntervalRef.current);
                    pingIntervalRef.current = null;
                }

                if (intentionalCloseRef.current) return;

                const attempt = reconnectCountRef.current;
                if (attempt < MAX_RECONNECT_ATTEMPTS) {
                    setConnectionStatus('reconnecting');
                    const delay = getBackoffDelay(attempt);
                    reconnectTimerRef.current = setTimeout(() => {
                        reconnectCountRef.current += 1;
                        setReconnectCount(reconnectCountRef.current);
                        connect();
                    }, delay);
                }
            };

            ws.onerror = () => {
                // onclose fires after onerror — reconnect handled there
            };
        } catch {
            setConnectionStatus('disconnected');
        }
        // wsUrl is the only external dep; reconnect logic uses refs to avoid stale closures
    }, [wsUrl]);

    // Connect on mount, cleanup on unmount
    useEffect(() => {
        connect();
        return () => {
            intentionalCloseRef.current = true;
            if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
            if (pingIntervalRef.current) clearInterval(pingIntervalRef.current);
            if (wsRef.current) wsRef.current.close();
        };
    }, [connect]);

    const disconnect = useCallback(() => {
        intentionalCloseRef.current = true;
        if (reconnectTimerRef.current) {
            clearTimeout(reconnectTimerRef.current);
            reconnectTimerRef.current = null;
        }
        if (pingIntervalRef.current) {
            clearInterval(pingIntervalRef.current);
            pingIntervalRef.current = null;
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

    const subscribe = useCallback((scrapers: string[]) => {
        const normalized = scrapers.length === 0 ? ['ieee', 'sciencedirect', 'acm', 'wiley', 'springer'] : scrapers;
        setSubscribedScrapers(normalized);
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'subscribe', scrapers: normalized }));
        }
    }, []);

    const value: ScraperContextType = {
        connectionStatus,
        lastEvent,
        events,
        reconnectCount,
        connect,
        disconnect,
        clearEvents,
        isConnected: connectionStatus === 'connected',
        subscribedScrapers,
        subscribe,
    };

    return (
        <ScraperContext.Provider value={value}>
            {children}
        </ScraperContext.Provider>
    );
}

export function useGlobalScraperEvents(options?: { onEvent?: (event: ScraperEvent) => void }) {
    const context = useContext(ScraperContext);

    if (!context) {
        throw new Error('useGlobalScraperEvents must be used within a ScraperProvider');
    }

    const { onEvent } = options || {};
    const onEventRef = useRef(onEvent);
    onEventRef.current = onEvent;

    useEffect(() => {
        if (onEventRef.current && context.lastEvent) {
            onEventRef.current(context.lastEvent);
        }
    }, [context.lastEvent]);

    return context;
}
