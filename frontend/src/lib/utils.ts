import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

// La funcion de siempre de shadcn: une clases y deja la ultima cuando chocan.
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
