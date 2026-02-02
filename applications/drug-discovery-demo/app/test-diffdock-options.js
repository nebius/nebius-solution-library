// Test what parameters DiffDock API accepts
const gatewayUrl = '185.82.69.28';

async function testOpenAPISpec() {
  // Check if there's an OpenAPI spec
  const specUrl = `http://${gatewayUrl}:8007/openapi.json`;
  console.log('Checking OpenAPI spec at:', specUrl);

  try {
    const response = await fetch(specUrl);
    if (response.ok) {
      const spec = await response.json();
      console.log('\nDiffDock API paths:', Object.keys(spec.paths || {}));

      // Find the generate endpoint schema
      const generatePath = spec.paths?.['/molecular-docking/diffdock/generate'];
      if (generatePath?.post?.requestBody?.content?.['application/json']?.schema) {
        const schema = generatePath.post.requestBody.content['application/json'].schema;
        console.log('\nRequest schema properties:');
        if (schema.properties) {
          for (const [key, val] of Object.entries(schema.properties)) {
            console.log(`  ${key}: ${val.type || val.$ref} ${val.default !== undefined ? `(default: ${val.default})` : ''}`);
          }
        } else if (schema.$ref) {
          console.log('  Schema ref:', schema.$ref);
          // Try to resolve ref
          const refName = schema.$ref.split('/').pop();
          const refSchema = spec.components?.schemas?.[refName];
          if (refSchema?.properties) {
            for (const [key, val] of Object.entries(refSchema.properties)) {
              console.log(`  ${key}: ${val.type || val.$ref} ${val.default !== undefined ? `(default: ${val.default})` : ''}`);
            }
          }
        }
      }
    } else {
      console.log('No OpenAPI spec available:', response.status);
    }
  } catch (e) {
    console.log('Error fetching spec:', e.message);
  }
}

async function testHealthEndpoint() {
  const healthUrl = `http://${gatewayUrl}:8007/v1/health/ready`;
  console.log('\nChecking health at:', healthUrl);

  try {
    const response = await fetch(healthUrl);
    console.log('Health status:', response.status);
  } catch (e) {
    console.log('Health check error:', e.message);
  }
}

async function main() {
  await testOpenAPISpec();
  await testHealthEndpoint();
}

main().catch(console.error);
