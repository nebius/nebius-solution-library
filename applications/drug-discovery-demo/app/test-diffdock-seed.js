// Test DiffDock with seed parameter for reproducibility
const gatewayUrl = '185.82.69.28';

// Simple test protein (just a few atoms)
const testProtein = `ATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00  0.00           N
ATOM      2  CA  ALA A   1       1.458   0.000   0.000  1.00  0.00           C
ATOM      3  C   ALA A   1       2.009   1.420   0.000  1.00  0.00           C
ATOM      4  O   ALA A   1       1.246   2.390   0.000  1.00  0.00           O
END`;

// Ibuprofen SMILES
const ibuprofen = 'CC(C)Cc1ccc(cc1)C(C)C(=O)O';

async function testWithSeed(seed) {
  const url = `http://${gatewayUrl}:8007/molecular-docking/diffdock/generate`;

  const body = {
    protein: testProtein,
    ligand: ibuprofen,
    ligand_file_type: 'txt',
    num_poses: 3,
    time_divisions: 20,
    steps: 18,
    save_trajectory: false,
    is_staged: false,
  };

  // Try adding seed
  if (seed !== undefined) {
    body.seed = seed;
  }

  console.log(`\nTesting with seed=${seed === undefined ? 'none' : seed}...`);

  try {
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const text = await response.text();
      console.log('Error:', response.status, text.substring(0, 200));
      return;
    }

    const data = await response.json();

    if (data.position_confidence) {
      const confidences = data.position_confidence
        .filter(c => c !== null)
        .map(c => (Math.exp(c) * 100).toFixed(1) + '%');
      console.log('Confidences:', confidences.join(', '));
    } else {
      console.log('No confidences returned');
    }
  } catch (e) {
    console.log('Error:', e.message);
  }
}

async function main() {
  console.log('Testing DiffDock reproducibility with seed parameter');

  // Test without seed (should vary)
  await testWithSeed(undefined);
  await testWithSeed(undefined);

  // Test with fixed seed (should be same)
  await testWithSeed(42);
  await testWithSeed(42);

  // Test with different seed
  await testWithSeed(123);
}

main().catch(console.error);
