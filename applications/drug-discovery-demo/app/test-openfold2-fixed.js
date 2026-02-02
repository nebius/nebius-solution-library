const P35354_SEQUENCE = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

const gatewayUrl = '185.82.69.28';

async function testOpenFold2Old() {
  console.log('\n=== Testing OpenFold2 with OLD format (msa field) ===');
  const url = 'http://' + gatewayUrl + ':8004/biology/openfold/openfold2/predict-structure-from-msa-and-template';

  const body = {
    sequence: P35354_SEQUENCE,
    msa: {
      uniref90: {
        a3m: {
          alignment: '>query\n' + P35354_SEQUENCE,
          format: 'a3m',
        },
      },
    },
    output_format: 'cif',
  };

  console.log('Request body:', JSON.stringify(body, null, 2).substring(0, 300) + '...');

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
      return;
    }

    const data = await response.json();
    const result = data.structures_in_ranked_order?.[0];
    if (result) {
      console.log('Results: Confidence=' + result.confidence?.toFixed(1) + '% Time=' + (elapsed / 1000).toFixed(1) + 's');
    }
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function testOpenFold2New() {
  console.log('\n=== Testing OpenFold2 with NEW format (alignments field) ===');
  const url = 'http://' + gatewayUrl + ':8004/biology/openfold/openfold2/predict-structure-from-msa-and-template';

  const body = {
    sequence: P35354_SEQUENCE,
    alignments: {
      uniref90: {
        a3m: {
          alignment: '>query\n' + P35354_SEQUENCE,
          format: 'a3m',
        },
      },
    },
    selected_models: [1, 2, 3, 4, 5],
    output_format: 'cif',
  };

  console.log('Request body:', JSON.stringify(body, null, 2).substring(0, 300) + '...');

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
      return;
    }

    const data = await response.json();
    console.log('Response keys:', Object.keys(data));
    const structures = data.structures_in_ranked_order || [];
    console.log('Number of structures returned:', structures.length);

    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Model ' + (i+1) + ': Confidence=' + s.confidence?.toFixed(1) + '%');
    }
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function testOpenFold2WithRealMsa() {
  console.log('\n=== Testing OpenFold2 with REAL MSA (alignments field) ===');

  // First get MSA
  console.log('Fetching MSA...');
  const msaUrl = 'http://' + gatewayUrl + ':8003/biology/colabfold/msa-search/predict';
  const msaResponse = await fetch(msaUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      sequence: P35354_SEQUENCE,
      databases: ['all'],
      output_alignment_formats: ['a3m'],
    }),
  });

  const msaData = await msaResponse.json();
  let a3m = '';
  for (const dbName of Object.keys(msaData.alignments)) {
    if (msaData.alignments[dbName]?.a3m?.alignment) {
      a3m = msaData.alignments[dbName].a3m.alignment;
      break;
    }
  }
  const numSeqs = (a3m.match(/^>/gm) || []).length;
  console.log('Got MSA with ' + numSeqs + ' sequences');

  const url = 'http://' + gatewayUrl + ':8004/biology/openfold/openfold2/predict-structure-from-msa-and-template';

  const body = {
    sequence: P35354_SEQUENCE,
    alignments: {
      uniref90: {
        a3m: {
          alignment: a3m,
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
      console.log('Failed: ' + response.status + ' - ' + (await response.text()).substring(0, 500));
      return;
    }

    const data = await response.json();
    const structures = data.structures_in_ranked_order || [];
    console.log('Number of structures returned:', structures.length);

    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Model ' + (i+1) + ': Confidence=' + s.confidence?.toFixed(1) + '%');
    }
    console.log('Time: ' + (elapsed / 1000).toFixed(1) + 's');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function main() {
  await testOpenFold2Old();
  await testOpenFold2New();
  await testOpenFold2WithRealMsa();
}

main().catch(console.error);
