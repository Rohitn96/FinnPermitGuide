import { NextResponse } from 'next/server';

export const runtime = 'edge';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

/**
 * Corpus metadata for the freshness badge.
 *
 * Proxied rather than fetched from the browser because the backend's CORS
 * policy only admits this site's own server-side calls. A failure here is not
 * worth showing an error for — the badge just does not render.
 */
export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/`, {
      // The corpus changes only when a new index is deployed.
      next: { revalidate: 3600 },
    });
    if (!res.ok) return NextResponse.json({});

    const data = await res.json();
    return NextResponse.json({ corpus_date: data.corpus_date ?? null });
  } catch {
    return NextResponse.json({});
  }
}
