// El buscador de una lista: busca en lo que ya se ve (numero y relacion), sin mayusculas
// ni acentos. Escape lo vacia.
import { Search, X } from 'lucide-react';
import { useId } from 'react';
import { Input } from '@/components/ui/input';
import { useT } from '@/i18n';

export function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  const { t } = useT();
  const id = useId();
  return (
    <div className='relative w-full max-w-xs'>
      <label htmlFor={id} className='sr-only'>
        {placeholder}
      </label>
      <Search className='pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground' aria-hidden='true' />
      <Input
        id={id}
        type='search'
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') onChange('');
        }}
        placeholder={placeholder}
        autoComplete='off'
        spellCheck={false}
        className='h-9 pl-8 pr-8'
      />
      {value && (
        <button
          type='button'
          aria-label={t.common.clearSearch}
          onClick={() => onChange('')}
          className='absolute right-1.5 top-1.5 flex h-6 w-6 items-center justify-center rounded-sm text-muted-foreground hover:text-foreground'
        >
          <X className='h-3.5 w-3.5' aria-hidden='true' />
        </button>
      )}
    </div>
  );
}
