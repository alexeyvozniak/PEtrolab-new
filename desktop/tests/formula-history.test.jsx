// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

const state = vi.hoisted(() => ({ legacy: false, catalog: null, previewError: false, previewResult: null, previewReply: null, scopedIssues: null }));
vi.mock('../src/desktopApi', () => ({
  invokePetrolab: vi.fn(async (command, payload) => {
    if (command === 'formula.methods.list' && state.scopedIssues) return { result: { methods: [], scope_issues: state.scopedIssues, scope_message: 'Примите минерал.' } };
    if (command === 'formula.methods.list' && state.catalog) return { result: { methods: [state.catalog] } };
    if (command === 'formula.preview' && state.previewReply) return state.previewReply(payload);
    if (command === 'formula.preview') return state.previewError
      ? { error: { code: 'TEST_INPUT_ERROR', message: 'Тестовый отказ расчёта' } }
      : { result: { parameters: payload.parameters, input_fingerprint: 'preview', can_save: true,
          results: [{ analysis_id: 'analysis-1', values: {}, ...(state.previewResult || {}) }] } };
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
import { MineralsWorkspace } from '../src/MineralsWorkspace';

function batchCatalog() {
  return { method_id: 'olivine.oxygen4', version: '1.0.0', name: 'Оливин', status: 'draft',
    parameters: [{ name: 'fe_mode' }], parameter_choices: { fe_mode: { all_fe2: 'Fe2', reported_split: 'Split' } },
    quick_presets: [{ parameters: { fe_mode: 'all_fe2' } }], citations: [], assumptions: [], applicability: [] };
}

test('100 explicit IDs show only one failed analysis; removal requires new preview and preserves Fe', async () => {
  state.catalog = batchCatalog();
  state.previewReply = async payload => ({ result: { parameters: payload.parameters,
    input_fingerprint: 'hundred', can_save: false,
    input_snapshots: payload.analysis_ids.map(id => ({ analysis_id: id, identity: { Analysis: id } })),
    results: payload.analysis_ids.map((id, index) => ({ analysis_id: id,
      status: index >= 98 ? 'failed' : 'current', values: { Fo: 50 },
      errors: index === 98 ? ['First row error', 'Extra reason'] : index === 99 ? ['Second row error'] : [] })) } });
  const ids = Array.from({ length: 100 }, (_, i) => `analysis-${i+1}`);
  const onExclude = vi.fn();
  const user = userEvent.setup();
  const props = { analysis: { analysis_id: ids[0] }, databasePath: 'project.sqlite', onExcludeAnalysis: onExclude };
  const view = render(<FormulaPanel {...props} analysisIds={ids} />);
  const action = await screen.findByRole('button', { name: 'Рассчитать формулы' });
  await waitFor(() => expect(action.disabled).toBe(false));
  expect(screen.getByText('Настроить расчёт').closest('details').open).toBe(false);
  await user.click(screen.getByText('Настроить расчёт'));
  await user.selectOptions(screen.getByLabelText('Режим железа'), 'reported_split');
  await user.click(action);
  await screen.findByText('Готово 98 · Требуют решения 2');
  expect(screen.getByText('Другие причины · 1').closest('details').open).toBe(false);
  expect(screen.queryByText('Second row error')).toBeNull();
  expect(screen.getByRole('button', { name: 'Сохранить 100 результатов' }).disabled).toBe(true);
  await user.click(screen.getByRole('button', { name: 'Следующая ошибка' }));
  expect(screen.getByText('Second row error')).toBeTruthy();
  expect(screen.queryByText('First row error')).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Убрать этот анализ из отбора' }));
  expect(onExclude).toHaveBeenCalledWith('analysis-100');
  view.rerender(<FormulaPanel {...props} analysisIds={ids.slice(0,99)} />);
  expect(screen.queryByLabelText('Предпросмотр формулы')).toBeNull();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Рассчитать формулы' }).disabled).toBe(false));
  expect(screen.getByLabelText('Режим железа').value).toBe('reported_split');
  expect(invokePetrolab.mock.calls.filter(([command]) => command === 'formula.preview').at(-1)[1].analysis_ids).toEqual(ids);
  expect(invokePetrolab.mock.calls.some(([command]) => command === 'formula.save')).toBe(false);
});

test('late batch preview cannot revive results after the exact scope changes', async () => {
  state.catalog = batchCatalog();
  let finish;
  state.previewReply = () => new Promise(resolve => { finish = resolve; });
  const user = userEvent.setup();
  const props = { analysis: { analysis_id: 'analysis-1' }, databasePath: 'project.sqlite' };
  const view = render(<FormulaPanel {...props} analysisIds={['analysis-1', 'analysis-2']} />);
  const action = await screen.findByRole('button', { name: 'Рассчитать формулы' });
  await waitFor(() => expect(action.disabled).toBe(false));
  await user.click(action);
  view.rerender(<FormulaPanel {...props} analysisIds={['analysis-1']} />);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Рассчитать формулы' }).disabled).toBe(false));
  finish({ result: { parameters: { fe_mode: 'all_fe2' }, input_fingerprint: 'old', can_save: true,
    results: [{ analysis_id: 'analysis-2', status: 'current', values: { Fo: 99 } }] } });
  await waitFor(() => expect(screen.queryByLabelText('Предпросмотр формулы')).toBeNull());
  await user.click(screen.getByText('Настроить расчёт'));
  expect(screen.queryByRole('button', { name: /Сохранить .*результатов/ })).toBeNull();
});

test('101 selected IDs explain the bound without truncation or hidden catalog batching', async () => {
  render(<FormulaPanel analysis={{ analysis_id: 'a' }} databasePath="project.sqlite"
    analysisIds={Array.from({ length: 101 }, (_, i) => `id-${i}`)} />);
  await screen.findByText('Выберите не больше 100 анализов. Отбор не будет разделён автоматически.');
  expect(screen.queryByRole('button', { name: 'Рассчитать формулы' })).toBeNull();
  expect(invokePetrolab.mock.calls.some(([command]) => command === 'formula.methods.list')).toBe(false);
});

test('reviewing an unloaded selected mineral fetches its exact ID without clearing Selection', async () => {
  state.scopedIssues = [{ analysis_id: 'analysis-1', identity: { Analysis: 'A1' }, can_review: true, message: 'Назначение не принято.' }];
  const record = { analysis_id: 'analysis-1', identity: { Analysis: 'A1' },
    mineral_verification: { status: 'consistent', prediction: 'olivine', confidence: 'high',
      input_fingerprint: 'real-input', ruleset_version: 'v1', issues: [], reasons: [], candidates: [] } };
  const onSelection = vi.fn(); const onDecide = vi.fn(); const loadedIds = vi.fn();
  function Unloaded() {
    const [rows, setRows] = useState([]);
    return <MineralsWorkspace project={{ total: 1, analyses: rows, mineral_options: ['olivine'] }}
      databasePath="project.sqlite" selectionIds={['analysis-1']} onSelectionChange={onSelection} onDecide={onDecide}
      onLoadSourceAnalyses={async ids => { loadedIds(ids); setRows([record]); return [record]; }} />;
  }
  const user = userEvent.setup(); render(<Unloaded />);
  await user.click(await screen.findByRole('button', { name: 'Проверить этот анализ' }));
  expect(loadedIds).toHaveBeenCalledWith(['analysis-1']);
  await screen.findByRole('button', { name: 'К групповому пересчёту' });
  await user.click(screen.getByRole('button', { name: 'Принять предложение' }));
  expect(onDecide.mock.calls[0][0].mineral_verification.input_fingerprint).toBe('real-input');
  expect(onSelection).not.toHaveBeenCalled();
});

afterEach(() => { cleanup(); state.legacy = false; state.catalog = null; state.previewError = false; state.previewResult = null; state.previewReply = null; state.scopedIssues = null; vi.clearAllMocks(); });

test('site heading uses Python ordered contract after Tauri alphabetically reorders JSON object keys', async () => {
  state.catalog = { method_id: 'clinopyroxene.structural6', version: '0.1.0', name: 'Cpx', status: 'draft',
    parameters: [{ name: 'fe_mode' }], parameter_choices: { fe_mode: { all_fe2: 'Fe2' } },
    quick_presets: [{ parameters: { fe_mode: 'all_fe2' } }], citations: [], assumptions: [], applicability: [] };
  state.previewResult = { sites: { M1: { Mg: 1 }, M2: { Ca: 1 }, T: { Si: 2 } },
    site_order: ['T', 'M1', 'M2'], values: { M1_Mg_apfu: 1, M2_Ca_apfu: 1, T_Si_apfu: 2 } };
  const user = userEvent.setup();
  render(<FormulaPanel analysis={{ analysis_id: 'analysis-1', mineral_verification: { accepted: { target: 'diopside' } } }} databasePath="project.sqlite" />);
  const button = await screen.findByRole('button', { name: 'Рассчитать формулу' });
  await waitFor(() => expect(button.disabled).toBe(false));
  await user.click(button);
  const positions = await screen.findByText('Позиции T/M1/M2 · оценка', { selector: 'summary' });
  await user.click(positions);
  expect(screen.getByRole('table', { name: 'Распределение по позициям' }).querySelector('tbody tr th').textContent).toBe('T · Si');
  expect(screen.queryByText('Позиции M1/M2/T · оценка', { selector: 'summary' })).toBeNull();
});

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
