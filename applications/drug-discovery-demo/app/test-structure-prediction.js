#!/usr/bin/env node
/**
 * Test script for structure prediction with and without MSA
 * Usage: node test-structure-prediction.js <gateway-url>
 * Example: node test-structure-prediction.js 10.0.0.1
 */

// P35354 - COX-2 (Prostaglandin G/H synthase 2) sequence
const P35354_SEQUENCE = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

async function testMsaSearch(gatewayUrl) {
  console.log('\n=== Testing MSA Search ===');
  const url = `http://${gatewayUrl}:8003/biology/colabfold/msa-search/predict`;

  const body = {
    sequence: P35354_SEQUENCE,
    databases: ['all'],
    output_alignment_formats: ['a3m'],
  };

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.log(`MSA Search failed: ${response.status} - ${errorText}`);
      return null;
    }

    const data = await response.json();

    // Extract A3M alignment
    let alignment = '';
    if (data.alignments) {
      for (const dbName of Object.keys(data.alignments)) {
        const dbData = data.alignments[dbName];
        if (dbData?.a3m?.alignment) {
          alignment = dbData.a3m.alignment;
          break;
        }
      }
    }

    const numSequences = (alignment.match(/^>/gm) || []).length;
    console.log(`MSA Search successful: ${numSequences} sequences found`);
    console.log(`First 500 chars of alignment:\n${alignment.substring(0, 500)}...`);

    return alignment;
  } catch (error) {
    console.log(`MSA Search error: ${error.message}`);
    return null;
  }
}

