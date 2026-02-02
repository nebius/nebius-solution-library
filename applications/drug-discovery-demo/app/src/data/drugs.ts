// Target drugs for rediscovery workflow

export interface DrugTarget {
  id: string;
  name: string;
  icon: string;
  category: string;
  description: string;
  mechanism: string;
  isCustom?: boolean; // For the custom prompt option
  targetProtein: {
    name: string;
    uniprotId: string;
    sequence: string; // Kept as fallback, will be fetched from UniProt
  };
  referenceSMILES: string;
  referenceQED?: number; // Pre-computed QED score for the reference drug (from RDKit/literature)
  llmPrompt: string;
}

export const DRUG_TARGETS: DrugTarget[] = [
  {
    id: 'ibuprofen',
    name: 'Ibuprofen',
    icon: '💊',
    category: 'Analgesic / Anti-inflammatory',
    description: 'Design molecules targeting COX-2 enzyme for anti-inflammatory effects. Goal: rediscover ibuprofen-like compounds.',
    mechanism: 'Blocks COX-1 and COX-2 enzymes → reduces prostaglandins → lowers pain, inflammation, and fever.',
    targetProtein: {
      name: 'COX-2 (Cyclooxygenase-2)',
      uniprotId: 'P35354',
      // Human COX-2 sequence (first 200 residues for demo - full sequence ~604 aa)
      sequence: 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTSGKMGPGFTKALGHGVDLGHIYGDNLERQYQLRLFKDGKLKYQVLDGEMYPPSVEEAPVLMHYPRGIPPQSQMAVGQEVFGLLPGLMLYATIWLREHNRVCDLLKAEHPTWGDEQLFQTT',
    },
    referenceSMILES: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
    referenceQED: 0.55, // Ibuprofen QED from RDKit (MW=206, LogP=3.5, good druglikeness)
    llmPrompt: `Design a small-molecule therapeutic that selectively inhibits cyclooxygenase enzymes responsible for converting arachidonic acid into pro-inflammatory prostaglandins. The compound should reduce peripheral and central sensitization to nociceptive stimuli, suppress inflammation-associated vasodilation and edema, and lower hypothalamic temperature set-points responsible for fever. The agent must act reversibly, demonstrate dose-dependent efficacy, and preserve normal cellular signaling pathways not involved in inflammatory mediator synthesis.

Target: COX-2 (Prostaglandin-endoperoxide synthase 2)
Desired outcome: Reduce pain, inflammation, and fever
Reference compound class: NSAIDs (non-steroidal anti-inflammatory drugs)`,
  },
  {
    id: 'amoxicillin',
    name: 'Amoxicillin',
    icon: '🦠',
    category: 'Antibacterial Agent',
    description: 'Generate candidates targeting bacterial cell wall synthesis. Goal: rediscover beta-lactam antibiotics.',
    mechanism: 'Interferes with bacterial cell wall formation by binding PBPs → bacteria cannot maintain structural integrity → osmotic lysis.',
    targetProtein: {
      name: 'PBP2a (Penicillin-binding protein 2a)',
      uniprotId: 'P0A0K4', // mecA PBP2a from S. aureus N315 - canonical, well-characterized entry
      // S. aureus PBP2a transpeptidase domain (truncated for demo)
      sequence: 'MKKIKFVLALLVAGVTGIQSAQNETSNNSNSTEKSSEKPNVVNKKESHKEKETEKPENIKTDEKTKETKKPEATKTDKTVKETKTKPEKTPEKPEKTPDKPEKTKPEKTKPEKTKEKAEKPVKTKPDKPVKTKPDKPVKTKPDKPVKTKPDKPVKTKPDKPVKTKPEKTKPDKPVKTKPEKTKE',
    },
    referenceSMILES: 'CC1(C(N2C(S1)C(C2=O)NC(=O)C(C3=CC=C(C=C3)O)N)C(=O)O)C',
    referenceQED: 0.60, // Amoxicillin QED from RDKit (MW=365, beta-lactam antibiotic)
    llmPrompt: `Develop a bactericidal compound effective against methicillin-resistant Staphylococcus aureus (MRSA). The compound should bind and inhibit PBP2a (penicillin-binding protein 2a), the mecA-encoded transpeptidase that confers beta-lactam resistance. By targeting PBP2a's active site, the compound should block peptidoglycan cross-linking and cause bacterial cell lysis.

Target: PBP2a from Staphylococcus aureus (UniProt: P0A0K4)
Desired outcome: Kill MRSA by inhibiting cell wall synthesis
Reference compound class: Beta-lactam antibiotics`,
  },
  {
    id: 'metformin',
    name: 'Metformin',
    icon: '🧬',
    category: 'Metabolic Regulation Agent',
    description: 'Design metabolic modulators for glucose control. Goal: rediscover biguanide-class compounds.',
    mechanism: 'Decreases hepatic glucose production, increases insulin sensitivity, slows intestinal glucose absorption → lowers blood sugar without increasing insulin.',
    targetProtein: {
      name: 'AMPK (AMP-activated protein kinase)',
      uniprotId: 'Q13131',
      // Human AMPK alpha-1 catalytic subunit (truncated for demo)
      sequence: 'MAEKQKHDGRVKIGHYILGDTLGVGTFGKVKVGKHELTGHKVAVKILNRQKIRSLDVVGKIRREIQNLKLFRHPHIIKLYQVISTPSDIFMVMEYVSGGELFERIIDCDFRFYMSNTGYLNVVMEYVPGGEMFSHLRRIGRFSEPHARFYAAQIVLTFEYLHSLDLIYRDLKPENLLIDQQGYIQVTDFGFAKRVKGRTWTLCGTPEYLAPEIILSKGYNKAVDWWALGVLIYEMAAGYPPFFADQPIQIYEKIVSGKVRFPSHFSSDLKDLLRNLLQVDLTKRFGNLKDFGVFNHTPDGKEVQKIIRQYQLDATGHNYPISNRLQELLVPK',
    },
    referenceSMILES: 'CN(C)C(=N)NC(=N)N',
    referenceQED: 0.47, // Metformin QED from RDKit (MW=129, small biguanide, lower due to multiple guanidine groups)
    llmPrompt: `Create a metabolic modulator that lowers systemic glucose concentrations by suppressing hepatic gluconeogenesis, enhancing peripheral insulin sensitivity, and reducing intestinal glucose uptake. The compound should activate AMP-activated protein kinase (AMPK), the master regulator of cellular energy homeostasis, without directly stimulating insulin secretion.

Target: AMPK alpha-1 catalytic subunit (UniProt: Q13131)
Desired outcome: Lower blood glucose without increasing insulin secretion
Reference compound class: Biguanides`,
  },
  {
    id: 'custom',
    name: 'Custom Discovery',
    icon: '🔬',
    category: 'Custom Research',
    description: 'Enter your own drug discovery prompt. The AI will identify the target protein and guide the discovery process.',
    mechanism: 'Define your own therapeutic goal and target.',
    isCustom: true,
    targetProtein: {
      name: 'To be identified by AI',
      uniprotId: '',
      sequence: '',
    },
    referenceSMILES: '',
    llmPrompt: '', // Will be set by user
  },
];

export const getReferenceDrugBySmiles = (smiles: string): DrugTarget | undefined => {
  return DRUG_TARGETS.find((d) => d.referenceSMILES === smiles);
};

export const getDrugById = (id: string): DrugTarget | undefined => {
  return DRUG_TARGETS.find((d) => d.id === id);
};
