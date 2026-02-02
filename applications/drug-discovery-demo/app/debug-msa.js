const P35354_SEQUENCE = 'MLARALLLCAVLALSHTANPCCSHPCQNRGVCMSVGFDQYKCDCTRTGFYGENCSTPEFLTRIKLFLKPTPNTVHYILTHFKGFWNVVNNIPFLRNAIMSYVLTSRSHLIDSPPTYNADYGYKSWEAFSNLSYYTRALPPVPDDCPTPLGVKGKKQLPDSNEIVEKLLLRRKFIPDPQGSNMMFAFFAQHFTHQFFKTDHKRGPAFTNGLGHGVDLNHIYGETLARQRKLRLFKDGKMKYQIIDGEMYPPTVKDTQAEMIYPPQVPEHLRFAVGQEVFGLVPGLMMYATIWLREHNRVCDVLKQEHPEWGDEQLFQTSRLILIGETIKIVIEDYVQHLSGYHFKLKFDPELLFNKQFQYQNRIAAEFNTLYHWHPLLPDTFQIHDQKYNYQQFIYNNSILLEHGITQFVESFTRQIAGRVAGGRNVPPAVQKVSQASIDQSRQMKYQSFNEYRKRFMLKPYESFEELTGEKEMSAELEALYGDIDAVELYPALLVEKPRPDAIFGETMVEVGAPFSLKGLMGNVICSPAYWKPSTFGGEVGFQIINTASIQSLICNNVKGCPFTSFSVPDPELIKTVTINASSSRSGLDDINPTVLLKERSTEL';

async function main() {
  const gatewayUrl = '185.82.69.28';

  // Get MSA
  console.log('Fetching MSA...');
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
  let a3m = '';
  for (const dbName of Object.keys(data.alignments)) {
    if (data.alignments[dbName] && data.alignments[dbName].a3m && data.alignments[dbName].a3m.alignment) {
      a3m = data.alignments[dbName].a3m.alignment;
      break;
    }
  }

  // Parse A3M and analyze
  const lines = a3m.trim().split('\n');
  const sequences = [];
  let currentHeader = '';
  let currentSeq = '';

  for (const line of lines) {
    if (line.startsWith('>')) {
      if (currentSeq) {
        sequences.push({ header: currentHeader, seq: currentSeq, len: currentSeq.length });
      }
      currentHeader = line;
      currentSeq = '';
    } else {
      currentSeq += line.trim();
    }
  }
  if (currentSeq) {
    sequences.push({ header: currentHeader, seq: currentSeq, len: currentSeq.length });
  }

  console.log('Query sequence length:', P35354_SEQUENCE.length);
  console.log('Number of sequences in A3M:', sequences.length);
  console.log('\nFirst 5 sequences:');
  for (let i = 0; i < Math.min(5, sequences.length); i++) {
    const s = sequences[i];
    const cleanedSeq = s.seq.replace(/[a-z]/g, '');
    console.log('  ' + i + ': header=' + s.header.substring(0, 40) + '...');
    console.log('      raw_len=' + s.len + ' cleaned_len=' + cleanedSeq.length);
    console.log('      first 80 raw: ' + s.seq.substring(0, 80));
    console.log('      first 80 cleaned: ' + cleanedSeq.substring(0, 80));
  }

  // Check if cleaned sequences match query length
  console.log('\nSequence length analysis (after removing lowercase):');
  const lengthCounts = {};
  for (const s of sequences) {
    const cleanedLen = s.seq.replace(/[a-z]/g, '').length;
    if (!lengthCounts[cleanedLen]) lengthCounts[cleanedLen] = 0;
    lengthCounts[cleanedLen]++;
  }
  const sortedLengths = Object.entries(lengthCounts).sort((a, b) => b[1] - a[1]);
  for (let i = 0; i < Math.min(10, sortedLengths.length); i++) {
    console.log('  Length ' + sortedLengths[i][0] + ': ' + sortedLengths[i][1] + ' sequences');
  }

  // Check if query matches first sequence
  console.log('\n=== Query vs First A3M Sequence ===');
  const firstSeq = sequences[0].seq;
  const firstSeqCleaned = firstSeq.replace(/[a-z]/g, '');
  console.log('Query length: ' + P35354_SEQUENCE.length);
  console.log('First A3M seq (cleaned) length: ' + firstSeqCleaned.length);
  console.log('Match: ' + (P35354_SEQUENCE === firstSeqCleaned));

  if (P35354_SEQUENCE !== firstSeqCleaned) {
    console.log('\nMismatch details:');
    for (let i = 0; i < Math.max(P35354_SEQUENCE.length, firstSeqCleaned.length); i++) {
      if (P35354_SEQUENCE[i] !== firstSeqCleaned[i]) {
        console.log('  First difference at position ' + i + ': query=' + (P35354_SEQUENCE[i] || 'END') + ' a3m=' + (firstSeqCleaned[i] || 'END'));
        break;
      }
    }
  }
}

main().catch(console.error);
