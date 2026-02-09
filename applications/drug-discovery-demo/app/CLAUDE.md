# Claude Code Project Configuration

## Project Overview

Drug Discovery Demo - Interactive React application showcasing NVIDIA NIMs for AI-driven drug discovery on Nebius AI Cloud.

## Custom Agents

### UI Testing Agent

Use this agent to validate UI components, user flows, and accessibility.

**How to invoke:**
```
Use the Task tool with subagent_type="Explore" and include "UI-TESTING-AGENT" in the prompt
```

**Agent Prompt Template:**
```
UI-TESTING-AGENT: You are a specialized UI testing agent for the Drug Discovery Demo.

Your responsibilities:
1. Review React components for correctness and best practices
2. Check for accessibility issues (ARIA labels, keyboard navigation, color contrast)
3. Validate user flows work correctly (step-by-step workflow, agent chat)
4. Identify missing error handling or edge cases
5. Check responsive design and mobile compatibility
6. Verify loading states, error states, and empty states are handled
7. Review CSS for consistency and potential issues

Focus areas:
- src/components/ - All React components
- src/styles/ - CSS files
- User interactions and state management

Report findings as:
- CRITICAL: Broken functionality
- WARNING: Usability issues
- SUGGESTION: Improvements

[TASK]: {describe what to test}
```

---

### Drug Discovery Agent

Use this agent to validate scientific accuracy and drug discovery workflow correctness.

**How to invoke:**
```
Use the Task tool with subagent_type="Explore" and include "DRUG-DISCOVERY-AGENT" in the prompt
```

**Agent Prompt Template:**
```
DRUG-DISCOVERY-AGENT: You are a specialized drug discovery validation agent.

Your responsibilities:
1. Validate scientific accuracy of drug targets (UniProt IDs, protein names, mechanisms)
2. Check mock data correctness (SMILES strings, PDB structures, docking scores)
3. Verify API request/response formats match NIM specifications
4. Ensure drug-likeness calculations are correct (Lipinski, QED)
5. Validate molecule generation parameters and constraints
6. Check docking workflow logic and confidence score handling
7. Review LLM prompts for scientific accuracy

Focus areas:
- src/data/drugs.ts - Drug target definitions
- src/data/mockData.ts - Mock scientific data
- src/services/ - API integrations
- Scientific caveats and disclaimers

Report findings as:
- SCIENTIFIC ERROR: Incorrect data or calculations
- API MISMATCH: Request/response format issues
- DATA QUALITY: Mock data improvements needed
- ACCURACY: Suggestions for better scientific representation

[TASK]: {describe what to validate}
```

---

## Example Agent Invocations

### Run UI Testing Agent
```
Task: UI-TESTING-AGENT - Review the K8sScalingPanel component for accessibility issues, proper error handling, and loading states. Check that the modal overlay works correctly and keyboard navigation is supported.
```

### Run Drug Discovery Agent
```
Task: DRUG-DISCOVERY-AGENT - Validate the mock protein data in mockData.ts. Ensure UniProt IDs are correct, protein sequences are valid, and the structure prediction mock data has realistic confidence scores.
```

### Run Both Agents After Changes
```
After making changes to the codebase, spawn both agents to validate:
1. UI agent checks component correctness
2. Drug discovery agent checks scientific accuracy
```

---

## Code Quality Guidelines

### React Components
- Use functional components with hooks
- Proper TypeScript typing for all props
- Handle loading, error, and empty states
- Use semantic HTML and ARIA attributes

### Services
- All API calls should check for demo mode first
- Proper error handling with user-friendly messages
- TypeScript interfaces for all request/response types

### Scientific Data
- All UniProt IDs should be valid and verifiable
- SMILES strings should be chemically valid
- Confidence scores should be in realistic ranges
- Include scientific caveats where appropriate

---

## Testing Checklist

### Before Committing
- [ ] Build passes: `npm run build`
- [ ] No TypeScript errors
- [ ] UI flows work in browser
- [ ] Demo mode functions correctly
- [ ] K8s scaling panel works (if kubectl connected)

### Periodic Validation
- [ ] Run UI Testing Agent on modified components
- [ ] Run Drug Discovery Agent on data changes
- [ ] Verify all drug targets have correct UniProt IDs
- [ ] Check mock data produces realistic results
