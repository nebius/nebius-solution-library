const P35354_SEQUENCE = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

const gatewayUrl = '185.82.69.28';

async function testOpenFold3NewFormat() {
  console.log('=== Testing OpenFold3 with NEW format (a3m, main db) ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  const query_only_a3m = '>query\n' + P35354_SEQUENCE;

  const payload = {
    request_id: 'P35354_query_only_msa',
    inputs: [{
      input_id: 'P35354',
      molecules: [{
        type: 'protein',
        id: 'A',
        sequence: P35354_SEQUENCE,
        msa: {
          main: {
            a3m: {
              alignment: query_only_a3m,
              format: 'a3m'
            }
          }
        }
      }],
      diffusion_samples: 1,
      output_format: 'cif'
    }]
  };

  console.log('Request format:');
  console.log('- msa.main.a3m (not main_db.csv)');
  console.log('- diffusion_samples: 1');
  console.log('- Sequence length:', P35354_SEQUENCE.length);

  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const elapsed = Date.now() - startTime;

    if (!response.ok) {
      const errorText = await response.text();
      console.log('Failed: ' + response.status);
      console.log('Error: ' + errorText.substring(0, 500));
      return;
    }

    const data = await response.json();
    const structures = data.outputs?.[0]?.structures_with_scores || [];

    console.log('\nResults:');
    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Sample ' + (i+1) + ': Confidence=' + (s.confidence_score * 100).toFixed(1) + '% pLDDT=' + s.complex_plddt_score?.toFixed(1) + ' pTM=' + s.ptm_score?.toFixed(3));
    }
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function testOpenFold3OldFormat() {
  console.log('\n=== Testing OpenFold3 with OLD format (csv, main_db) ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  const csvMsa = 'key,sequence\n-1,' + P35354_SEQUENCE;

  const payload = {
    inputs: [{
      input_id: 'P35354',
      molecules: [{
        type: 'protein',
        id: 'A',
        sequence: P35354_SEQUENCE,
        msa: {
          main_db: {
            csv: {
              alignment: csvMsa,
              format: 'csv'
            }
          }
        }
      }],
      output_format: 'cif'
    }]
  };

  console.log('Request format:');
  console.log('- msa.main_db.csv');
  console.log('- no diffusion_samples specified');

  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const elapsed = Date.now() - startTime;

    if (!response.ok) {
      const errorText = await response.text();
      console.log('Failed: ' + response.status);
      console.log('Error: ' + errorText.substring(0, 500));
      return;
    }

    const data = await response.json();
    const structures = data.outputs?.[0]?.structures_with_scores || [];

    console.log('\nResults:');
    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Sample ' + (i+1) + ': Confidence=' + (s.confidence_score * 100).toFixed(1) + '% pLDDT=' + s.complex_plddt_score?.toFixed(1) + ' pTM=' + s.ptm_score?.toFixed(3));
    }
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function main() {
  await testOpenFold3NewFormat();
  await testOpenFold3OldFormat();
}

main().catch(console.error);
