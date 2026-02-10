/**
 * FineTuningMode Component
 *
 * Main container for the Nebius Jobs Fine-Tuning workflow.
 * Renders the appropriate step based on current navigation state.
 */

import { useFineTuning } from '../../contexts/FineTuningContext';
import { useGateway } from '../../contexts/GatewayContext';
import { FineTuningSidebar } from './FineTuningSidebar';
import { ModelSelectionStep } from './steps/ModelSelectionStep';
import { DataSelectionStep } from './steps/DataSelectionStep';
import { DataPreviewStep } from './steps/DataPreviewStep';
import { ModelConfigStep } from './steps/ModelConfigStep';
import { TrainingStep } from './steps/TrainingStep';
import { EvaluationStep } from './steps/EvaluationStep';
import { ScreeningStep } from './steps/ScreeningStep';

export function FineTuningMode() {
  const { currentStepId, steps } = useFineTuning();
  const { gatewayUrl } = useGateway();

  const renderStepContent = () => {
    switch (currentStepId) {
      case 'model-selection':
        return <ModelSelectionStep />;
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
        return <ModelSelectionStep />;
    }
  };

  return (
    <>
      <FineTuningSidebar steps={steps} />
      <div className="content">{renderStepContent()}</div>
    </>
  );
}
