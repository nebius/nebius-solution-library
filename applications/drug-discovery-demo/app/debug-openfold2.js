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

function a3mToCsv(a3m, querySequence) {
  const lines = a3m.trim().split('\n');
  const rows = ['key,sequence'];
  rows.push('-1,' + querySequence);

  let currentSeq = '';
  let isFirstSequence = true;
  let inSequence = false;

  for (const line of lines) {
    if (line.startsWith('>')) {
      if (inSequence && currentSeq && !isFirstSequence) {
        const cleanedSeq = currentSeq.replace(/[a-z]/g, '');
        rows.push('-1,' + cleanedSeq);
      }
      currentSeq = '';
      inSequence = true;
      if (isFirstSequence) {
        isFirstSequence = false;
      }
    } else if (inSequence) {
      currentSeq += line.trim();
    }
  }

  if (currentSeq && !isFirstSequence) {
    const cleanedSeq = currentSeq.replace(/[a-z]/g, '');
    rows.push('-1,' + cleanedSeq);
  }

  return rows.join('\n');
}

async function testOpenFold3WithRealMsa(a3m) {
  console.log('\n=== Testing OpenFold3 with REAL MSA (101 sequences) ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  const csvMsa = a3mToCsv(a3m, P35354_SEQUENCE);
  const csvLines = csvMsa.split('\n');
  console.log('CSV lines: ' + csvLines.length);
  console.log('First 3 lines:');
  for (let i = 0; i < Math.min(3, csvLines.length); i++) {
    console.log('  ' + csvLines[i].substring(0, 100) + '...');
  }

  const body = {
    inputs: [{
      input_id: 'test',
      molecules: [{
        type: 'protein',
        id: 'A',
        sequence: P35354_SEQUENCE,
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
      console.log('Error: ' + errorText.substring(0, 1000));
      return;
    }

    const data = await response.json();
    const result = data.outputs?.[0]?.structures_with_scores?.[0];
    if (result) {
      console.log('OpenFold3 (real MSA) Results:');
      console.log('  Confidence: ' + (result.confidence_score * 100).toFixed(1) + '%');
      console.log('  pLDDT: ' + result.complex_plddt_score?.toFixed(1));
      console.log('  pTM: ' + result.ptm_score?.toFixed(3));
      console.log('  Time: ' + (elapsed / 1000).toFixed(1) + 's');
    }
  } catch (e) {
    console.log('OpenFold3 error: ' + e.message);
  }
}

async function testOpenFold3WithA3mFormat(a3m) {
  console.log('\n=== Testing OpenFold3 with A3M format (not CSV) ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  const body = {
    inputs: [{
      input_id: 'test',
      molecules: [{
        type: 'protein',
        id: 'A',
        sequence: P35354_SEQUENCE,
        msa: {
          main_db: {
            a3m: {
              alignment: a3m,
              format: 'a3m',
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
      console.log('Error: ' + errorText.substring(0, 1000));
      return;
    }

    const data = await response.json();
    const result = data.outputs?.[0]?.structures_with_scores?.[0];
    if (result) {
      console.log('OpenFold3 (A3M format) Results:');
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
  console.log('Fetching MSA...');
  const a3m = await getMsa();
  if (!a3m) {
    console.log('Failed to get MSA');
    return;
  }
  console.log('Got MSA');

  // Test with CSV format
  await testOpenFold3WithRealMsa(a3m);

  // Test with A3M format directly (maybe OpenFold3 prefers this)
  await testOpenFold3WithA3mFormat(a3m);
}

main().catch(console.error);
