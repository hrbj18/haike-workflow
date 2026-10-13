import test from 'node:test';
import assert from 'node:assert/strict';
import {accountCenterUrl} from '../src/gateway-config.js';
test('account navigation follows the saved gateway without keys, credentials or query strings',()=>{
  assert.equal(accountCenterUrl('https://8.138.207.71:17894/v2'),'https://8.138.207.71:17894/');
  assert.equal(accountCenterUrl('http://127.0.0.1:17894/v2'),'http://127.0.0.1:17894/');
  assert.equal(accountCenterUrl('https://example.com/haike/v2?token=private#fragment'),'https://example.com/haike/');
  assert.equal(accountCenterUrl('javascript:alert(1)'),accountCenterUrl());
  assert.equal(accountCenterUrl('https://name:password@example.com/v2'),accountCenterUrl());
});
