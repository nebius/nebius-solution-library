/**
 * App Provider
 *
 * Combines all application contexts into a single provider component.
 * This simplifies the main.tsx setup and ensures proper context nesting.
 *
 * Context hierarchy (outer to inner):
 * 1. GatewayProvider - Connection settings (no dependencies)
 * 2. WorkflowDataProvider - Workflow data storage (no dependencies)
 * 3. WorkflowProvider - Navigation (depends on WorkflowData for reset)
 * 4. FineTuningProvider - Fine-tuning state (independent)
 */

import { useCallback, type ReactNode } from 'react';
import { GatewayProvider } from './GatewayContext';
import { WorkflowProvider, type WorkflowMode } from './WorkflowContext';
import { WorkflowDataProvider, useWorkflowData } from './WorkflowDataContext';
import { FineTuningProvider } from './FineTuningContext';

export interface AppProviderProps {
  children: ReactNode;
  initialGatewayUrl?: string;
  initialWorkflowMode?: WorkflowMode;
}

/**
 * Inner provider that connects WorkflowProvider to WorkflowDataProvider
 * This allows the workflow to reset data when drug changes
 */
function WorkflowWithDataReset({
  children,
  initialWorkflowMode,
}: {
  children: ReactNode;
  initialWorkflowMode: WorkflowMode;
}) {
  const { resetAllData } = useWorkflowData();

  const handleDrugChange = useCallback(
    (drugId: string | null, previousDrugId: string | null) => {
      // Reset all workflow data when drug changes
      if (drugId !== previousDrugId) {
        resetAllData();
      }
    },
    [resetAllData]
  );

  return (
    <WorkflowProvider
      initialMode={initialWorkflowMode}
      onDrugChange={handleDrugChange}
    >
      {children}
    </WorkflowProvider>
  );
}

/**
 * Main application provider that combines all contexts
 */
export function AppProvider({
  children,
  initialGatewayUrl = '',
  initialWorkflowMode = 'steps',
}: AppProviderProps) {
  return (
    <GatewayProvider
      initialGatewayUrl={initialGatewayUrl}
    >
      <WorkflowDataProvider>
        <WorkflowWithDataReset initialWorkflowMode={initialWorkflowMode}>
          <FineTuningProvider>
            {children}
          </FineTuningProvider>
        </WorkflowWithDataReset>
      </WorkflowDataProvider>
    </GatewayProvider>
  );
}
