# Drug Discovery Demo - Developer Setup Guide

## Prerequisites

- **Node.js**: 18.x or higher
- **npm**: 9.x or higher
- **Git**: For version control

## Quick Start

### 1. Install Dependencies
```bash
cd app
npm install
```

### 2. Start Development Server
```bash
npm run dev
```

The app will be available at `http://localhost:5173`

### 3. Demo Mode (No Backend Required)
The application includes a demo mode that works without any backend services:

1. Start the dev server
2. Leave the "Gateway URL" field empty
3. Toggle "Demo Mode" ON in the sidebar

Demo mode provides realistic mock data for all operations.

## Development Modes

### Demo Mode (Recommended for UI Development)
- No backend required
- All endpoints show as "ready"
- Mock data for all API calls
- Perfect for testing UI/UX changes

### Live Mode (Requires NIM Backend)
- Enter the gateway URL (e.g., `46.243.144.128`)
- Health checks run automatically
- Real API calls to NIM endpoints

## Backend Configuration

### Gateway URL Format
Enter just the IP or hostname (no protocol, no port):
```
46.243.144.128    # Correct
http://46.243.144.128  # Wrong
46.243.144.128:8000    # Wrong
```

### Required Endpoints
The application requires these NIM services:

| Service | Port | Required for |
|---------|------|--------------|
| Qwen3-80B | 8008 | AI planning, agent mode |
| OpenFold3 | 8000 | Structure prediction |
| Boltz2 | 8001 | Structure prediction (alternative) |
| MolMIM | 8006 | Molecule generation |
| DiffDock | 8007 | Molecular docking |

### Health Check
- Endpoints are checked when gateway URL is entered
- Status indicators: green (ready), red (not ready), yellow (checking)
- Click "Reconnect" to manually refresh status

## Project Structure

```
app/
├── src/
│   ├── components/        # React components
│   │   ├── steps/        # Workflow step components
│   │   ├── AgentChat.tsx # Agent mode UI
│   │   └── ...
│   ├── data/             # Static data (drugs, endpoints)
│   ├── hooks/            # Custom React hooks
│   ├── services/         # API integration services
│   ├── styles/           # CSS stylesheets
│   └── types/            # TypeScript type definitions
├── docs/                 # Documentation
├── public/               # Static assets
└── vite.config.ts        # Vite configuration
```

## Common Development Tasks

### Adding a New Drug Target
1. Edit `src/data/drugs.ts`
2. Add a new `DrugTarget` object with:
   - Unique `id`
   - Valid `uniprotId` for the target protein
   - Correct `oligomericState` (important for homodimers)
   - Valid `referenceSmiles` for the drug

### Modifying Workflow Steps
1. Step definitions are in `src/App.tsx` (e.g., `SMALL_MOLECULE_STEPS`)
2. Step components are in `src/components/steps/`
3. Add new step IDs to `WorkflowStepId` type in `src/types/workflow.ts`

### Adding a New NIM Endpoint
1. Add endpoint config to `src/data/endpoints.ts`
2. Add proxy route to `vite.config.ts` if needed
3. Create service function in appropriate file under `src/services/`

### Working with Mock Data
Mock data is in `src/data/mockData.ts` and `src/services/demoService.ts`:
- `MOCK_PROTEINS` - UniProt protein data
- `MOCK_STRUCTURES` - PDB structure data
- `MOCK_MOLECULES` - Generated molecule data
- `MOCK_DOCKING_RESULTS` - Docking scores

## Vite Configuration

### Dev Server Proxy
The Vite dev server proxies API requests to avoid CORS issues:

```typescript
// vite.config.ts
proxy: {
  '/api/nim-proxy': {
    target: 'http://localhost:3000',
    configure: (proxy) => {
      proxy.on('proxyReq', (proxyReq, req) => {
        // Extracts host/port/path from URL
        // Routes to: http://{host}:{port}{path}
      });
    }
  }
}
```

### Build for Production
```bash
npm run build
```

Output is in `dist/` directory. In production, API calls go directly to NIM endpoints (no proxy).

## Troubleshooting

### "All endpoints show as not-ready"
1. Verify gateway URL is correct (no protocol prefix)
2. Check if NIM services are running on the backend
3. Try toggling demo mode to verify UI works

### "CORS errors in console"
- In development, requests should go through the Vite proxy
- Check that `buildNimUrl()` returns proxy URL in dev mode
- Verify `vite.config.ts` proxy configuration

### "Structure prediction fails"
1. Check if the protein sequence is valid
2. Verify OpenFold3/Boltz2/OpenFold2 services are healthy
3. For homodimers, ensure `oligomericState` is set correctly

### "Mock data not loading"
1. Ensure demo mode is enabled
2. Check `isDemoMode()` in `src/services/demoService.ts`
3. Verify mock data exists for the selected drug target

### Build Errors
```bash
# Clear cache and reinstall
rm -rf node_modules
rm package-lock.json
npm install
npm run build
```

## Testing

### Manual Testing Checklist
1. **Demo Mode**
   - [ ] All drug targets load correctly
   - [ ] Structure viewer displays proteins
   - [ ] Molecule generation shows results
   - [ ] Docking step completes

2. **Live Mode**
   - [ ] Health checks complete
   - [ ] OpenFold3 structure prediction works
   - [ ] Boltz2 alternative works
   - [ ] MolMIM generates molecules
   - [ ] DiffDock produces docking poses

3. **Agent Mode**
   - [ ] LLM streaming works
   - [ ] Tools execute correctly
   - [ ] Results display in chat

### Key Test Cases
- **Imatinib (ABL1)** - Monomer protein
- **Ibuprofen (COX-2)** - Homodimer protein (tests multi-chain)
- **Custom prompt** - Free-form drug discovery

## Environment Variables

Currently, no environment variables are required. Configuration is done through:
- Gateway URL in the UI
- Demo mode toggle

For future deployment, consider:
```env
VITE_DEFAULT_GATEWAY_URL=your-gateway-ip
VITE_ENABLE_DEMO_MODE=true
```

## IDE Setup

### VS Code Extensions
- ESLint
- Prettier
- TypeScript Vue Plugin (for Vite)

### Recommended Settings
```json
{
  "editor.formatOnSave": true,
  "editor.defaultFormatter": "esbenp.prettier-vscode",
  "typescript.preferences.importModuleSpecifier": "relative"
}
```

## Additional Resources

- [ARCHITECTURE.md](./ARCHITECTURE.md) - System design documentation
- [NIM API Documentation](https://developer.nvidia.com/nim)
- [UniProt REST API](https://www.uniprot.org/help/api)
- [Mol* Viewer](https://molstar.org/)
