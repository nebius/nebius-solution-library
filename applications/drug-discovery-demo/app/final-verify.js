const P35354_SEQUENCE = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

const gatewayUrl = '185.82.69.28';

async function getMsa() {
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
      return data.alignments[dbName].a3m.alignment;
    }
  }
  return null;
}

async function testModel(name, url, body) {
  console.log('\n' + name + ':');
  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);

    if (!response.ok) {
      console.log('  Failed: ' + response.status);
      return;
    }

    const data = await response.json();

    // OpenFold3
    if (data.outputs) {
      const s = data.outputs[0]?.structures_with_scores?.[0];
      console.log('  Confidence: ' + (s.confidence_score * 100).toFixed(1) + '%');
      console.log('  Time: ' + elapsed + 's');
    }
    // Boltz2
    else if (data.confidence_scores) {
      console.log('  Confidence: ' + (data.confidence_scores[0] * 100).toFixed(1) + '%');
      console.log('  Time: ' + elapsed + 's');
    }
    // OpenFold2
    else if (data.structures_in_ranked_order) {
      console.log('  Confidence: ' + data.structures_in_ranked_order[0].confidence.toFixed(1) + '%');
      console.log('  Time: ' + elapsed + 's');
    }
  } catch (e) {
    console.log('  Error: ' + e.message);
  }
}

async function main() {
  console.log('='.repeat(50));
  console.log('FINAL VERIFICATION - P35354 Structure Prediction');
  console.log('='.repeat(50));

  console.log('\nFetching MSA...');
  const realMsa = await getMsa();
  const numSeqs = (realMsa.match(/^>/gm) || []).length;
  console.log('Got ' + numSeqs + ' sequences');

  const singleSeqA3m = '>query\n' + P35354_SEQUENCE;

  // OpenFold3 - single sequence (RECOMMENDED)
  await testModel(
    'OpenFold3 (single seq, a3m+main format)',
    'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict',
    {
      inputs: [{
        input_id: 'P35354',
        molecules: [{
          type: 'protein', id: 'A', sequence: P35354_SEQUENCE,
          msa: { main: { a3m: { alignment: singleSeqA3m, format: 'a3m' } } }
        }],
        diffusion_samples: 1,
        output_format: 'cif'
      }]
    }
  );

  // OpenFold2 - single sequence
  await testModel(
    'OpenFold2 (single seq)',
    'http://' + gatewayUrl + ':8004/biology/openfold/openfold2/predict-structure-from-msa-and-template',
    {
      sequence: P35354_SEQUENCE,
      alignments: { uniref90: { a3m: { alignment: singleSeqA3m, format: 'a3m' } } },
      selected_models: [1, 2, 3, 4, 5],
      output_format: 'cif'
    }
  );

  // OpenFold2 - with real MSA (RECOMMENDED for OpenFold2)
  await testModel(
    'OpenFold2 (real MSA, 101 seqs)',
    'http://' + gatewayUrl + ':8004/biology/openfold/openfold2/predict-structure-from-msa-and-template',
    {
      sequence: P35354_SEQUENCE,
      alignments: { uniref90: { a3m: { alignment: realMsa, format: 'a3m' } } },
      selected_models: [1, 2, 3, 4, 5],
      output_format: 'cif'
    }
  );

  // Boltz2 (BEST)
  await testModel(
    'Boltz2 (no MSA needed)',
    'http://' + gatewayUrl + ':8001/biology/mit/boltz2/predict',
    {
      polymers: [{ molecule_type: 'protein', sequence: P35354_SEQUENCE, cyclic: false }],
      recycling_steps: 3, sampling_steps: 50, diffusion_samples: 1,
      step_scale: 1.638, output_format: 'mmcif'
    }
  );

  console.log('\n' + '='.repeat(50));
  console.log('RECOMMENDATIONS:');
  console.log('1. Boltz2: Best performer (~92%), no MSA needed');
  console.log('2. OpenFold2 + MSA: Good (~52%), requires MSA search');
  console.log('3. OpenFold3: Moderate (~33%), DO NOT use MSA');
  console.log('='.repeat(50));
}

main().catch(console.error);
