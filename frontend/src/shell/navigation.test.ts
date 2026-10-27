import { describe, expect, it } from 'vitest';
import { recordRoute, viewRoute } from '@/screens/registry';
import { defaultViewFor, nextTrail } from './navigation';

describe('el camino (paso 16: sin pestanas)', () => {
  const list = viewRoute('clients');
  const client = recordRoute('client', 4);
  const invoice = recordRoute('invoice', 9);

  it('una entrada o una vista empieza un camino nuevo', () => {
    expect(nextTrail([list, client], { type: 'go', view: 'vat' })).toEqual({ trail: [viewRoute('vat')], lastMove: 'forward' });
    expect(nextTrail([list, client], { type: 'open', route: viewRoute('home') }).trail).toEqual([viewRoute('home')]);
  });

  it('una ficha es un paso mas; si ya estaba en el camino, se vuelve a ella', () => {
    expect(nextTrail([list], { type: 'open', route: client })).toEqual({ trail: [list, client], lastMove: 'forward' });
    expect(nextTrail([list, client], { type: 'open', route: invoice }).trail).toEqual([list, client, invoice]);
    expect(nextTrail([list, client, invoice], { type: 'open', route: { screen: 'client', id: 4 } })).toEqual({
      trail: [list, client],
      lastMove: 'back',
    });
  });

  it('volver quita el ultimo paso; en la raiz no hace nada; una miga vuelve a su paso', () => {
    expect(nextTrail([list, client, invoice], { type: 'back' }).trail).toEqual([list, client]);
    expect(nextTrail([list], { type: 'back' }).trail).toEqual([list]);
    expect(nextTrail([list, client, invoice], { type: 'backTo', index: 0 }).trail).toEqual([list]);
    expect(nextTrail([list, client], { type: 'backTo', index: 5 }).trail).toEqual([list, client]);
  });

  it('desde Ctrl+K o la caja del inicio: la vista de la ficha y la ficha', () => {
    expect(nextTrail([viewRoute('home')], { type: 'openFrom', view: 'clients', route: client }).trail).toEqual([list, client]);
    expect(nextTrail([viewRoute('home')], { type: 'openFrom', view: 'vat', route: viewRoute('vat') }).trail).toEqual([viewRoute('vat')]);
  });

  it('una factura sin lista se abre en la de su sentido', () => {
    expect(defaultViewFor(invoice, 'entrante')).toBe('invoices-in');
    expect(defaultViewFor(invoice, 'saliente')).toBe('invoices-out');
    expect(defaultViewFor(client)).toBe('clients');
    expect(defaultViewFor(recordRoute('exception', 3))).toBe('exceptions');
    expect(defaultViewFor(viewRoute('vat'))).toBe('vat');
  });
});
