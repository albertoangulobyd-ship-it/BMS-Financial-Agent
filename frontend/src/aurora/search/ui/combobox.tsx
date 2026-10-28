// PartyCombobox de Aurora (components/ui/combobox.tsx, entrega del 28-10-2026), tal cual: la lista
// con su buscador (cmdk), los dos grupos y las iniciales. Cambio (I): los textos del diccionario.
import { useId, useState } from 'react';
import { CheckIcon, ChevronsUpDownIcon } from 'lucide-react';
import { Label } from 'radix-ui';
import { useT } from '@/i18n';
import { Avatar, AvatarFallback } from './avatar';
import { Button } from './button';
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from './command';
import { Popover, PopoverContent, PopoverTrigger } from './popover';

export type PartyOption = { value: string; label: string; description: string; group: 'client' | 'provider' };

const initialsOf = (label: string) =>
  label
    .split(' ')
    .slice(0, 2)
    .map((w) => w[0])
    .join('');

export function PartyCombobox({ options, value, onValueChange }: { options: PartyOption[]; value: string; onValueChange: (value: string) => void }) {
  const { t } = useT();
  const s = t.aurora.search;
  const id = useId(),
    [open, setOpen] = useState(false),
    selected = options.find((o) => o.value === value);
  return (
    <div className='party-combobox'>
      <Label.Root htmlFor={id} className='filter-label'>
        {s.party}
      </Label.Root>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button id={id} variant='outline' role='combobox' aria-expanded={open} aria-label={s.partyChoose}>
            {selected ? (
              <span className='party-selected'>
                <Avatar>
                  <AvatarFallback>{initialsOf(selected.label)}</AvatarFallback>
                </Avatar>
                <span data-proper-name=''>{selected.label}</span>
              </span>
            ) : (
              <span>{s.partyAll}</span>
            )}
            <ChevronsUpDownIcon size={14} />
          </Button>
        </PopoverTrigger>
        <PopoverContent className='party-popover'>
          <Command>
            <CommandInput placeholder={s.partySearch} aria-label={s.partySearchLabel} />
            <CommandList>
              <CommandEmpty>{s.partyNone}</CommandEmpty>
              <CommandGroup>
                <CommandItem
                  value={s.partyAll}
                  onSelect={() => {
                    onValueChange('');
                    setOpen(false);
                  }}
                >
                  {s.partyAll}
                  {!value && <CheckIcon size={14} />}
                </CommandItem>
              </CommandGroup>
              {(['client', 'provider'] as const).map((group) => (
                <CommandGroup key={group} heading={group === 'client' ? s.clients : s.providers}>
                  {options
                    .filter((o) => o.group === group)
                    .map((o) => (
                      <CommandItem
                        key={o.value}
                        value={o.value + ' ' + o.label + ' ' + o.description}
                        onSelect={() => {
                          onValueChange(o.value === value ? '' : o.value);
                          setOpen(false);
                        }}
                      >
                        <Avatar>
                          <AvatarFallback>{initialsOf(o.label)}</AvatarFallback>
                        </Avatar>
                        <span className='party-option'>
                          <strong data-proper-name=''>{o.label}</strong>
                          <small data-proper-name=''>{o.description}</small>
                        </span>
                        {value === o.value && <CheckIcon size={14} />}
                      </CommandItem>
                    ))}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
    </div>
  );
}
