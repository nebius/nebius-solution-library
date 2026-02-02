const P35354_SEQUENCE = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

const gatewayUrl = '185.82.69.28';

// Test a shorter sequence first to see if length is an issue
const SHORT_SEQ = P35354_SEQUENCE.substring(0, 200);

async function testBoltz2(sequence, label) {
  console.log('\n=== Testing Boltz2: ' + label + ' ===');
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
      console.log('Boltz2 failed: ' + response.status + ' - ' + await response.text());
      return;
    }

    const data = await response.json();
    console.log('Boltz2 Results:');
    console.log('  Confidence: ' + ((data.confidence_scores?.[0] || 0) * 100).toFixed(1) + '%');
    console.log('  pLDDT: ' + ((data.complex_plddt_scores?.[0] || 0) * 100).toFixed(1));
    console.log('  pTM: ' + (data.ptm_scores?.[0] || 0).toFixed(3));
    console.log('  Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Boltz2 error: ' + e.message);
  }
}

async function testOpenFold3Minimal(sequence, label) {
  console.log('\n=== Testing OpenFold3 (minimal request): ' + label + ' ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  // Try the absolute minimal request format
  const body = {
    inputs: [{
      input_id: 'test',
      molecules: [{
        type: 'protein',
        id: 'A',
        sequence: sequence,
      }],
      output_format: 'cif',
    }],
  };

  console.log('Request (no MSA at all):');
  console.log(JSON.stringify(body, null, 2).substring(0, 400));

  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const elapsed = Date.now() - startTime;

    if (!response.ok) {
      const errorText = await response.text();
      console.log('OpenFold3 failed: ' + response.status);
      console.log('Error: ' + errorText.substring(0, 500));
      return;
    }

    const data = await response.json();
    const result = data.outputs?.[0]?.structures_with_scores?.[0];
    if (result) {
      console.log('OpenFold3 Results:');
      console.log('  Confidence: ' + (result.confidence_score * 100).toFixed(1) + '%');
      console.log('  pLDDT: ' + result.complex_plddt_score?.toFixed(1));
      console.log('  pTM: ' + result.ptm_score?.toFixed(3));
      console.log('  Time: ' + (elapsed / 1000).toFixed(1) + 's');
    }
  } catch (e) {
    console.log('OpenFold3 error: ' + e.message);
  }
}

async function testOpenFold3WithSimpleMsa(sequence, label) {
  console.log('\n=== Testing OpenFold3 (simple MSA): ' + label + ' ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  // Simple single-sequence MSA
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
      const errorText = await response.text();
      console.log('OpenFold3 failed: ' + response.status);
      console.log('Error: ' + errorText.substring(0, 500));
      return;
    }

    const data = await response.json();
    const result = data.outputs?.[0]?.structures_with_scores?.[0];
    if (result) {
      console.log('OpenFold3 Results:');
      console.log('  Confidence: ' + (result.confidence_score * 100).toFixed(1) + '%');
      console.log('  pLDDT: ' + result.complex_plddt_score?.toFixed(1));
      console.log('  pTM: ' + result.ptm_score?.toFixed(3));
      console.log('  Time: ' + (elapsed / 1000).toFixed(1) + 's');
    }
  } catch (e) {
    console.log('OpenFold3 error: ' + e.message);
  }
}

async function main() {
  console.log('Testing with sequence length: ' + P35354_SEQUENCE.length);

  // Test Boltz2 first (known to work well)
  await testBoltz2(P35354_SEQUENCE, 'Full P35354');

  // Test OpenFold3 without any MSA
  await testOpenFold3Minimal(P35354_SEQUENCE, 'Full P35354');

  // Test OpenFold3 with simple single-sequence MSA
  await testOpenFold3WithSimpleMsa(P35354_SEQUENCE, 'Full P35354');
}

main().catch(console.error);
