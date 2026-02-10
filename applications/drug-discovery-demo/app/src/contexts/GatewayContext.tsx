/**
 * Gateway Context
 *
 * Manages the connection to the NIM gateway, including:
 * - Gateway URL configuration
 * - Endpoint health status
 * - Health check functionality
 *
 * This context eliminates gatewayUrl prop drilling throughout the app.
 */

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  type ReactNode,
} from 'react';
import { NIM_ENDPOINTS, type NimEndpoint } from '../data/endpoints';
import { checkAllEndpointsHealth } from '../services/nimApi';

export interface GatewayContextValue {
  // Connection settings
  gatewayUrl: string;
  setGatewayUrl: (url: string) => void;

  // Endpoint status
  endpoints: NimEndpoint[];
  isCheckingHealth: boolean;

  // Connection state (derived)
  isConnected: boolean;

  // Actions
  runHealthCheck: () => Promise<void>;
}

const GatewayContext = createContext<GatewayContextValue | null>(null);

export interface GatewayProviderProps {
  children: ReactNode;
  initialGatewayUrl?: string;
}

export function GatewayProvider({
  children,
  initialGatewayUrl = '',
}: GatewayProviderProps) {
  const [gatewayUrl, setGatewayUrlState] = useState(initialGatewayUrl);
  const [endpoints, setEndpoints] = useState<NimEndpoint[]>(NIM_ENDPOINTS);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  // Ref for debounce timer
  const healthCheckTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derived: connection state
  const requiredEndpoints = endpoints.filter((e) => e.required);
  const isConnected = requiredEndpoints.some((e) => e.status === 'ready');

  // Health check function
  const runHealthCheck = useCallback(async () => {
    if (!gatewayUrl.trim()) return;

    setIsCheckingHealth(true);
    setEndpoints((prev) =>
      prev.map((e) => ({ ...e, status: 'checking' as const }))
    );

    const results = await checkAllEndpointsHealth(gatewayUrl, NIM_ENDPOINTS);

    setEndpoints((prev) =>
      prev.map((endpoint) => {
        const result = results.find((r) => r.id === endpoint.id);
        return result ? { ...endpoint, status: result.status } : endpoint;
      })
    );
    setIsCheckingHealth(false);
  }, [gatewayUrl]);

  // Handle gateway URL changes
  const setGatewayUrl = useCallback((url: string) => {
    setGatewayUrlState(url);
  }, []);

  // Run health check when gateway URL changes (debounced)
  useEffect(() => {
    if (healthCheckTimerRef.current) {
      clearTimeout(healthCheckTimerRef.current);
    }

    if (!gatewayUrl.trim()) {
      setEndpoints((prev) =>
        prev.map((e) => ({ ...e, status: 'unknown' as const }))
      );
      return;
    }

    healthCheckTimerRef.current = setTimeout(runHealthCheck, 800);

    return () => {
      if (healthCheckTimerRef.current) {
        clearTimeout(healthCheckTimerRef.current);
      }
    };
  }, [gatewayUrl, runHealthCheck]);

  const value: GatewayContextValue = useMemo(() => ({
    gatewayUrl,
    setGatewayUrl,
    endpoints,
    isCheckingHealth,
    isConnected,
    runHealthCheck,
  }), [gatewayUrl, setGatewayUrl, endpoints, isCheckingHealth, isConnected, runHealthCheck]);

  return (
    <GatewayContext.Provider value={value}>
      {children}
    </GatewayContext.Provider>
  );
}

/**
 * Hook to access the gateway context
 *
 * @throws Error if used outside of GatewayProvider
 */
export function useGateway(): GatewayContextValue {
  const context = useContext(GatewayContext);
  if (!context) {
    throw new Error('useGateway must be used within a GatewayProvider');
  }
  return context;
}

/**
 * Hook to get just the gateway URL (convenience hook)
 */
export function useGatewayUrl(): string {
  const { gatewayUrl } = useGateway();
  return gatewayUrl;
}

/**
 * Hook to check if connected (convenience hook)
 */
export function useIsConnected(): boolean {
  const { isConnected } = useGateway();
  return isConnected;
}
