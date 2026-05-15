import type { Metadata } from 'next';
import './globals.css';

export const metadata: Metadata = {
  title: 'MigriGuide — Finnish Immigration Assistant',
  description:
    'AI-powered Finnish immigration assistant. All answers sourced exclusively from official Finnish government sources (Migri, Kela, DVV, Vero, InfoFinland).',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full">{children}</body>
    </html>
  );
}
