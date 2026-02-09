/**
 * FineTuningMode Component
 *
 * Main container for the Nebius Serverless Fine-Tuning workflow.
 * Renders the appropriate step based on current navigation state.
 */

import { useFineTuning } from '../../contexts/FineTuningContext';
import { FineTuningSidebar } from './FineTuningSidebar';
import { DataSelectionStep } from './steps/DataSelectionStep';
import { DataPreviewStep } from './steps/DataPreviewStep';
import { ModelConfigStep } from './steps/ModelConfigStep';
import { TrainingStep } from './steps/TrainingStep';
import { EvaluationStep } from './steps/EvaluationStep';
import { ScreeningStep } from './steps/ScreeningStep';

interface FineTuningModeProps {
  gatewayUrl: string;
  onGatewayUrlChange: (url: string) => void;
  onBack: () => void;
}

export function FineTuningMode({
  gatewayUrl,
  onGatewayUrlChange,
  onBack,
}: FineTuningModeProps) {
  const { currentStepId, steps } = useFineTuning();

  const renderStepContent = () => {
    switch (currentStepId) {
      case 'data-selection':
        return <DataSelectionStep />;
      case 'data-preview':
        return <DataPreviewStep />;
      case 'model-config':
        return <ModelConfigStep />;
      case 'training':
        return <TrainingStep gatewayUrl={gatewayUrl} />;
      case 'evaluation':
        return <EvaluationStep />;
      case 'screening':
        return <ScreeningStep gatewayUrl={gatewayUrl} />;
      default:
        return <DataSelectionStep />;
    }
  };

  return (
    <>
      <FineTuningSidebar
        steps={steps}
        gatewayUrl={gatewayUrl}
        onGatewayUrlChange={onGatewayUrlChange}
        onBack={onBack}
      />
      <div className="content">{renderStepContent()}</div>
    </>
  );
}
