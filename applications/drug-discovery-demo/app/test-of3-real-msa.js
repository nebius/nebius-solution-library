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
      console.log('Got MSA with ' + numSeqs + ' sequences\n');
      return a3m;
    }
  }
  return null;
}

async function testOpenFold3WithA3m(a3m, label) {
  console.log('=== OpenFold3: ' + label + ' (a3m format, main db) ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  const payload = {
    request_id: 'test_a3m',
    inputs: [{
      input_id: 'P35354',
      molecules: [{
        type: 'protein',
        id: 'A',
        sequence: P35354_SEQUENCE,
        msa: {
          main: {
            a3m: {
              alignment: a3m,
              format: 'a3m'
            }
          }
        }
      }],
      diffusion_samples: 1,
      output_format: 'cif'
    }]
  };

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

    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Confidence=' + (s.confidence_score * 100).toFixed(1) + '% pLDDT=' + s.complex_plddt_score?.toFixed(1) + ' pTM=' + s.ptm_score?.toFixed(3));
    }
    console.log('  Time: ' + (elapsed / 1000).toFixed(1) + 's\n');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
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

async function testOpenFold3WithCsv(a3m, label) {
  console.log('=== OpenFold3: ' + label + ' (csv format, main_db) ===');
  const url = 'http://' + gatewayUrl + ':8000/biology/openfold/openfold3/predict';

  const csvMsa = a3mToCsv(a3m, P35354_SEQUENCE);

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

    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      console.log('  Confidence=' + (s.confidence_score * 100).toFixed(1) + '% pLDDT=' + s.complex_plddt_score?.toFixed(1) + ' pTM=' + s.ptm_score?.toFixed(3));
    }
    console.log('  Time: ' + (elapsed / 1000).toFixed(1) + 's\n');
  } catch (e) {
    console.log('Error: ' + e.message);
  }
}

async function main() {
  const realMsa = await getMsa();
  if (!realMsa) {
    console.log('Failed to get MSA');
    return;
  }

  const singleSeqA3m = '>query\n' + P35354_SEQUENCE;

  // Test single sequence with both formats
  await testOpenFold3WithA3m(singleSeqA3m, 'Single sequence');
  await testOpenFold3WithCsv(singleSeqA3m, 'Single sequence');

  // Test real MSA with both formats
  await testOpenFold3WithA3m(realMsa, 'Real MSA (101 seqs)');
  await testOpenFold3WithCsv(realMsa, 'Real MSA (101 seqs)');

  console.log('='.repeat(50));
  console.log('SUMMARY:');
  console.log('Compare a3m vs csv format with real MSA data');
  console.log('='.repeat(50));
}

main().catch(console.error);
