// P35354 full sequence (includes signal peptide 1-17)
const P35354_FULL = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

// P35354 mature protein (without signal peptide, residues 18-604)
// The signal peptide is MLARALLLCAVLALSHT (residues 1-17)
const P35354_MATURE = P35354_FULL.substring(17);

const gatewayUrl = '185.82.69.28';

async function testOpenFold3(sequence, label, diffusionSamples) {
  console.log('\n=== Testing OpenFold3: ' + label + ' (diffusion_samples=' + diffusionSamples + ') ===');
  console.log('Sequence length: ' + sequence.length);

  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';
  const csvMsa = 'key,sequence\n-1,' + sequence;

  const body = {
    inputs: [{
      input_id: 'test',
      molecules: [{
        type: 'protein',
        id: 'A',
        sequence: sequence,
        msa: {
          main_db: {
            csv: {
              alignment: csvMsa,
              format: 'csv',
            },
          },
        },
      }],
      diffusion_samples: diffusionSamples,
      output_format: 'cif',
    }],
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
      console.log('Failed: ' + response.status + ' - ' + (await response.text()).substring(0, 500));
      return null;
    }

    const data = await response.json();
    const structures = data.outputs?.[0]?.structures_with_scores || [];

    console.log('Got ' + structures.length + ' structures:');
    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Sample ' + (i+1) + ': Confidence=' + (s.confidence_score * 100).toFixed(1) + '% pLDDT=' + s.complex_plddt_score?.toFixed(1) + ' pTM=' + s.ptm_score?.toFixed(3));
    }
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');

    return structures;
  } catch (e) {
    console.log('Error: ' + e.message);
    return null;
  }
}

async function testBoltz2(sequence, label) {
  console.log('\n=== Testing Boltz2: ' + label + ' ===');
  console.log('Sequence length: ' + sequence.length);

  const url = 'http://' + gatewayUrl + ':8001/biology/mit/boltz2/predict';
  const body = {
    polymers: [{
      molecule_type: 'protein',
      sequence: sequence,
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
    console.log('Boltz2: Confidence=' + ((data.confidence_scores?.[0] || 0) * 100).toFixed(1) + '% pLDDT=' + ((data.complex_plddt_scores?.[0] || 0) * 100).toFixed(1) + ' pTM=' + (data.ptm_scores?.[0] || 0).toFixed(3));
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function main() {
  console.log('P35354 (COX-2) Testing');
  console.log('Full sequence: ' + P35354_FULL.length + ' residues');
  console.log('Mature protein (no signal peptide): ' + P35354_MATURE.length + ' residues');

  // Test Boltz2 with full and mature
  await testBoltz2(P35354_FULL, 'Full (with signal peptide)');
  await testBoltz2(P35354_MATURE, 'Mature (no signal peptide)');

  // Test OpenFold3 with different diffusion samples
  await testOpenFold3(P35354_FULL, 'Full sequence', 1);
  await testOpenFold3(P35354_FULL, 'Full sequence', 5);

  // Test with mature protein
  await testOpenFold3(P35354_MATURE, 'Mature (no signal peptide)', 1);
  await testOpenFold3(P35354_MATURE, 'Mature (no signal peptide)', 5);
}

main().catch(console.error);
