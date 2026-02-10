// Target drugs for rediscovery workflow

import type { WorkflowType } from '../types/workflow';

export interface DrugTarget {
  id: string;
  name: string;
  icon: string;
  category: string;
  description: string;
  mechanism: string;
  workflowType: WorkflowType; // Determines which steps to show in step-based mode
  isCustom?: boolean; // For the custom prompt option
  targetProtein: {
    name: string;
    uniprotId: string;
    sequence: string; // Kept as fallback, will be fetched from UniProt
    oligomericState?: 'monomer' | 'homodimer' | 'homotrimer' | 'homotetramer'; // For structure prediction
  };
  referenceSMILES: string;
  referenceQED?: number; // Pre-computed QED score for the reference drug (from RDKit/literature)
  llmPrompt: string;
  caveats?: string[]; // Scientific caveats/limitations for this target (displayed as warnings)
}

export const DRUG_TARGETS: DrugTarget[] = [
  {
    id: 'imatinib',
    name: 'Imatinib',
    icon: 'target',
    category: 'Tyrosine Kinase Inhibitor',
    description: 'Design molecules targeting BCR-ABL kinase for cancer treatment. Goal: rediscover imatinib-like compounds.',
    mechanism: 'Competitively inhibits the ATP-binding site of BCR-ABL tyrosine kinase → blocks aberrant signaling → induces apoptosis in leukemic cells.',
    workflowType: 'small-molecule',
    targetProtein: {
      name: 'ABL1 (Abelson tyrosine-protein kinase 1)',
      uniprotId: 'P00519',
      // Human ABL1 kinase domain (residues 229-500, the therapeutically relevant region)
      sequence: 'ITMKHKLGGGQYGEVYEGVWKKYSLTVAVKTLKEDTMEVEEFLKEAAVMKEIKHPNLVQLLGVCTREPPFYIITEFMTYGNLLDYLRECNRQEVNAVVLLYMATQISSAMEYLEKKNFIHRDLAARNCLVGENHLVKVADFGLSRLMTGDTYTAHAGAKFPIKWTAPESLAYNKFSIKSDVWAFGVLLWEIATYGMSPYPGIDLSQVYELLEKDYRMERPEGCPEKVYELMRACWQWNPSDRPSFAEIHQAFETMFQESSISDEVEKELGKQGVRGAVSTLLQAPELPTKTRTSRRAAEHRDTTDVPEMPHSKGQGESDPLDHEPAVSPLLPRKERGPPEGGLNEDERLLPKDKKTNLFSALIKKKKKTAPTPPKRSSSFREMDGQPERRGAGEEEGRDISNGALAFTPLDTADPAKSPKPSNGAGVPNGALRESGGSGFRSPHLWKKSSTLTSSRLATGEEEGGGSSSKRFLRSCSASCVPHGAKDTEWRSVTLPRDLQSTGRQFDSSTFGGHKSEKPALPRKRAGENRSDQVTRGTVTPPPRLVKKNEEAADEVFKDIMESSPGSSPPNLTPKPLRRQVTVAPASGLPHKEEAGKGSALGTPAAAEPVTPTSKAGSGAPGGTSKGPAEESRVRRHKHSSESPGRDKGKLSRLKPAPPPPPAASAGKAGGKPSQSPSQEAAGEAVLGAKTKATSLVDAVNSDAAKPSQPGEGLKKPVLPATPKPQSAKPSGTPISPAPVPSTLPSASSALAGDQPSSTAFIPLISTRVSLRKTRQPPERIASGAITKGVVLDSTEALCLAISRNSEQMASHSAVLEAGKNLYTFCVSYVDSIQQMRNKFAFREAINKLENNLRELQICPATAGSGPAATQDFSKLLSSVKEISDIVQR',
    },
    referenceSMILES: 'Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(CC5)C',
    referenceQED: 0.77, // Imatinib QED from RDKit (MW=493, good druglikeness for kinase inhibitor)
    llmPrompt: `Design a small-molecule therapeutic that selectively inhibits the BCR-ABL fusion tyrosine kinase, which drives chronic myeloid leukemia (CML). The compound should competitively bind the ATP-binding pocket of the kinase domain, blocking phosphorylation of downstream substrates and disrupting aberrant proliferative signaling. The agent should be orally bioavailable, selective against wild-type ABL1 and the BCR-ABL fusion, and induce apoptosis in Philadelphia chromosome-positive leukemic cells.

Target: BCR-ABL / ABL1 tyrosine kinase (UniProt: P00519)
Desired outcome: Inhibit leukemic cell proliferation in CML
Reference compound class: Tyrosine kinase inhibitors (TKIs)`,
  },
  {
    id: 'ibuprofen',
    name: 'Ibuprofen',
    icon: 'pill',
    category: 'Analgesic / Anti-inflammatory',
    description: 'Design molecules targeting COX-2 enzyme for anti-inflammatory effects. Goal: rediscover ibuprofen-like compounds.',
    mechanism: 'Blocks COX-1 and COX-2 enzymes → reduces prostaglandins → lowers pain, inflammation, and fever.',
    workflowType: 'small-molecule',
    targetProtein: {
      name: 'COX-2 (Cyclooxygenase-2)',
      uniprotId: 'P35354',
      // Human COX-2 sequence (first 200 residues for demo - full sequence ~604 aa)
      sequence: 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTSGKMGPGFTKALGHGVDLGHIYGDNLERQYQLRLFKDGKLKYQVLDGEMYPPSVEEAPVLMHYPRGIPPQSQMAVGQEVFGLLPGLMLYATIWLREHNRVCDLLKAEHPTWGDEQLFQTT',
      oligomericState: 'homodimer', // COX-2 functions as an obligate homodimer
    },
    referenceSMILES: 'CC(C)Cc1ccc(cc1)C(C)C(=O)O',
    referenceQED: 0.55, // Ibuprofen QED from RDKit (MW=206, LogP=3.5, good druglikeness)
    // Scientific caveats for this target
    caveats: [
      'COX-2 is an obligate homodimer with functionally asymmetric subunits (heterodimer behavior). This demo shows only a single subunit.',
      'The catalytic subunit of COX-2 is always heme-bound in vivo. Structure prediction and docking without the heme cofactor is a simplified demonstration.',
    ],
    llmPrompt: `Design a small-molecule therapeutic that selectively inhibits cyclooxygenase enzymes responsible for converting arachidonic acid into pro-inflammatory prostaglandins. The compound should reduce peripheral and central sensitization to nociceptive stimuli, suppress inflammation-associated vasodilation and edema, and lower hypothalamic temperature set-points responsible for fever. The agent must act reversibly, demonstrate dose-dependent efficacy, and preserve normal cellular signaling pathways not involved in inflammatory mediator synthesis.

Target: COX-2 (Prostaglandin-endoperoxide synthase 2)
Desired outcome: Reduce pain, inflammation, and fever
Reference compound class: NSAIDs (non-steroidal anti-inflammatory drugs)`,
  },
  {
    id: 'amoxicillin',
    name: 'Amoxicillin',
    icon: 'bacteria',
    category: 'Antibacterial Agent',
    description: 'Generate candidates targeting bacterial cell wall synthesis. Goal: rediscover beta-lactam antibiotics.',
    mechanism: 'Interferes with bacterial cell wall formation by binding PBPs → bacteria cannot maintain structural integrity → osmotic lysis.',
    workflowType: 'small-molecule',
    targetProtein: {
      name: 'PBP2a (Penicillin-binding protein 2a)',
      uniprotId: 'Q53707', // mecA PBP2a from S. aureus - penicillin binding protein 2'
      // S. aureus PBP2a transpeptidase domain (residues 327-668, truncated for demo)
      sequence: 'NYPLEKATSHLLGYVGPINSEELKQKEYKGYKDDAVIGKKGLEKLYDKKLQHEDGYRVTIVDDNSNTIAHTLIEKKKKDGKDIQLTIDAKVQKSIYNNMKNDYGSGTAIHPQTGELLALVSTPSYDVYPFMYGMSNEEYNKLTEDKKEPLLNKFQITTSPGSTQKILTAMIGLNNKTLDDKTSYKIDGKGWQKDKSWGGYNVTRYEVVNGNIDLKQAIESSDNIFFARVALELGSKKFEKGMKKLGVGEDIPSDYPFYNAQISNKNLDNEILLADSGYGQGEILINPVQILSIYSALENNGNINAPHLLKDTKNKVWKKNIISKENINLLNDGMQQVVNKTHKEDIYRSYANLIGKSGTAELKMKQGESGRQIGWFISYDKDNPNMMMAINVKDVQDKGMASYNAKISGKVYDELYENGNKKYDIDE',
    },
    referenceSMILES: 'CC1(C(N2C(S1)C(C2=O)NC(=O)C(C3=CC=C(C=C3)O)N)C(=O)O)C',
    referenceQED: 0.60, // Amoxicillin QED from RDKit (MW=365, beta-lactam antibiotic)
    llmPrompt: `Develop a bactericidal compound effective against methicillin-resistant Staphylococcus aureus (MRSA). The compound should bind and inhibit PBP2a (penicillin-binding protein 2a), the mecA-encoded transpeptidase that confers beta-lactam resistance. By targeting PBP2a's active site, the compound should block peptidoglycan cross-linking and cause bacterial cell lysis.

Target: PBP2a from Staphylococcus aureus (UniProt: Q53707)
Desired outcome: Kill MRSA by inhibiting cell wall synthesis
Reference compound class: Beta-lactam antibiotics`,
  },
  {
    id: 'metformin',
    name: 'Metformin',
    icon: 'dna',
    category: 'Metabolic Regulation Agent',
    description: 'Design metabolic modulators for glucose control. Goal: rediscover biguanide-class compounds.',
    mechanism: 'Decreases hepatic glucose production, increases insulin sensitivity, slows intestinal glucose absorption → lowers blood sugar without increasing insulin.',
    workflowType: 'small-molecule',
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
  // ============ ANTIVIRAL DISCOVERY ============
  {
    id: 'sars-cov2-mpro',
    name: 'COVID-19 Mpro Inhibitor',
    icon: 'virus',
    category: 'Antiviral Agent',
    description: 'Design inhibitors of SARS-CoV-2 main protease (Mpro). Goal: discover novel antiviral candidates.',
    mechanism: 'Inhibits Mpro, the essential viral protease that cleaves polyproteins → blocks viral replication → prevents infection spread.',
    workflowType: 'small-molecule',
    targetProtein: {
      name: 'SARS-CoV-2 Main Protease (Mpro/3CLpro)',
      uniprotId: 'P0DTD1', // Replicase polyprotein 1ab, Mpro is nsp5
      // SARS-CoV-2 Mpro (3CLpro) - 306 residues, well-characterized drug target
      sequence: 'SGFRKMAFPSGKVEGCMVQVTCGTTTLNGLWLDDVVYCPRHVICTSEDMLNPNYEDLLIRKSNHNFLVQAGNVQLRVIGHSMQNCVLKLKVDTANPKTPKYKFVRIQPGQTFSVLACYNGSPSGVYQCAMRPNFTIKGSFLNGSCGSVGFNIDYDCVSFCYMHHMELPTGVHAGTDLEGNFYGPFVDRQTAQAAGTDTTITVNVLAWLYAAVINGDRWFLNRFTTTLNDFNLVAMKYNYEPLTQDHVDILGPLSAQTGIAVLDMCASLKELLQNGMNGRTILGSALLEDEFTPFDVVRQCSGVTFQ',
    },
    referenceSMILES: 'CC1(C2C1C(N(C2)C(=O)C(C(C)(C)C)NC(=O)C(F)(F)F)C(=O)NC(CC3CCNC3=O)C#N)C', // Nirmatrelvir (PubChem CID 155903259)
    referenceQED: 0.65,
    llmPrompt: `Design a small-molecule inhibitor of SARS-CoV-2 main protease (Mpro/3CLpro), the essential cysteine protease that cleaves viral polyproteins pp1a and pp1ab at multiple sites. The compound should covalently or non-covalently target the catalytic dyad (Cys145-His41) in the active site, blocking proteolytic processing and halting viral replication.

Target: SARS-CoV-2 Mpro (3C-like protease, nsp5)
UniProt: P0DTD1 (polyprotein 1ab, positions 3264-3569)
Desired outcome: Block viral replication by inhibiting essential protease
Reference compound class: Peptidomimetic protease inhibitors (e.g., Nirmatrelvir)`,
  },

  // ============ PROTEIN BINDER DESIGN ============
  {
    id: 'spike-binder',
    name: 'Spike Protein Binder',
    icon: 'link',
    category: 'Protein Binder Design',
    description: 'Design a mini-protein that binds SARS-CoV-2 spike RBD. Alternative to antibody therapeutics.',
    mechanism: 'Designed protein binds spike RBD → blocks ACE2 interaction → prevents viral entry into host cells.',
    workflowType: 'protein-binder',
    targetProtein: {
      name: 'SARS-CoV-2 Spike RBD',
      uniprotId: 'P0DTC2', // Spike glycoprotein
      // Spike RBD region (residues 319-541)
      sequence: 'RVQPTESIVRFPNITNLCPFGEVFNATRFASVYAWNRKRISNCVADYSVLYNSASFSTFKCYGVSPTKLNDLCFTNVYADSFVIRGDEVRQIAPGQTGKIADYNYKLPDDFTGCVIAWNSNNLDSKVGGNYNYLYRLFRKSNLKPFERDISTEIYQAGSTPCNGVEGFNCYFPLQSYGFQPTNGVGYQPYRVVVLSFELLHAPATVCGPKKSTNLVKNKCVNF',
    },
    referenceSMILES: '', // No small molecule - this is a protein design task
    llmPrompt: `Design a de novo mini-protein (60-80 residues) that binds with high affinity to the SARS-CoV-2 spike protein receptor binding domain (RBD). The binder should competitively block the spike-ACE2 interaction, preventing viral entry.

This is a PROTEIN BINDER DESIGN task - use RFDiffusion in binder mode to generate the backbone structure, then ProteinMPNN to design the sequence.

Target: SARS-CoV-2 Spike RBD (UniProt: P0DTC2, residues 319-541)
Desired outcome: Design a protein therapeutic that neutralizes SARS-CoV-2
Workflow: predict_structure (target) → design_protein (binder mode) → design_sequence → predict_structure (validation)`,
  },

  // ============ DE NOVO PROTEIN DESIGN ============
  {
    id: 'novel-scaffold',
    name: 'De Novo Protein Scaffold',
    icon: 'cube',
    category: 'De Novo Protein Design',
    description: 'Design a completely new protein fold from scratch. Create novel structures not found in nature.',
    mechanism: 'RFDiffusion generates novel backbone → ProteinMPNN designs sequence → structure validation confirms foldability.',
    workflowType: 'de-novo-protein',
    targetProtein: {
      name: 'Novel Design (no natural target)',
      uniprotId: '', // No UniProt ID - this is de novo design
      sequence: '', // Will be designed
    },
    referenceSMILES: '', // No small molecule
    llmPrompt: `Design a novel protein scaffold (~100 residues) with a stable, compact fold. The protein should have:
- Good predicted structure quality (high pLDDT)
- No homology to existing natural proteins
- Potential for future functionalization (e.g., loop grafting, binding site engineering)

This is a DE NOVO PROTEIN DESIGN task - use RFDiffusion in unconditional mode to generate a novel backbone, then ProteinMPNN to design a sequence that will fold into that structure.

Desired outcome: Create a novel protein fold with good predicted stability
Workflow: design_protein (unconditional) → design_sequence → predict_structure (validation)`,
  },

  // ============ ENZYME ENGINEERING ============
  {
    id: 'lipase-engineering',
    name: 'Lipase Engineering',
    icon: 'flask',
    category: 'Enzyme Engineering',
    description: 'Redesign Candida antarctica lipase B for improved substrate scope or thermostability.',
    mechanism: 'Structure prediction reveals active site → partial redesign preserves catalytic triad → new sequences may have improved properties.',
    workflowType: 'enzyme-engineering',
    targetProtein: {
      name: 'Lipase B (Candida antarctica)',
      uniprotId: 'P41365',
      // CALB (Candida antarctica lipase B) - industrially important enzyme
      sequence: 'LPSGSDPAFSQPKSVLDAGLTCQGASPSSVSKPILLVPGTGTTGPQSFDSNWIPLSTQLGYTPCWISPPPFMLNDTQVNTEYMVNAITALYSGDGSNLNVQGASVSTPNFGIVWHDPSSATTLPQGMVAQSYADLCTRQVTVSLDRSVRSSLSIPFTTSGYFSKTGTPRNTSMSLVVNALKDVADKYGTLSGSNGNLCPNDVVSLIGGLPGLTMFGALDNVGGSVATMVQTQSGFLVFSSSNSSKGSFIQTCPAGTTGGSPVLGLCLGHYVSPEGAPDSSGGFHVQVLANSYKMTQGLCTLFSWTSSGLSSFKSSTRLCTNSSLPNGGLFTD',
    },
    referenceSMILES: '', // No small molecule - enzyme engineering
    llmPrompt: `Analyze and potentially redesign Candida antarctica lipase B (CALB) for industrial biocatalysis applications. The goal is to understand the enzyme structure and identify regions that could be modified to improve:
- Thermostability for industrial processes
- Substrate scope for larger or different substrates
- Activity in non-aqueous solvents

This is an ENZYME ENGINEERING task. First predict the structure, then analyze the active site and potential modification sites.

Target: CALB lipase (UniProt: P41365)
Desired outcome: Identify engineering targets or design improved variants
Workflow: search_uniprot → predict_structure → analysis → potentially design_protein (partial diffusion) → design_sequence`,
  },

  // ============ PPI MODULATOR ============
  {
    id: 'mdm2-inhibitor',
    name: 'p53-MDM2 Inhibitor',
    icon: 'protein',
    category: 'PPI Modulator',
    description: 'Design inhibitors of the p53-MDM2 interaction to reactivate tumor suppression in cancer.',
    mechanism: 'Small molecule binds MDM2 pocket → disrupts p53-MDM2 interaction → restores p53 tumor suppressor function → induces cancer cell apoptosis.',
    workflowType: 'small-molecule',
    targetProtein: {
      name: 'MDM2 (Mouse double minute 2 homolog)',
      uniprotId: 'Q00987',
      // Human MDM2 N-terminal domain (p53 binding region, residues 1-125)
      sequence: 'MCNTNMSVPTDGAVTTSQIPASEQETLVRPKPLLLKLLKSVGAQKDTYTMKEVLFYLGQYIMTKRLYDEKQQHIVYCSNDLLGDLFGVPSFSVKEHRKIYTMIYRNLVVVNQQESSDSGTSVSENRCHLEGGSDQKDLVQELQEEKPSSSHLVSRPSTSSRRRAISETEENSDELSGERQRKRHKSDSISLSFDESLALCVIREICCERSSSSESTGTPSNPDLDAGVSEHSGDWLDQDSVSDQFSVEFEVESLDSEDYSLSEEGQELSDEDDEVYQVTVYQAGESDTDSFEEDPEISLADYWKCTSCNEMNPPLPSHCNRCWALRENWLPEDKGKDKGEISEKAKLENSTQAEEGFDVPDCKKTIVNDSRESCVEENDDKITQASQSQESEDYSQPSTSSSIIYSSQEDVKEFEREETQDKEESVESSLPLNAIEPCVICQGRPKNGCIVHGKTGHLMACFTCAKKLKKRNKPCPVCRQPIQMIVLTYFP',
    },
    referenceSMILES: 'CC(C)OC1=C(C=CC(=C1)OC)C2=NC(C(N2C(=O)N3CCNC(=O)C3)C4=CC=C(C=C4)Cl)C5=CC=C(C=C5)Cl', // Nutlin-3a (PubChem)
    referenceQED: 0.72,
    llmPrompt: `Design a small-molecule inhibitor that disrupts the protein-protein interaction (PPI) between p53 and MDM2. MDM2 binds and ubiquitinates p53, targeting it for degradation. In many cancers, MDM2 is overexpressed, suppressing p53 tumor suppressor activity.

The compound should bind the p53-binding pocket of MDM2, mimicking key p53 residues (Phe19, Trp23, Leu26) that are critical for the interaction.

Target: MDM2 N-terminal domain (UniProt: Q00987)
Desired outcome: Reactivate p53 by blocking MDM2-mediated degradation
Reference compound class: Nutlins, Idasanutlin, AMG 232`,
    caveats: [
      'The p53-MDM2 interface is relatively flat and hydrophobic, making it a challenging drug target.',
      'PPI modulators often have high molecular weight and may face bioavailability challenges.',
    ],
  },

  // ============ GPCR DRUG DISCOVERY ============
  {
    id: 'dopamine-d2',
    name: 'Dopamine D2 Modulator',
    icon: 'brain',
    category: 'GPCR Modulator',
    description: 'Design compounds targeting dopamine D2 receptor for neuropsychiatric conditions.',
    mechanism: 'Modulates D2 receptor signaling → affects dopaminergic neurotransmission → therapeutic effects in schizophrenia, Parkinson\'s, or addiction.',
    workflowType: 'small-molecule',
    targetProtein: {
      name: 'Dopamine D2 Receptor',
      uniprotId: 'P14416',
      // Human D2 receptor (truncated, transmembrane regions)
      sequence: 'MDPLNLSWYDDDLERQNWSRPFNGSEGKADRPHYNYYAMLLTLLIFVIVFGNVLVCMAVSREKALQTTTNYLIVSLAVADLLVATLVMPWVVYLEVVGEWKFSRIHCDIFVTLDVMMCTASILNLCAISIDRYTAVAMPMLYNTRYSSKRRVTVMISIVWVLSFTISCPLLFGLNNADQNECIIANPAFVVYSSIVSFYVPFIVTLLVYIKIYIVLRRRRKRVNTKRSSRAFRAHLRAPLKGNCTHPEDMKLCTVIMKSNGSFPVNRRRVEAARRAQELEMEMLSSTSPPERTRYSPIPPSHHQLTLPDPSHHGLHSTPDSPAKPEKNGHAKDHPKIAKIFEIQTMPNGKTRTSLKTMSRRKLSQQKEKKATQMLAIVLGVFIICWLPFFITHILNIHCDCNIPPVLYSAFTWLGYVNSAVNPIIYTTFNIEFRKAFLKILHC',
    },
    referenceSMILES: 'C1CC(=O)NC2=C1C=CC(=C2)OCCCCN3CCN(CC3)C4=C(C(=CC=C4)Cl)Cl', // Aripiprazole (PubChem)
    referenceQED: 0.58,
    llmPrompt: `Design a dopamine D2 receptor modulator for treatment of neuropsychiatric conditions. The compound could act as:
- A partial agonist (like aripiprazole) for schizophrenia treatment
- An antagonist for antipsychotic effects
- An agonist for Parkinson's disease symptom relief

The compound should demonstrate selectivity for D2 over other dopamine receptor subtypes and have good CNS penetration.

Target: Dopamine D2 receptor (UniProt: P14416)
Desired outcome: Modulate dopaminergic signaling in the brain
Reference compound class: Atypical antipsychotics, dopamine agonists`,
    caveats: [
      'GPCRs are membrane proteins - structure prediction may have lower accuracy for transmembrane regions.',
      'Receptor conformational dynamics (active vs inactive states) significantly affect ligand binding - static structures are approximations.',
    ],
  },

  // ============ CUSTOM OPTION (keep last) ============
  {
    id: 'custom',
    name: 'Custom Discovery',
    icon: 'microscope',
    category: 'Custom Research',
    description: 'Enter your own drug discovery prompt. The AI will identify the target protein and guide the discovery process.',
    mechanism: 'Define your own therapeutic goal and target.',
    workflowType: 'small-molecule', // Default workflow for custom, agent mode can adapt
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

/**
 * Convert oligomeric state to number of chain copies for structure prediction
 */
export const getNumCopiesFromOligomericState = (
  state: 'monomer' | 'homodimer' | 'homotrimer' | 'homotetramer' | undefined
): number => {
  switch (state) {
    case 'homodimer':
      return 2;
    case 'homotrimer':
      return 3;
    case 'homotetramer':
      return 4;
    case 'monomer':
    default:
      return 1;
  }
};
