import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'edge';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// Shared secret proving to the backend that a request came through this route
// rather than straight at the public Cloud Run URL. Set it in the Cloudflare
// Pages dashboard (Settings → Environment variables) — never NEXT_PUBLIC_*.
const EDGE_SECRET = process.env.EDGE_SHARED_SECRET || '';

export async function POST(req: NextRequest) {
  const body = await req.json();

  // Cloud Run sees this Worker as the caller, not the user. Without forwarding
  // the real IP the backend limiter buckets every visitor under one key.
  const callerIp =
    req.headers.get('cf-connecting-ip') ??
    req.headers.get('x-forwarded-for')?.split(',')[0].trim() ??
    '';

  const res = await fetch(`${BACKEND_URL}/ask`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(callerIp ? { 'CF-Connecting-IP': callerIp } : {}),
      ...(EDGE_SECRET ? { 'X-Edge-Auth': EDGE_SECRET } : {}),
    },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
