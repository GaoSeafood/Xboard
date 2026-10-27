import {createHmac} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

const secret = process.env.DEPLOY_SECRET;
const sha = process.env.TARGET_SHA;
if (!secret || secret.length < 32) throw new Error('DEPLOY_HOOK_SECRET is missing or too short');
if (!/^[a-f0-9]{40}$/.test(sha || '')) throw new Error('Invalid source revision');
if (process.env.REPOSITORY !== 'GaoSeafood/Xboard' || process.env.REF !== 'refs/heads/master') {
  throw new Error('Only the owned production branch may be deployed');
}
const base = 'https://ad.gaoseafood.com/api/deploy-hook/xboard';
const body = JSON.stringify({repository: {full_name: process.env.REPOSITORY}, ref: process.env.REF, after: sha});
const signature = 'sha256=' + createHmac('sha256', secret).update(body).digest('hex');
const accepted = await fetch(base, {
  method: 'POST', signal: AbortSignal.timeout(30_000),
  headers: {'content-type': 'application/json', 'x-github-event': 'push',
    'x-github-delivery': process.env.DELIVERY_ID, 'x-hub-signature-256': signature}, body,
});
if (!accepted.ok) throw new Error(`Deployment request rejected: HTTP ${accepted.status}`);
const receipt = await accepted.json();
if (receipt.queued !== true || receipt.sha !== sha) throw new Error('Unexpected deployment receipt');
const statusUrl = `${base}/status?sha=${sha}`;
const deadline = Date.now() + 80 * 60_000;
let transientFailures = 0;
while (Date.now() < deadline) {
  let state;
  try {
    const response = await fetch(statusUrl, {headers: {'x-deploy-token': secret}, signal: AbortSignal.timeout(20_000)});
    if (response.status === 401 || response.status === 403) throw new Error('Deployment status authentication failed');
    if (!response.ok) throw new TypeError('Deployment status temporarily unavailable');
    state = await response.json();
    transientFailures = 0;
  } catch (error) {
    if (!(error instanceof TypeError) && error.name !== 'TimeoutError') throw error;
    if (++transientFailures >= 12) throw new Error('Deployment status unavailable for repeated requests');
    await delay(10_000);
    continue;
  }
  if (state.sha !== sha) throw new Error('Deployment response revision mismatch');
  if (state.status === 'succeeded') {
    console.log(`Production verified: ${sha}`);
    process.exit(0);
  }
  if (state.status === 'failed') throw new Error('Server release failed; inspect the protected server release status');
  await delay(10_000);
}
throw new Error('Timed out waiting for production verification');
