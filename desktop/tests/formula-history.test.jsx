// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const state = vi.hoisted(() => ({ legacy: false }));
vi.mock('../src/desktopApi', () => ({
  invokePetrolab: vi.fn(async command => {
    if (command === 'formula.methods.list') return { result: { methods: [{
      method_id: 'olivine.oxygen4', version: '2.0.0', name: 'Новый метод', status: 'draft',
      parameters: [{ name: 'fe_mode' }],
      parameter_choices: { fe_mode: { all_fe2: 'Новое описание — не относится к старому run' } },
      quick_presets: [], citations: [], assumptions: [], applicability: [],
    }] } };
    if (command === 'formula.runs.list') return { result: { runs: [{ run: {
      id: 'old-run', method_id: 'olivine.oxygen4', method_version: '1.0.0',
      status: 'current', stale_reasons: [], created_at: '2026-09-01T00:00:00Z',
      input_fingerprint: 'old-input', parameters: { fe_mode: 'all_fe2' },
      result_manifest: {
        method: { name: 'Старый метод' }, results: [{ analysis_id: 'analysis-1', values: {} }],
        ...(state.legacy ? {} : { parameter_descriptions: {
          fe_mode: { all_fe2: 'Сохранённое допущение: всё Fe как Fe²⁺' },
        } }),
      },
    } }] } };
    throw new Error(command);
  }),
}));

import { FormulaPanel } from '../src/FormulaPanel';

afterEach(() => { cleanup(); state.legacy = false; });

test('formula history uses saved parameter descriptions, not a newer method catalog', async () => {
  const user = userEvent.setup();
  render(<FormulaPanel analysis={{ analysis_id: 'analysis-1', identity: { Analysis: 'A1' },
    mineral_verification: { accepted: { target: 'olivine' } } }} databasePath="project.sqlite" />);
  const history = (await screen.findByText(/Старый метод · v1\.0\.0/)).closest('details');
  await user.click(within(history).getByText(/Старый метод/));
  await waitFor(() => expect(within(history).getByText('Сохранённое допущение: всё Fe как Fe²⁺')).toBeTruthy());
  expect(within(history).queryByText('Новое описание — не относится к старому run')).toBeNull();
});

test('legacy history without descriptions shows exact stored parameter key', async () => {
  state.legacy = true;
  const user = userEvent.setup();
  render(<FormulaPanel analysis={{ analysis_id: 'analysis-1', identity: { Analysis: 'A1' },
    mineral_verification: { accepted: { target: 'olivine' } } }} databasePath="project.sqlite" />);
  const history = (await screen.findByText(/Старый метод · v1\.0\.0/)).closest('details');
  await user.click(within(history).getByText(/Старый метод/));
  expect(within(history).getByText('all_fe2')).toBeTruthy();
  expect(within(history).queryByText('Новое описание — не относится к старому run')).toBeNull();
});
