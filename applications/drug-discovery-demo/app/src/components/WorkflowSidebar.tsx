import type { WorkflowStep, WorkflowStepId } from '../types/workflow';
import { SidebarCommon } from './SidebarCommon';

interface WorkflowSidebarProps {
  steps: WorkflowStep[];
  onStepClick: (stepId: WorkflowStepId) => void;
}

export function WorkflowSidebar({
  steps,
  onStepClick,
}: WorkflowSidebarProps) {
  return (
    <aside className="sidebar">
      <SidebarCommon />

      {/* Workflow Steps */}
      <div className="sidebar-section">
        <h3 className="sidebar-section-title">Workflow</h3>
        <div className="workflow-steps">
          {steps.map((step, index) => (
            <button
              key={step.id}
              className={`workflow-step ${step.status}`}
              onClick={() => onStepClick(step.id)}
            >
              <span className="workflow-step-number">
                {step.status === 'completed' ? (
                  <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                    <path
                      d="M11.5 4L5.5 10L2.5 7"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                ) : (
                  index + 1
                )}
              </span>
              <div className="workflow-step-content">
                <div className="workflow-step-title">{step.title}</div>
                <div className="workflow-step-subtitle">{step.subtitle}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
