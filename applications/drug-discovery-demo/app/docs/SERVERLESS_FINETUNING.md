# Nebius Serverless Fine-Tuning - Design Document

## Overview

This document describes the design for a new "Serverless Fine-Tuning" mode in the Drug Discovery Demo. This mode showcases Nebius Serverless AI capabilities for training and deploying custom ML models for drug discovery.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Fine-Tuning Mode                                                    │    │
│  │  • Data Selection Step                                               │    │
│  │  • Model Configuration Step                                          │    │
│  │  • Training Step (with live updates)                                 │    │
│  │  • Evaluation Step                                                   │    │
│  │  • Deployment Step                                                   │    │
│  │  • Screening Step                                                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           BACKEND API GATEWAY                                │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  /api/finetuning/*                                                   │    │
│  │  • POST /data/chembl - Fetch ChEMBL data                            │    │
│  │  • POST /data/upload - Upload custom dataset                         │    │
│  │  • POST /train/start - Start training job                            │    │
│  │  • GET  /train/status/:jobId - Get job status                        │    │
│  │  • WS   /train/logs/:jobId - Stream training logs                    │    │
│  │  • POST /deploy - Deploy trained model                               │    │
│  │  • POST /predict/:modelId - Run inference                            │    │
│  │  • POST /predict/:modelId/batch - Batch inference                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         NEBIUS SERVERLESS AI                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐       │
│  │   TRAINING JOB   │    │  OBJECT STORAGE  │    │    ENDPOINT      │       │
│  │                  │    │                  │    │                  │       │
│  │  GPU: H200       │───▶│  Models/         │◀───│  Model Serving   │       │
│  │  Container:      │    │  Checkpoints/    │    │  GPU/CPU         │       │
│  │  chembert-train  │    │  Datasets/       │    │  Auto-scaling    │       │
│  │                  │    │  Logs/           │    │                  │       │
│  └──────────────────┘    └──────────────────┘    └──────────────────┘       │
│                                                                              │
│  CLI Commands Used:                                                          │
│  • nebius ai job create --platform gpu-h200-sxm --preset 1gpu-16vcpu-200gb  │
│  • nebius ai job get $JOB_ID                                                │
│  • nebius ai logs $JOB_ID                                                   │
│  • nebius ai endpoint create --platform gpu-h200-sxm                        │
│  • nebius ai endpoint get $ENDPOINT_ID                                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## User Flow

### Step 1: Data Selection
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SELECT TRAINING DATA                                        Step 1 of 6    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Choose how to provide training data for your model:                         │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  📊  USE CHEMBL DATABASE                              [Recommended]  │    │
│  │      Search millions of bioactivity measurements from ChEMBL         │    │
│  │                                                                      │    │
│  │      Target: [________________________] 🔍                           │    │
│  │               e.g., "COX-2", "CHEMBL220", "BCR-ABL"                  │    │
│  │                                                                      │    │
│  │      Activity Type: [IC50 ▼]    Min Samples: [500]                  │    │
│  │                                                                      │    │
│  │      [ Search ChEMBL ]                                               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  📁  UPLOAD YOUR DATA                                                │    │
│  │      CSV file with SMILES and activity values                        │    │
│  │                                                                      │    │
│  │      ┌──────────────────────────────────────────────────────────┐   │    │
│  │      │  Drag & drop CSV file here or click to browse            │   │    │
│  │      │                                                          │   │    │
│  │      │  Format: smiles,activity (header required)               │   │    │
│  │      └──────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  🎯  USE DEMO DATASET                                                │    │
│  │      Pre-loaded datasets for quick testing                           │    │
│  │                                                                      │    │
│  │      ○ COX-2 Inhibitors (2,847 compounds, IC50)                     │    │
│  │      ○ ABL1 Kinase Inhibitors (1,523 compounds, Ki)                 │    │
│  │      ○ Dopamine D2 Ligands (4,211 compounds, Ki)                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step 2: Data Preview & Validation
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DATA PREVIEW                                                Step 2 of 6    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Dataset: COX-2 Inhibitors from ChEMBL                                      │
│  Source: CHEMBL220 | Activity: IC50 (nM)                                    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  STATISTICS                                                          │    │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐│    │
│  │  │ Total        │ │ Valid        │ │ Activity     │ │ Molecular    ││    │
│  │  │ Compounds    │ │ SMILES       │ │ Range        │ │ Weight Range ││    │
│  │  │   2,847      │ │   2,831      │ │ 0.1 - 50μM   │ │ 180 - 650 Da ││    │
│  │  └──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ACTIVITY DISTRIBUTION                  │  SAMPLE COMPOUNDS         │    │
│  │  ┌─────────────────────────────┐       │  ┌────────────────────────┐│    │
│  │  │     ▃▅▇█▇▅▃▂▁              │       │  │ CC(C)Cc1ccc(cc1)...    ││    │
│  │  │  ───────────────────       │       │  │ IC50: 12.3 nM          ││    │
│  │  │  -2  -1   0   1   2        │       │  │                        ││    │
│  │  │     log10(IC50 μM)         │       │  │ [2D Structure]         ││    │
│  │  └─────────────────────────────┘       │  └────────────────────────┘│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  DATA SPLIT                                                          │    │
│  │  Training: 80% (2,265)  │  Validation: 10% (283)  │  Test: 10% (283)│    │
│  │  ════════════════════════  ════════════════         ════════════════│    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ⚠️  16 compounds removed due to invalid SMILES                             │
│                                                                              │
│                                         [ Back ]  [ Continue to Config → ]  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step 3: Model Configuration
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MODEL CONFIGURATION                                         Step 3 of 6    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  BASE MODEL                                                          │    │
│  │                                                                      │    │
│  │  ● ChemBERTa-77M-MTR          [Recommended]                         │    │
│  │    Pre-trained on 77M molecules, multi-task regression head         │    │
│  │    Best for: IC50, Ki, EC50 prediction                              │    │
│  │                                                                      │    │
│  │  ○ ChemBERTa-77M-MLM                                                │    │
│  │    Masked language model, good for general molecular understanding   │    │
│  │                                                                      │    │
│  │  ○ MolBERT-100M                                                     │    │
│  │    Larger model, better for complex SAR relationships               │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  TRAINING PARAMETERS                                                 │    │
│  │                                                                      │    │
│  │  Epochs:        [10 ▼]      Learning Rate:    [1e-5 ▼]              │    │
│  │  Batch Size:    [32 ▼]      Weight Decay:     [0.01   ]             │    │
│  │  Warmup Steps:  [100  ]     Early Stopping:   [✓] Patience: [3]    │    │
│  │                                                                      │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │  💡 Recommended settings auto-selected based on dataset size  │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ☁️  NEBIUS SERVERLESS COMPUTE                                       │    │
│  │                                                                      │    │
│  │  GPU Type:      H200 SXM (80GB)                                     │    │
│  │  Preset:        1gpu-16vcpu-200gb                                   │    │
│  │  Est. Time:     ~8-12 minutes                                       │    │
│  │  Est. Cost:     ~$0.80 - $1.20                                      │    │
│  │                                                                      │    │
│  │  ┌───────────────────────────────────────────────────────────────┐  │    │
│  │  │  💰 Pay only for GPU time used. No idle costs.                │  │    │
│  │  └───────────────────────────────────────────────────────────────┘  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│                                         [ Back ]  [ Start Training → ]      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step 4: Training (Live Updates)
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TRAINING ON NEBIUS SERVERLESS                               Step 4 of 6    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ☁️  NEBIUS SERVERLESS GPU             Job ID: ft-2024-abc123       │    │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │    │
│  │  Platform: gpu-h200-sxm  •  Preset: 1gpu-16vcpu-200gb  •  Training  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌────────────────────────────┐  ┌────────────────────────────────────┐     │
│  │  PROGRESS                  │  │  LIVE METRICS                      │     │
│  │                            │  │                                    │     │
│  │  ██████████████░░░░░ 72%   │  │  Training Loss                     │     │
│  │                            │  │  ┌────────────────────────────┐    │     │
│  │  Epoch:  7 / 10            │  │  │ 0.8─╲                      │    │     │
│  │  Step:   580 / 800         │  │  │ 0.6─ ╲                     │    │     │
│  │                            │  │  │ 0.4─  ╲___                 │    │     │
│  │  Elapsed: 6m 42s           │  │  │ 0.2─     ╲____╲___        │    │     │
│  │  ETA:     ~2m 30s          │  │  └────────────────────────────┘    │     │
│  │                            │  │  Current: 0.187  Best: 0.183       │     │
│  │  ┌──────────────────────┐  │  │                                    │     │
│  │  │ Loss:     0.187 ↓    │  │  │  Validation R²                    │     │
│  │  │ Val R²:   0.847 ↑    │  │  │  ┌────────────────────────────┐    │     │
│  │  │ Val MAE:  0.312      │  │  │  │ 0.9─           ___──────   │    │     │
│  │  └──────────────────────┘  │  │  │ 0.7─     ___──            │    │     │
│  └────────────────────────────┘  │  │ 0.5─ __──                  │    │     │
│                                  │  └────────────────────────────┘    │     │
│                                  │  Current: 0.847  Best: 0.851       │     │
│                                  └────────────────────────────────────┘     │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  💰 SERVERLESS COST TRACKER                                          │    │
│  │  ════════════════════════════════════════════════════════════════    │    │
│  │  GPU Time: 6m 42s  │  Current Cost: $0.67  │  Rate: $6.00/hr        │    │
│  │  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░  Est. Total: $0.92  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  📋 TRAINING LOG                                            [Expand]│    │
│  │  ─────────────────────────────────────────────────────────────────  │    │
│  │  [10:23:45] 🚀 Requesting Nebius Serverless GPU...                  │    │
│  │  [10:23:52] ✓ GPU allocated: gpu-h200-sxm (cold start: 7.2s)       │    │
│  │  [10:23:53] 📦 Loading ChemBERTa-77M-MTR base model...              │    │
│  │  [10:24:01] 📊 Dataset loaded: 2,265 train / 283 val samples        │    │
│  │  [10:24:15] ✓ Epoch 1/10 - Loss: 0.891 - Val R²: 0.623             │    │
│  │  [10:25:02] ✓ Epoch 2/10 - Loss: 0.534 - Val R²: 0.745             │    │
│  │  [10:25:48] ✓ Epoch 3/10 - Loss: 0.342 - Val R²: 0.812             │    │
│  │  [10:26:35] ✓ Epoch 4/10 - Loss: 0.267 - Val R²: 0.834             │    │
│  │  [10:27:21] ✓ Epoch 5/10 - Loss: 0.221 - Val R²: 0.841             │    │
│  │  [10:28:08] ✓ Epoch 6/10 - Loss: 0.198 - Val R²: 0.845             │    │
│  │  [10:28:54] ⏳ Epoch 7/10 - Training step 580/800...                │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│                                                          [ Cancel Training ] │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step 5: Evaluation
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  MODEL EVALUATION                                            Step 5 of 6    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ✅ Training Complete!  Total Time: 9m 12s  │  Cost: $0.92                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  TEST SET PERFORMANCE                                                │    │
│  │  ┌────────────────┐ ┌────────────────┐ ┌────────────────┐           │    │
│  │  │  R² Score      │ │  MAE           │ │  RMSE          │           │    │
│  │  │    0.856       │ │    0.298       │ │    0.412       │           │    │
│  │  │  ████████▌     │ │  log10(μM)     │ │  log10(μM)     │           │    │
│  │  │  Excellent     │ │  Good          │ │  Good          │           │    │
│  │  └────────────────┘ └────────────────┘ └────────────────┘           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌──────────────────────────────────┐  ┌──────────────────────────────┐     │
│  │  PREDICTED VS ACTUAL             │  │  RESIDUAL DISTRIBUTION       │     │
│  │  ┌────────────────────────────┐  │  │  ┌────────────────────────┐  │     │
│  │  │      •  •••• •            │  │  │  │         ▃▅▇█▇▅▃        │  │     │
│  │  │    •••••••••••• •         │  │  │  │       ▂▅████████▅▂     │  │     │
│  │  │  ••••••••••••••••         │  │  │  │     ▁▃█████████████▃▁  │  │     │
│  │  │ •••••••••••••••••         │  │  │  └────────────────────────┘  │     │
│  │  │•••••••••••••••••••        │  │  │  Mean: -0.02  Std: 0.41      │     │
│  │  └────────────────────────────┘  │  │  Normal distribution ✓       │     │
│  │  R² = 0.856                      │  └──────────────────────────────┘     │
│  └──────────────────────────────────┘                                       │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  COMPARISON: Your Model vs Baseline                                  │    │
│  │  ────────────────────────────────────────────────────────────────── │    │
│  │                        Your Model      Random Forest    Baseline    │    │
│  │  R² Score              0.856           0.721            0.534       │    │
│  │  MAE (log10 μM)        0.298           0.412            0.623       │    │
│  │  Inference Time        2.3ms           45ms             N/A         │    │
│  │  ────────────────────────────────────────────────────────────────── │    │
│  │  🎉 Your model outperforms the baseline by 60%!                     │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│                                   [ Back ]  [ Deploy to Serverless → ]      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Step 6: Deployment & Screening
```
┌─────────────────────────────────────────────────────────────────────────────┐
│  DEPLOY & SCREEN                                             Step 6 of 6    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  ☁️  NEBIUS SERVERLESS ENDPOINT                                      │    │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │    │
│  │  Status: ● Active    Model: cox2-predictor-v1    Created: 2 min ago │    │
│  │  URL: https://ep-abc123.serverless.nebius.cloud                      │    │
│  │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │    │
│  │  Auto-scaling: 0-10 replicas  │  Cold start: ~3s  │  Cost: $0/idle  │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  🔬 VIRTUAL SCREENING                                                │    │
│  │                                                                      │    │
│  │  ┌────────────────────────────────────────────────────────────────┐ │    │
│  │  │  Upload compound library (CSV/SDF) or paste SMILES:            │ │    │
│  │  │  ┌──────────────────────────────────────────────────────────┐  │ │    │
│  │  │  │  CC(C)Cc1ccc(cc1)C(C)C(=O)O                              │  │ │    │
│  │  │  │  COc1ccc2c(c1)c(CC(=O)O)c(C)n2C(=O)c3ccc(Cl)cc3          │  │ │    │
│  │  │  │  Cc1ccc(cc1)C2=CC(=O)c3c(O2)ccc(c3)O                     │  │ │    │
│  │  │  │  ...                                                      │  │ │    │
│  │  │  └──────────────────────────────────────────────────────────┘  │ │    │
│  │  │                                                                │ │    │
│  │  │  Compounds: 1,000  │  [ Screen Library ]                       │ │    │
│  │  └────────────────────────────────────────────────────────────────┘ │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  📊 SCREENING RESULTS                              1,000 compounds  │    │
│  │  ────────────────────────────────────────────────────────────────── │    │
│  │  Screened in 2.3 seconds (435 compounds/sec)                        │    │
│  │                                                                      │    │
│  │  Rank │ SMILES                              │ Pred IC50  │ Conf     │    │
│  │  ─────┼─────────────────────────────────────┼────────────┼──────────│    │
│  │   1   │ CC(C)Cc1ccc(cc1)C(C)C(=O)O          │  12.3 nM   │  High    │    │
│  │   2   │ COc1ccc2c(c1)c(CC(=O)O)c(C)n2...    │  18.7 nM   │  High    │    │
│  │   3   │ Cc1ccc(cc1)C2=CC(=O)c3c(O2)cc...    │  24.1 nM   │  Medium  │    │
│  │   4   │ O=C(O)Cc1ccccc1Nc2c(Cl)cccc2Cl      │  31.5 nM   │  High    │    │
│  │   5   │ COc1ccc(cc1OC)C2CC(=O)c3c(O)c...    │  45.2 nM   │  Medium  │    │
│  │  ─────┴─────────────────────────────────────┴────────────┴──────────│    │
│  │                                                                      │    │
│  │  [ Download All Results (CSV) ]  [ Download Top 100 ]  [ Dock Top ] │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  💡 Tip: Use these predictions to prioritize compounds for docking!         │
│                                                                              │
│                              [ Start Over ]  [ Go to Docking Workflow → ]   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Technical Implementation

### Frontend Components

```
src/components/finetuning/
├── FineTuningMode.tsx           # Main mode container
├── steps/
│   ├── DataSelectionStep.tsx    # ChEMBL search, upload, demo data
│   ├── DataPreviewStep.tsx      # Statistics, distribution, validation
│   ├── ModelConfigStep.tsx      # Base model, hyperparameters
│   ├── TrainingStep.tsx         # Live training with WebSocket
│   ├── EvaluationStep.tsx       # Metrics, plots, comparison
│   └── ScreeningStep.tsx        # Deploy and screen compounds
├── components/
│   ├── ChemBLSearch.tsx         # Target search component
│   ├── DataUploader.tsx         # CSV/SDF file upload
│   ├── TrainingProgress.tsx     # Live progress visualization
│   ├── MetricsChart.tsx         # Loss/R² charts
│   ├── CostTracker.tsx          # Serverless cost display
│   ├── ServerlessStatus.tsx     # GPU status badge
│   └── ScreeningResults.tsx     # Results table with export
└── hooks/
    ├── useTrainingJob.ts        # Training job management
    ├── useChemBLData.ts         # ChEMBL API integration
    └── useServerlessEndpoint.ts # Inference endpoint
```

### Context for Fine-Tuning Mode

```typescript
// src/contexts/FineTuningContext.tsx

interface FineTuningState {
  // Data
  dataSource: 'chembl' | 'upload' | 'demo' | null;
  dataset: DatasetInfo | null;

  // Model config
  baseModel: 'chemberta-77m-mtr' | 'chemberta-77m-mlm' | 'molbert-100m';
  hyperparameters: HyperParameters;

  // Training
  trainingJobId: string | null;
  trainingStatus: TrainingStatus | null;
  trainingLogs: TrainingLogEntry[];

  // Results
  trainedModelId: string | null;
  evaluationMetrics: EvaluationMetrics | null;

  // Deployment
  endpointId: string | null;
  endpointStatus: EndpointStatus | null;

  // Screening
  screeningResults: ScreeningResult[] | null;
}

interface TrainingStatus {
  state: 'pending' | 'initializing' | 'training' | 'completed' | 'failed' | 'cancelled';
  epoch: number;
  totalEpochs: number;
  step: number;
  totalSteps: number;
  loss: number;
  valMetrics: { r2: number; mae: number; rmse: number };
  elapsedTime: number;
  estimatedTimeRemaining: number;
  cost: number;
  gpuUtilization: number;
}
```

### Backend API Service

```typescript
// src/services/fineTuningApi.ts

const FINETUNING_BASE = '/api/finetuning';

export const fineTuningApi = {
  // Data
  searchChembl: (targetQuery: string, activityType: string, minSamples: number) =>
    post(`${FINETUNING_BASE}/data/chembl`, { targetQuery, activityType, minSamples }),

  uploadDataset: (file: File) =>
    postFormData(`${FINETUNING_BASE}/data/upload`, { file }),

  getDemoDataset: (datasetId: string) =>
    get(`${FINETUNING_BASE}/data/demo/${datasetId}`),

  validateDataset: (datasetId: string) =>
    post(`${FINETUNING_BASE}/data/validate`, { datasetId }),

  // Training
  startTraining: (config: TrainingConfig) =>
    post(`${FINETUNING_BASE}/train/start`, config),

  getTrainingStatus: (jobId: string) =>
    get(`${FINETUNING_BASE}/train/status/${jobId}`),

  cancelTraining: (jobId: string) =>
    post(`${FINETUNING_BASE}/train/cancel/${jobId}`),

  // Returns WebSocket URL for live updates
  getTrainingLogsWsUrl: (jobId: string) =>
    `wss://${window.location.host}${FINETUNING_BASE}/train/logs/${jobId}`,

  // Deployment
  deployModel: (modelId: string, config: DeployConfig) =>
    post(`${FINETUNING_BASE}/deploy`, { modelId, ...config }),

  getEndpointStatus: (endpointId: string) =>
    get(`${FINETUNING_BASE}/endpoints/${endpointId}`),

  deleteEndpoint: (endpointId: string) =>
    del(`${FINETUNING_BASE}/endpoints/${endpointId}`),

  // Inference
  predict: (endpointId: string, smiles: string[]) =>
    post(`${FINETUNING_BASE}/predict/${endpointId}`, { smiles }),

  batchPredict: (endpointId: string, file: File) =>
    postFormData(`${FINETUNING_BASE}/predict/${endpointId}/batch`, { file }),
};
```

### Nebius CLI Wrapper (Backend)

```python
# backend/nebius_serverless.py

import subprocess
import json
from typing import Optional

class NebiusServerless:
    """Wrapper for Nebius CLI commands for serverless AI."""

    def create_training_job(
        self,
        name: str,
        dataset_path: str,  # S3 path
        model_output_path: str,  # S3 path
        base_model: str,
        hyperparameters: dict,
    ) -> str:
        """Create a serverless training job."""

        # Build training command
        train_cmd = f"""
        python train.py \\
            --dataset {dataset_path} \\
            --output {model_output_path} \\
            --base-model {base_model} \\
            --epochs {hyperparameters['epochs']} \\
            --batch-size {hyperparameters['batch_size']} \\
            --learning-rate {hyperparameters['learning_rate']}
        """

        result = subprocess.run([
            'nebius', 'ai', 'job', 'create',
            '--name', name,
            '--image', 'registry.nebius.cloud/drug-discovery/chemberta-trainer:latest',
            '--container-command', '/bin/bash',
            '--args', f'-c "{train_cmd}"',
            '--platform', 'gpu-h200-sxm',
            '--preset', '1gpu-16vcpu-200gb',
            '--timeout', '1h',
            '--subnet-id', self.subnet_id,
            '--format', 'json',
        ], capture_output=True, text=True)

        job_info = json.loads(result.stdout)
        return job_info['id']

    def get_job_status(self, job_id: str) -> dict:
        """Get job status and metrics."""
        result = subprocess.run([
            'nebius', 'ai', 'job', 'get', job_id,
            '--format', 'json',
        ], capture_output=True, text=True)
        return json.loads(result.stdout)

    def get_job_logs(self, job_id: str) -> str:
        """Get job logs."""
        result = subprocess.run([
            'nebius', 'ai', 'logs', job_id,
        ], capture_output=True, text=True)
        return result.stdout

    def create_endpoint(
        self,
        name: str,
        model_path: str,  # S3 path to trained model
    ) -> str:
        """Deploy model as serverless endpoint."""

        result = subprocess.run([
            'nebius', 'ai', 'endpoint', 'create',
            '--name', name,
            '--image', 'registry.nebius.cloud/drug-discovery/chemberta-server:latest',
            '--platform', 'gpu-h200-sxm',
            '--preset', '1gpu-16vcpu-200gb',
            '--public',
            '--container-port', '8080',
            '--container-env', f'MODEL_PATH={model_path}',
            '--auth', 'token',
            '--token', self._generate_token(),
            '--subnet-id', self.subnet_id,
            '--format', 'json',
        ], capture_output=True, text=True)

        endpoint_info = json.loads(result.stdout)
        return endpoint_info['id']
```

## Demo Mode

For demo mode (when Nebius is not connected), we'll simulate:
- Training progress with realistic metrics
- GPU allocation and cost tracking
- Model evaluation results
- Endpoint deployment
- Inference predictions

```typescript
// src/services/demoFineTuning.ts

export async function* simulateTraining(config: TrainingConfig): AsyncGenerator<TrainingStatus> {
  const totalEpochs = config.hyperparameters.epochs;
  const stepsPerEpoch = Math.ceil(config.datasetSize / config.hyperparameters.batchSize);

  // Simulate cold start
  yield { state: 'initializing', message: 'Requesting Nebius Serverless GPU...' };
  await sleep(2000);
  yield { state: 'initializing', message: 'GPU allocated: gpu-h200-sxm (cold start: 7.2s)' };
  await sleep(1000);
  yield { state: 'initializing', message: 'Loading base model...' };
  await sleep(2000);

  // Simulate training epochs
  for (let epoch = 1; epoch <= totalEpochs; epoch++) {
    for (let step = 1; step <= stepsPerEpoch; step++) {
      const progress = ((epoch - 1) * stepsPerEpoch + step) / (totalEpochs * stepsPerEpoch);

      yield {
        state: 'training',
        epoch,
        totalEpochs,
        step,
        totalSteps: stepsPerEpoch,
        loss: 0.9 * Math.exp(-3 * progress) + 0.1 + Math.random() * 0.05,
        valMetrics: {
          r2: 0.5 + 0.4 * (1 - Math.exp(-4 * progress)),
          mae: 0.6 * Math.exp(-2 * progress) + 0.25,
          rmse: 0.8 * Math.exp(-2 * progress) + 0.35,
        },
        elapsedTime: progress * 600000, // ~10 min total
        estimatedTimeRemaining: (1 - progress) * 600000,
        cost: progress * 1.0, // ~$1 total
        gpuUtilization: 85 + Math.random() * 10,
      };

      await sleep(100); // Fast simulation
    }
  }

  yield { state: 'completed', message: 'Training complete!' };
}
```

## Integration Points

### With Existing Drug Discovery Workflow

1. **After Screening**: "Use top hits in docking workflow"
2. **Before Docking**: "Pre-filter with trained model"
3. **Molecule Generation**: "Score generated molecules"

### Data Flow

```
Fine-Tuning Mode                    Drug Discovery Mode
─────────────────                   ───────────────────
     │                                     │
     │  Trained Model                      │
     ├─────────────────────────────────────┤
     │                                     │
     │  Screening Results ──────▶ Docking Step
     │                                     │
     │  Top Predictions ────────▶ Molecule Analysis
     │                                     │
```

## File Structure

```
src/
├── components/
│   ├── finetuning/              # New fine-tuning components
│   │   ├── FineTuningMode.tsx
│   │   ├── FineTuningSidebar.tsx
│   │   ├── steps/
│   │   │   ├── DataSelectionStep.tsx
│   │   │   ├── DataPreviewStep.tsx
│   │   │   ├── ModelConfigStep.tsx
│   │   │   ├── TrainingStep.tsx
│   │   │   ├── EvaluationStep.tsx
│   │   │   └── ScreeningStep.tsx
│   │   └── components/
│   │       ├── ChemBLSearch.tsx
│   │       ├── TrainingProgress.tsx
│   │       ├── MetricsChart.tsx
│   │       └── CostTracker.tsx
│   └── ... (existing components)
├── contexts/
│   ├── FineTuningContext.tsx    # New context
│   └── ... (existing contexts)
├── services/
│   ├── fineTuningApi.ts         # API client
│   ├── demoFineTuning.ts        # Demo mode simulation
│   ├── chemblApi.ts             # ChEMBL integration
│   └── ... (existing services)
├── data/
│   ├── demoDatasets.ts          # Pre-loaded datasets
│   └── ... (existing data)
└── types/
    ├── finetuning.ts            # Type definitions
    └── ... (existing types)
```

## Next Steps

1. **Phase 1**: Create basic UI structure and navigation
2. **Phase 2**: Implement data selection with ChEMBL integration
3. **Phase 3**: Build training step with demo mode simulation
4. **Phase 4**: Add evaluation visualizations
5. **Phase 5**: Implement deployment and screening
6. **Phase 6**: Connect to real Nebius Serverless API
7. **Phase 7**: Integration with existing workflows
