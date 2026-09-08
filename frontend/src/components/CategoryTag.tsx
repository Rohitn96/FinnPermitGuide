const STYLES: Record<string, string> = {
  work:                 'bg-blue-50 text-blue-700 border-blue-200',
  family:               'bg-pink-50 text-pink-700 border-pink-200',
  study:                'bg-purple-50 text-purple-700 border-purple-200',
  permanent:            'bg-emerald-50 text-emerald-700 border-emerald-200',
  citizenship:          'bg-yellow-50 text-yellow-700 border-yellow-200',
  benefits:             'bg-teal-50 text-teal-700 border-teal-200',
  asylum:               'bg-red-50 text-red-700 border-red-200',
  tax:                  'bg-orange-50 text-orange-700 border-orange-200',
  registration:         'bg-slate-50 text-slate-700 border-slate-200',
  eu_citizen:           'bg-blue-50 text-blue-700 border-blue-200',
  appeals:              'bg-red-50 text-red-700 border-red-200',
  processing:           'bg-indigo-50 text-indigo-700 border-indigo-200',
  documents:            'bg-slate-50 text-slate-700 border-slate-200',
  customs:              'bg-yellow-50 text-yellow-700 border-yellow-200',
  worker_rights:        'bg-rose-50 text-rose-700 border-rose-200',
  general:              'bg-gray-50 text-gray-600 border-gray-200',
};

const LABELS: Record<string, string> = {
  work:                 'Work',
  family:               'Family',
  study:                'Study',
  permanent:            'Permanent Residence',
  citizenship:          'Citizenship',
  benefits:             'Benefits',
  asylum:               'Asylum',
  tax:                  'Tax',
  registration:         'Registration',
  eu_citizen:           'EU Citizen',
  appeals:              'Appeals',
  processing:           'Processing',
  documents:            'Documents',
  customs:              'Customs',
  worker_rights:        'Workers’ Rights',
  general:              'General',
};

export default function CategoryTag({ category }: { category: string }) {
  const style = STYLES[category] ?? STYLES.general;
  const label = LABELS[category] ?? category;
  return (
    <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full border mb-2 ${style}`}>
      {label}
    </span>
  );
}
