// FilterComboBox de Aurora (components/ui/heroui-combo-box.tsx, entrega del 28-10-2026), tal cual.
// Cambio (I): los textos del diccionario.
import { useId, useState } from 'react';
import { Check, ChevronDown } from 'lucide-react';
import { fmt, useT } from '@/i18n';
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from './command';
import { Popover, PopoverContent, PopoverTrigger } from './popover';

// Scoped adaptation of the supplied editable combobox. Each instance owns its list.
export function FilterComboBox({
  label,
  options,
  value,
  onValueChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  onValueChange: (value: string) => void;
}) {
  const { t } = useT();
  const s = t.aurora.search;
  const id = useId(),
    [open, setOpen] = useState(false);
  const search = fmt(s.comboSearch, { what: label.toLocaleLowerCase() });
  return (
    <div className='filter-combo'>
      <label className='filter-label' htmlFor={id}>
        {label}
      </label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button id={id} type='button' className='filter-combo-trigger' role='combobox' aria-label={label} aria-expanded={open}>
            {options.find((o) => o.value === value)?.label ?? s.all}
            <ChevronDown size={14} />
          </button>
        </PopoverTrigger>
        <PopoverContent className='filter-combo-popover'>
          <Command>
            <CommandInput placeholder={search + '…'} aria-label={search} />
            <CommandList>
              <CommandEmpty>{s.comboNone}</CommandEmpty>
              {options.map((o) => (
                <CommandItem
                  key={o.value}
                  value={o.value + ' ' + o.label}
                  onSelect={() => {
                    onValueChange(o.value);
                    setOpen(false);
                  }}
                >
                  {o.label}
                  {value === o.value && <Check size={14} />}
                </CommandItem>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
