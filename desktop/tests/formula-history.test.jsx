// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const state = vi.hoisted(() => ({ legacy: false, catalog: null, previewError: false }));
vi.mock('../src/desktopApi', () => ({
  invokePetrolab: vi.fn(async (command, payload) => {
    if (command === 'formula.methods.list' && state.catalog) return { result: { methods: [state.catalog] } };
    if (command === 'formula.preview') return state.previewError
      ? { error: { code: 'TEST_INPUT_ERROR', message: 'Тестовый отказ расчёта' } }
      : { result: { parameters: payload.parameters, input_fingerprint: 'preview', can_save: true,
          results: [{ analysis_id: 'analysis-1', values: {} }] } };
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
import { invokePetrolab } from '../src/desktopApi';

afterEach(() => { cleanup(); state.legacy = false; state.catalog = null; state.previewError = false; vi.clearAllMocks(); });

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

test.each([
  ['olivine.oxygen4', 'olivine', false, true],
  ['mica.charge22', 'phlogopite', true, true],
  ['clinopyroxene.oxygen6', 'diopside', false, true],
  ['orthopyroxene.oxygen6', 'enstatite', false, true],
  ['amphibole.oxygen23', 'tremolite', false, false],
])('%s has one keyboard-accessible action which never resets current parameters', async (methodId, target, mica, split) => {
  const preset = { fe_mode: 'all_fe2', ...(mica ? { anion_basis: 'ideal_O10_W2', oh_mode: 'not_calculated' } : {}) };
  state.catalog = {
    method_id: methodId, version: '0.1.0', name: target, status: 'draft',
    parameters: Object.keys(preset).map(name => ({ name })),
    parameter_choices: {
      fe_mode: { all_fe2: 'Fe²⁺', ...(split ? { reported_split: 'Измеренные Fe²⁺/Fe³⁺' } : {}) },
      ...(mica ? { anion_basis: { ideal_O10_W2: 'O10W2' },
        oh_mode: { not_calculated: 'Без OH', ideal_2_minus_f_cl: 'Измеренные F/Cl → OH' } } : {}),
    },
    quick_presets: [{ label: 'Рассчитать формулу', parameters: preset }],
    citations: [], assumptions: [], applicability: [],
  };
  const user = userEvent.setup();
  render(<FormulaPanel analysis={{ analysis_id: 'analysis-1', identity: { Analysis: 'A1' },
    mineral_verification: { accepted: { target } } }} databasePath="project.sqlite" />);
  const button = await screen.findByRole('button', { name: 'Рассчитать формулу' });
  await waitFor(() => expect(button.disabled).toBe(false));
  expect(screen.queryByRole('button', { name: 'Рассчитать с этими настройками' })).toBeNull();
  const settings = screen.getByText('Настроить расчёт', { selector: 'summary' });
  expect(settings.closest('details').open).toBe(false);
  button.focus();
  await user.tab();
  expect(document.activeElement).toBe(settings);
  await user.click(settings);
  const fe = screen.getByRole('combobox', { name: 'Режим железа' });
  expect(fe.value).toBe('all_fe2');
  const chosen = { ...preset };
  if (split) { await user.selectOptions(fe, 'reported_split'); chosen.fe_mode = 'reported_split'; }
  if (mica) {
    await user.selectOptions(screen.getByRole('combobox', { name: 'Расчёт OH' }), 'ideal_2_minus_f_cl');
    chosen.oh_mode = 'ideal_2_minus_f_cl';
  }
  button.focus();
  await user.keyboard('{Enter}');
  await screen.findByLabelText('Предпросмотр формулы');
  expect(within(screen.getByLabelText('Предпросмотр формулы')).getByText('Черновой bulk-пересчёт · не определение вида минерала.')).toBeTruthy();
  const previews = () => invokePetrolab.mock.calls.filter(([command]) => command === 'formula.preview');
  expect(previews().at(-1)[1]).toMatchObject({ analysis_ids: ['analysis-1'], method_id: methodId, parameters: chosen });
  await user.selectOptions(fe, '');
  expect(screen.queryByLabelText('Предпросмотр формулы')).toBeNull();
  expect(button.disabled).toBe(true);
  expect(screen.getByText('Выберите: Режим железа.')).toBeTruthy();
  expect(screen.getByText('Сохранённые расчёты · 1')).toBeTruthy();
  await user.selectOptions(fe, chosen.fe_mode);
  state.previewError = true;
  await user.click(button);
  await screen.findByRole('alert');
  expect(fe.value).toBe(chosen.fe_mode);
  expect(button.disabled).toBe(false);
  expect(previews().at(-1)[1].parameters).toEqual(chosen);
  expect(invokePetrolab.mock.calls.some(([command]) => command === 'formula.save')).toBe(false);
});
