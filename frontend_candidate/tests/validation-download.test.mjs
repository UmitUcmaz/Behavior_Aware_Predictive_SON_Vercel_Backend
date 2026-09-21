import assert from 'node:assert/strict';
import {test} from 'node:test';
import {GET} from '../src/app/api/validation-download/route.ts';

test('invalid validation ids cannot sign arbitrary Blob paths', async () => {
  for (const id of ['', 'FR-20260919T162449116079Z', 'VAL-../../source/network_traffic.csv.gz']) {
    const response=await GET(new Request(`https://app.example/api/validation-download?validation_id=${encodeURIComponent(id)}`));
    assert.equal(response.status,400);
    assert.equal(response.headers.get('location'),null);
    assert.equal(response.headers.get('cache-control'),'no-store');
  }
});

test('missing Blob secret fails closed without a redirect', async () => {
  const previous=process.env.BLOB_READ_WRITE_TOKEN;
  delete process.env.BLOB_READ_WRITE_TOKEN;
  try {
    const response=await GET(new Request('https://app.example/api/validation-download?validation_id=VAL-20260919T162449116079Z'));
    assert.equal(response.status,503); assert.equal(response.headers.get('location'),null);
  } finally {
    if(previous!==undefined)process.env.BLOB_READ_WRITE_TOKEN=previous;
  }
});
