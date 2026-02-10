/**
 * Dataset Registry
 *
 * Curated open-source datasets for fine-tuning molecular and protein models.
 */

import type { CuratedDataset, ModelModality } from '../types/finetuning';

export const DATASET_REGISTRY: CuratedDataset[] = [
  // ============================================================================
  // Molecular Datasets
  // ============================================================================
  {
    id: 'chembl-cox2',
    name: 'ChEMBL COX-2 Inhibitors',
    source: 'ChEMBL',
    modality: 'molecular',
    size: 2847,
    taskType: 'regression',
    description: 'IC50 values for cyclooxygenase-2 inhibitors from ChEMBL database.',
    columns: ['smiles', 'IC50 (nM)'],
    sampleData: [
      { input: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O', label: '12.5 nM' },
      { input: 'COc1ccc2c(c1)c(CC(=O)O)c(C)n2C(=O)c3ccc(Cl)cc3', label: '3.2 nM' },
    ],
  },
  {
    id: 'chembl-kinase',
    name: 'ChEMBL Kinase Inhibitors',
    source: 'ChEMBL',
    modality: 'molecular',
    size: 4523,
    taskType: 'regression',
    description: 'Ki values for ABL1 and other kinase inhibitors from ChEMBL.',
    columns: ['smiles', 'Ki (nM)'],
    sampleData: [
      { input: 'Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc4nccc(-c5cccnc5)n4', label: '1.1 nM' },
      { input: 'CC(C)c1ccc(NC(=O)Nc2ccc(OC3CCCC3)cc2)cc1', label: '45.0 nM' },
    ],
  },
  {
    id: 'bbbp',
    name: 'BBBP (Blood-Brain Barrier)',
    source: 'MoleculeNet',
    modality: 'molecular',
    size: 2039,
    taskType: 'regression',
    description: 'Blood-brain barrier penetration dataset. Binary permeability labels.',
    columns: ['smiles', 'permeability'],
    sampleData: [
      { input: 'O=C(O)c1ccccc1O', label: '1 (permeable)' },
      { input: 'CC(=O)Oc1ccccc1C(=O)O', label: '1 (permeable)' },
    ],
  },
  {
    id: 'bace',
    name: 'BACE (Beta-Secretase)',
    source: 'MoleculeNet',
    modality: 'molecular',
    size: 1513,
    taskType: 'regression',
    description: 'Quantitative binding results for beta-secretase 1 (BACE-1) inhibitors.',
    columns: ['smiles', 'pIC50'],
    sampleData: [
      { input: 'O=C(NC1CCCCC1)c1cc2c(F)cccc2[nH]1', label: '5.24' },
      { input: 'Fc1cccc(-c2cc(NC(=O)C3CCCCC3)[nH]c2=O)c1', label: '6.78' },
    ],
  },
  {
    id: 'hiv',
    name: 'HIV Activity',
    source: 'MoleculeNet',
    modality: 'molecular',
    size: 41127,
    taskType: 'regression',
    description: 'Ability to inhibit HIV replication. Large benchmark dataset.',
    columns: ['smiles', 'activity'],
    sampleData: [
      { input: 'CCC1=[O+][Cu-3]2([O+]=C(CC)C1)[O+]=C(CC)CC(CC)=[O+]2', label: '0 (inactive)' },
      { input: 'C(=Cc1ccccc1)c1ccccc1', label: '0 (inactive)' },
    ],
  },
  {
    id: 'tox21',
    name: 'Tox21 (Toxicity)',
    source: 'MoleculeNet',
    modality: 'molecular',
    size: 7831,
    taskType: 'regression',
    description: 'Toxicity data on 12 biological targets including nuclear receptors and stress response.',
    columns: ['smiles', 'NR-AR', 'NR-ER', 'SR-ARE', '...'],
    sampleData: [
      { input: 'CCOc1ccc2nc(S(N)(=O)=O)sc2c1', label: '0 (non-toxic)' },
      { input: 'CCN1C(=O)NC(c2ccccc2)C1=O', label: '1 (toxic)' },
    ],
  },
  {
    id: 'lipophilicity',
    name: 'Lipophilicity (LogD)',
    source: 'MoleculeNet',
    modality: 'molecular',
    size: 4200,
    taskType: 'regression',
    description: 'Experimental octanol/water distribution coefficient at pH 7.4.',
    columns: ['smiles', 'logD'],
    sampleData: [
      { input: 'Cn1c(CN2CCN(CC2)c3ccc(Cl)cc3)nc4ccccc14', label: '3.54' },
      { input: 'COc1cc(OC)c(cc1NC(=O)CSCC(=O)O)S(=O)(=O)N2C(C)CCc3ccccc32', label: '2.11' },
    ],
  },
  {
    id: 'freesolv',
    name: 'FreeSolv',
    source: 'MoleculeNet',
    modality: 'molecular',
    size: 642,
    taskType: 'regression',
    description: 'Hydration free energy of small molecules in water.',
    columns: ['smiles', 'free_energy (kcal/mol)'],
    sampleData: [
      { input: 'CN(C)C(=O)c1ccc(cc1)OC', label: '-11.01' },
      { input: 'CCCC=O', label: '-3.18' },
    ],
  },
  {
    id: 'qm9',
    name: 'QM9 (Quantum Properties)',
    source: 'MoleculeNet',
    modality: 'molecular',
    size: 133885,
    taskType: 'regression',
    description: 'Quantum mechanical properties of 134k small organic molecules.',
    columns: ['smiles', 'mu', 'alpha', 'HOMO', 'LUMO', 'gap', '...'],
    sampleData: [
      { input: 'C', label: 'mu=0, HOMO=-0.3877' },
      { input: 'CC', label: 'mu=0, HOMO=-0.3593' },
    ],
  },
  {
    id: 'zinc250k',
    name: 'ZINC250K Subset',
    source: 'ZINC',
    modality: 'molecular',
    size: 249455,
    taskType: 'regression',
    description: 'Drug-like subset of ZINC database with logP, QED, and SA scores.',
    columns: ['smiles', 'logP', 'qed', 'SAS'],
    sampleData: [
      { input: 'CC(C)(C)c1ccc2occ(CC(=O)Nc3ccccc3F)c2c1', label: 'logP=5.05' },
      { input: 'C[C@@H]1CC(Nc2cncc(-c3nncn3C)c2)C[C@@H](C)C1', label: 'logP=1.78' },
    ],
  },

  // ============================================================================
  // Protein Datasets
  // ============================================================================
  {
    id: 'stability',
    name: 'Protein Stability (Rocklin/FLIP)',
    source: 'FLIP Benchmark',
    modality: 'protein',
    size: 67753,
    taskType: 'classification',
    description: 'Stability measurements for designed miniproteins. Binary stable/unstable labels.',
    columns: ['sequence', 'stability_label'],
    sampleData: [
      { input: 'MEKFLILNKQKQLAWDLNPHADYLARIQKLF...', label: 'stable' },
      { input: 'GKKVFLIANAQKALIDLNVSTQDDLARIQALFE...', label: 'unstable' },
    ],
  },
  {
    id: 'fluorescence',
    name: 'GFP Fluorescence (TAPE)',
    source: 'TAPE Benchmark',
    modality: 'protein',
    size: 21446,
    taskType: 'classification',
    description: 'Fluorescence intensity of GFP variants. Continuous to 3-class (low/med/high).',
    columns: ['sequence', 'fluorescence_class'],
    sampleData: [
      { input: 'SKGEELFTGVVPILVELDGDVNGHKFSVSGEG...', label: 'high' },
      { input: 'SKGEELFTGVVPILVELDGDVNGHKFAVSGEG...', label: 'low' },
    ],
  },
  {
    id: 'subcellular-localization',
    name: 'Subcellular Localization (DeepLoc)',
    source: 'DeepLoc',
    modality: 'protein',
    size: 13858,
    taskType: 'classification',
    description: 'Predict protein subcellular location (10 classes: nucleus, cytoplasm, etc.).',
    columns: ['sequence', 'location'],
    sampleData: [
      { input: 'MFRSLLRRKSTLLQHISLLLL...', label: 'Extracellular' },
      { input: 'MASGHRGRRRALRGTPSPRLL...', label: 'Nucleus' },
    ],
  },
  {
    id: 'secondary-structure',
    name: 'Secondary Structure (NetSurfP)',
    source: 'NetSurfP-2.0',
    modality: 'protein',
    size: 10848,
    taskType: 'classification',
    description: 'Per-residue secondary structure prediction (3-state: helix, sheet, coil).',
    columns: ['sequence', 'ss3_labels'],
    sampleData: [
      { input: 'MGSSHHHHHHSSGLVPRGSH...', label: 'CCCCCCCCCCCCCCHHHHHH...' },
      { input: 'MHHHHHHSSGVDLGTENLYFQ...', label: 'CCCCCCCCCCCCCCEEEEE...' },
    ],
  },
  {
    id: 'enzyme-commission',
    name: 'Enzyme Commission (EC)',
    source: 'CLEAN',
    modality: 'protein',
    size: 22168,
    taskType: 'classification',
    description: 'Enzyme function classification using EC numbers (6 top-level classes).',
    columns: ['sequence', 'ec_class'],
    sampleData: [
      { input: 'MKVLLLSGVLAALVAGSMASE...', label: 'EC 3 (Hydrolase)' },
      { input: 'MGTKRKKDFVNTSDELLPEFQ...', label: 'EC 2 (Transferase)' },
    ],
  },
  {
    id: 'thermostability',
    name: 'Thermostability (Meltome)',
    source: 'Meltome Atlas',
    modality: 'protein',
    size: 25869,
    taskType: 'classification',
    description: 'Thermal stability classes based on melting temperature (thermophilic vs mesophilic).',
    columns: ['sequence', 'thermo_class'],
    sampleData: [
      { input: 'MKYNNHDIAMKLEVPEV...', label: 'thermophilic' },
      { input: 'MSDEQLKMIGKFLEELF...', label: 'mesophilic' },
    ],
  },
];

export function getDatasetsByModality(modality: ModelModality): CuratedDataset[] {
  return DATASET_REGISTRY.filter((d) => d.modality === modality);
}

export function getDatasetById(id: string): CuratedDataset | undefined {
  return DATASET_REGISTRY.find((d) => d.id === id);
}
