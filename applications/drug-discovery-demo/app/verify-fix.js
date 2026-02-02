// Verify the OpenFold2 fix is working
const P35354_SEQUENCE = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

const gatewayUrl = '185.82.69.28';

async function getMsa() {
  console.log('Fetching MSA from ColabFold...');
  const url = 'http://' + gatewayUrl + ':8003/biology/colabfold/msa-search/predict';
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sequence: P35354_SEQUENCE,
      databases: ['all'],
      output_alignment_formats: ['a3m'],
    }),
  });

  const data = await response.json();
  for (const dbName of Object.keys(data.alignments)) {
    if (data.alignments[dbName]?.a3m?.alignment) {
      const a3m = data.alignments[dbName].a3m.alignment;
      const numSeqs = (a3m.match(/^>/gm) || []).length;
      console.log('Got MSA with ' + numSeqs + ' sequences');
      return a3m;
    }
  }
  return null;
}

async function testOpenFold2(msa, label) {
  console.log('\n=== OpenFold2: ' + label + ' ===');
  const url = 'http://' + gatewayUrl + ':8004/biology/openfold/openfold2/predict-structure-from-msa-and-template';

  // Use the CORRECT format with 'alignments' field
  const body = {
    sequence: P35354_SEQUENCE,
    alignments: {
      uniref90: {
        a3m: {
          alignment: msa,
          format: 'a3m',
        },
      },
    },
    selected_models: [1, 2, 3, 4, 5],
    output_format: 'cif',
  };

  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const elapsed = Date.now() - startTime;

    if (!response.ok) {
      console.log('Failed: ' + response.status + ' - ' + (await response.text()).substring(0, 300));
      return;
    }

    const data = await response.json();
    const structures = data.structures_in_ranked_order || [];
    console.log('Returned ' + structures.length + ' structures');

    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Model ' + (i+1) + ': Confidence=' + s.confidence?.toFixed(1) + '%');
    }
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function testBoltz2() {
  console.log('\n=== Boltz2 (baseline) ===');
  const url = 'http://' + gatewayUrl + ':8001/biology/mit/boltz2/predict';

  const body = {
    polymers: [{
      molecule_type: 'protein',
      sequence: P35354_SEQUENCE,
      cyclic: false,
    }],
    recycling_steps: 3,
    sampling_steps: 50,
    diffusion_samples: 1,
    step_scale: 1.638,
    output_format: 'mmcif',
  };

  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const elapsed = Date.now() - startTime;

    if (!response.ok) {
      console.log('Failed: ' + response.status);
      return;
    }

    const data = await response.json();
    console.log('Confidence: ' + ((data.confidence_scores?.[0] || 0) * 100).toFixed(1) + '%');
    console.log('pLDDT: ' + ((data.complex_plddt_scores?.[0] || 0) * 100).toFixed(1));
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function main() {
  console.log('='.repeat(60));
  console.log('P35354 (COX-2) Structure Prediction Verification');
  console.log('Sequence length: ' + P35354_SEQUENCE.length + ' residues');
  console.log('='.repeat(60));

  // Get real MSA
  const realMsa = await getMsa();
  if (!realMsa) {
    console.log('Failed to get MSA');
    return;
  }

  // Test with single sequence (baseline)
  const singleSeqMsa = '>query\n' + P35354_SEQUENCE;
  await testOpenFold2(singleSeqMsa, 'Single sequence (no homologs)');

  // Test with real MSA
  await testOpenFold2(realMsa, 'Real MSA (with homologs)');

  // Boltz2 as baseline comparison
  await testBoltz2();

  console.log('\n' + '='.repeat(60));
  console.log('SUMMARY:');
  console.log('- OpenFold2 with real MSA should show ~52% confidence');
  console.log('- OpenFold2 without MSA should show ~33% confidence');
  console.log('- Boltz2 should show ~92% confidence (best performer)');
  console.log('='.repeat(60));
}

main().catch(console.error);