function a3mToCsv(a3m, querySequence) {
  const lines = a3m.trim().split('\n');
  const rows = ['key,sequence'];

  // First row is always the query sequence (must match exactly)
  rows.push(`-1,${querySequence}`);

  let currentSeq = '';
  let isFirstSequence = true;
  let inSequence = false;

  for (const line of lines) {
    if (line.startsWith('>')) {
      if (inSequence && currentSeq && !isFirstSequence) {
        const cleanedSeq = currentSeq.replace(/[a-z]/g, '');
        rows.push(`-1,${cleanedSeq}`);
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
    rows.push(`-1,${cleanedSeq}`);
  }

  return rows.join('\n');
}

async function testOpenFold3(gatewayUrl, msaA3m = null) {
  const withMsa = msaA3m !== null;
  console.log(`\n=== Testing OpenFold3 ${withMsa ? 'WITH' : 'WITHOUT'} MSA ===`);

  const url = `http://${gatewayUrl}:8000/biology/openfold/openfold3/predict`;

  let csvMsa;
  if (withMsa) {
    csvMsa = a3mToCsv(msaA3m, P35354_SEQUENCE);
    console.log(`CSV MSA (first 300 chars):\n${csvMsa.substring(0, 300)}...`);
    console.log(`CSV MSA lines: ${csvMsa.split('\n').length}`);
  } else {
    csvMsa = `key,sequence\n-1,${P35354_SEQUENCE}`;
  }

  const body = {
    inputs: [{
      input_id: 'prediction_1',
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

  console.log('Request body (truncated):', JSON.stringify(body, null, 2).substring(0, 500) + '...');

  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const elapsedTime = Date.now() - startTime;

    if (!response.ok) {
      const errorText = await response.text();
      console.log(`OpenFold3 failed: ${response.status} - ${errorText}`);
      return null;
    }

    const data = await response.json();
    const output = data.outputs?.[0];
    const result = output?.structures_with_scores?.[0];

    if (result) {
      console.log(`OpenFold3 ${withMsa ? '(WITH MSA)' : '(NO MSA)'} Results:`);
      console.log(`  - Confidence: ${(result.confidence_score * 100).toFixed(1)}%`);
      console.log(`  - pLDDT: ${result.complex_plddt_score?.toFixed(1)}`);
      console.log(`  - pTM: ${result.ptm_score?.toFixed(3)}`);
      console.log(`  - Time: ${(elapsedTime / 1000).toFixed(1)}s`);
      return result;
    } else {
      console.log('No structure returned');
      return null;
    }
  } catch (error) {
    console.log(`OpenFold3 error: ${error.message}`);
    return null;
  }
}

async function testOpenFold2(gatewayUrl, msaA3m = null) {
  const withMsa = msaA3m !== null;
  console.log(`\n=== Testing OpenFold2 ${withMsa ? 'WITH' : 'WITHOUT'} MSA ===`);

  const url = `http://${gatewayUrl}:8004/biology/openfold/openfold2/predict-structure-from-msa-and-template`;

  let a3mContent;
  if (withMsa) {
    a3mContent = msaA3m;
    const numSeqs = (a3mContent.match(/^>/gm) || []).length;
    console.log(`Using real MSA with ${numSeqs} sequences`);
  } else {
    a3mContent = `>query\n${P35354_SEQUENCE}`;
    console.log('Using single-sequence MSA (query only)');
  }

  const body = {
    sequence: P35354_SEQUENCE,
    msa: {
      uniref90: {
        a3m: {
          alignment: a3mContent,
          format: 'a3m',
        },
      },
    },
    output_format: 'cif',
  };

  try {
    const startTime = Date.now();
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const elapsedTime = Date.now() - startTime;

    if (!response.ok) {
      const errorText = await response.text();
      console.log(`OpenFold2 failed: ${response.status} - ${errorText}`);
      return null;
    }

    const data = await response.json();
    const result = data.structures_in_ranked_order?.[0];

    if (result) {
      console.log(`OpenFold2 ${withMsa ? '(WITH MSA)' : '(NO MSA)'} Results:`);
      console.log(`  - Confidence: ${result.confidence?.toFixed(1)}%`);
      console.log(`  - Time: ${(elapsedTime / 1000).toFixed(1)}s`);
      return result;
    } else {
      console.log('No structure returned');
      return null;
    }
  } catch (error) {
    console.log(`OpenFold2 error: ${error.message}`);
    return null;
  }
}

async function main() {
  const gatewayUrl = process.argv[2];

  if (!gatewayUrl) {
    console.log('Usage: node test-structure-prediction.js <gateway-url>');
    console.log('Example: node test-structure-prediction.js 10.0.0.1');
    process.exit(1);
  }

  console.log(`Testing structure prediction for P35354 (COX-2)`);
  console.log(`Gateway: ${gatewayUrl}`);
  console.log(`Sequence length: ${P35354_SEQUENCE.length} residues`);

  // Test WITHOUT MSA first
  console.log('\n' + '='.repeat(60));
  console.log('PHASE 1: Testing WITHOUT MSA Search');
  console.log('='.repeat(60));

  const of3NoMsa = await testOpenFold3(gatewayUrl, null);
  const of2NoMsa = await testOpenFold2(gatewayUrl, null);

  // Get MSA
  console.log('\n' + '='.repeat(60));
  console.log('PHASE 2: Getting MSA from ColabFold');
  console.log('='.repeat(60));

  const msaAlignment = await testMsaSearch(gatewayUrl);

  if (msaAlignment) {
    // Test WITH MSA
    console.log('\n' + '='.repeat(60));
    console.log('PHASE 3: Testing WITH MSA Search');
    console.log('='.repeat(60));

    const of3WithMsa = await testOpenFold3(gatewayUrl, msaAlignment);
    const of2WithMsa = await testOpenFold2(gatewayUrl, msaAlignment);

    // Summary
    console.log('\n' + '='.repeat(60));
    console.log('SUMMARY');
    console.log('='.repeat(60));
    console.log('\nOpenFold3:');
    console.log(`  Without MSA: ${of3NoMsa ? (of3NoMsa.confidence_score * 100).toFixed(1) + '%' : 'FAILED'}`);
    console.log(`  With MSA:    ${of3WithMsa ? (of3WithMsa.confidence_score * 100).toFixed(1) + '%' : 'FAILED'}`);
    console.log('\nOpenFold2:');
    console.log(`  Without MSA: ${of2NoMsa ? of2NoMsa.confidence?.toFixed(1) + '%' : 'FAILED'}`);
    console.log(`  With MSA:    ${of2WithMsa ? of2WithMsa.confidence?.toFixed(1) + '%' : 'FAILED'}`);

    console.log('\nExpected behavior:');
    console.log('  - WITH MSA should generally give HIGHER confidence');
    console.log('  - P35354 (COX-2) is a well-studied protein, should have good MSA coverage');
    console.log('  - If WITH MSA is worse, there may be a format bug');
  }
}

main().catch(console.error);
