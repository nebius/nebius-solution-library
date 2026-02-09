/**
 * Gateway Context
 *
 * Manages the connection to the NIM gateway, including:
 * - Gateway URL configuration
 * - Demo mode toggle
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
  useRef,
  type ReactNode,
} from 'react';
import { NIM_ENDPOINTS, type NimEndpoint } from '../data/endpoints';
import { checkAllEndpointsHealth } from '../services/nimApi';
import { setDemoMode } from '../services/demoService';

export interface GatewayContextValue {
  // Connection settings
  gatewayUrl: string;
  setGatewayUrl: (url: string) => void;

  // Demo mode
  demoModeEnabled: boolean;
  setDemoModeEnabled: (enabled: boolean) => void;

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
  initialDemoMode?: boolean;
}

export function GatewayProvider({
  children,
  initialGatewayUrl = '',
  initialDemoMode = false,
}: GatewayProviderProps) {
  const [gatewayUrl, setGatewayUrlState] = useState(initialGatewayUrl);
  const [demoModeEnabled, setDemoModeEnabledState] = useState(initialDemoMode);
  const [endpoints, setEndpoints] = useState<NimEndpoint[]>(NIM_ENDPOINTS);
  const [isCheckingHealth, setIsCheckingHealth] = useState(false);

  // Ref for debounce timer
  const healthCheckTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Derived: connection state
  const requiredEndpoints = endpoints.filter((e) => e.required);
  const isConnected = requiredEndpoints.some((e) => e.status === 'ready') || demoModeEnabled;

  // Health check function
  const runHealthCheck = useCallback(async () => {
    if (!gatewayUrl.trim() || demoModeEnabled) return;

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
  }, [gatewayUrl, demoModeEnabled]);

  // Handle gateway URL changes with debounced health check
  const setGatewayUrl = useCallback((url: string) => {
    setGatewayUrlState(url);
  }, []);

  // Handle demo mode changes
  const setDemoModeEnabled = useCallback((enabled: boolean) => {
    setDemoModeEnabledState(enabled);
    setDemoMode(enabled);

    if (enabled) {
      // In demo mode, mark all endpoints as ready
      setEndpoints((prev) =>
        prev.map((e) => ({ ...e, status: 'ready' as const }))
      );
    } else {
      // Reset endpoints to unknown
      setEndpoints((prev) =>
        prev.map((e) => ({ ...e, status: 'unknown' as const }))
      );
    }
  }, []);

  // Run health check when gateway URL changes (debounced)
  useEffect(() => {
    // Skip in demo mode
    if (demoModeEnabled) return;

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
  }, [gatewayUrl, runHealthCheck, demoModeEnabled]);

  const value: GatewayContextValue = {
    gatewayUrl,
    setGatewayUrl,
    demoModeEnabled,
    setDemoModeEnabled,
    endpoints,
    isCheckingHealth,
    isConnected,
    runHealthCheck,
  };

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
