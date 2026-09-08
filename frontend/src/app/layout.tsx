import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'FinnPermit Guide — Finnish Immigration Assistant',
  description:
    'FinnPermit Guide — A free AI assistant for Finnish immigration questions, answered from official Finnish government sources. Not affiliated with the Finnish Immigration Service (Migri).',
};

/*
 * No client-side analytics beacon by design.
 *
 * Usage is measured server-side instead: the API emits a JSON event per request
 * to stdout, which Cloud Logging collects. That records what people actually ask
 * and how well the knowledge base covered it — far more actionable here than
 * pageview counts — and it needs no third-party script in the visitor's browser.
 * See README.md § Analytics.
 */
export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">{children}</body>
    </html>
  );
}
