import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'FinnPermit Guide — Finnish Immigration Assistant',
  description:
    'FinnPermit Guide — A free AI assistant for Finnish immigration questions. Not affiliated with the Finnish Immigration Service (Migri).',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">{children}</body>
    </html>
  );
}
