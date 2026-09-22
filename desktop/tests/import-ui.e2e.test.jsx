// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnalysesWorkspace } from '../src/AnalysesWorkspace';
import { MineralsWorkspace } from '../src/MineralsWorkspace';

const uiState = vi.hoisted(() => ({ imported: false, mediaImported: false, mediaPlacementCount: 0, pointCreated: false, pointRetired: false, pointPlacementAvailable: false, mode: "clean", detailsEnabled: true, unitApplied: false, duplicatesReviewed: false, mineralAccepted: false, mediaDuplicates: false, mediaPreviewFailures: 0 }));

test('selected Analyses require explicit semantics before creating an Analytical Point', async () => {
  const user = userEvent.setup();
  const onCreate = vi.fn().mockResolvedValue({ analytical_point_id: 'point-created-p01' });
  const analyses = ['epma-p01', 'la-p01'].map((analysisId, index) => ({
    analysis_id: analysisId,
    source_name: index === 0 ? 'KIV-2_EPMA.xlsx' : 'KIV-2_LA.xlsx',
    sheet_name: 'Data',
    source_row_number: index + 2,
    identity: { Analysis: `P-01-${index + 1}`, Sample: 'KIV-2', Point: 'P-01' },
    measurement_list: [{ field: index === 0 ? 'SiO2' : 'Rb', raw_token: '1', unit: index === 0 ? 'wt.%' : 'ppm', method: index === 0 ? 'EPMA' : 'LA-ICP-MS' }],
    measurements: {},
  }));

  render(<AnalysesWorkspace project={{ total: 2, source_count: 2, analyses }} busy={false} onCreateAnalyticalPoint={onCreate} />);
  const rowSelections = screen.getAllByRole('checkbox', { name: /Выбрать P-01-/ });
  await user.click(rowSelections[0]);
  expect(screen.getByRole('button', { name: 'Создать Analytical Point' }).disabled).toBe(true);
  await user.click(rowSelections[1]);
  await user.click(screen.getByRole('button', { name: 'Создать Analytical Point' }));

  expect(screen.getByRole('dialog', { name: 'Создать Analytical Point' })).toBeTruthy();
  expect(screen.getByRole('textbox', { name: 'Sample новой Analytical Point' }).value).toBe('KIV-2');
  expect(screen.getByRole('textbox', { name: 'Имя новой Analytical Point' }).value).toBe('P-01');
  await user.click(screen.getByRole('button', { name: 'Отмена' }));
  expect(onCreate).not.toHaveBeenCalled();

  await user.click(screen.getByRole('button', { name: 'Создать Analytical Point' }));
  const submit = screen.getAllByRole('button', { name: 'Создать точку' })[0];
  expect(submit.disabled).toBe(true);
  await user.selectOptions(screen.getByRole('combobox', { name: 'Тип связи Analyses' }), 'same_point');
  await user.click(screen.getByRole('checkbox', { name: /Подтверждаю, что эти 2 Analyses/ }));
  expect(submit.disabled).toBe(false);
  await user.click(submit);

  await waitFor(() => expect(onCreate).toHaveBeenCalledWith({
    sampleName: 'KIV-2',
    pointName: 'P-01',
    analysisIds: ['epma-p01', 'la-p01'],
    linkType: 'same_point',
  }));
  expect(screen.queryByRole('dialog', { name: 'Создать Analytical Point' })).toBeNull();
});

test('Analytical Point registry exposes provenance, reversible unlink and source Analyses', async () => {
  const user = userEvent.setup();
  const onRetire = vi.fn().mockResolvedValue({ analytical_point_id: 'point-stable-p01' });
  const onChangeMembership = vi.fn().mockResolvedValue({ effect: 'analysis_added' });
  const onRemovePlacement = vi.fn().mockResolvedValue({ effect: 'annotation_link_removed' });
  const onUndo = vi.fn().mockResolvedValue({ effect: 'restored' });
  const analyses = [{
    analysis_id: 'epma-p01', source_name: 'KIV-2_EPMA.xlsx', sheet_name: 'Data', source_row_number: 9,
    identity: { Analysis: 'P-01-EPMA', Sample: 'KIV-2' }, measurement_list: [{ method: 'EPMA' }], measurements: {},
  }, {
    analysis_id: 'la-p01', source_name: 'KIV-2_LA.xlsx', sheet_name: 'Trace', source_row_number: 11,
    identity: { Analysis: 'P-01-LA', Sample: 'KIV-2' }, measurement_list: [{ method: 'LA-ICP-MS' }], measurements: {},
  }, {
    analysis_id: 'epma-other', source_name: 'OTHER_EPMA.xlsx', sheet_name: 'Data', source_row_number: 4,
    identity: { Analysis: 'P-03-EPMA', Sample: 'OTHER' }, measurement_list: [{ method: 'EPMA' }], measurements: {},
  }];
  const analyticalPoints = { total: 2, sample_names: ['KIV-2', 'OTHER'], items: [{
    analytical_point_id: 'point-stable-p01', point_name: 'P-01', sample_name: 'KIV-2',
    analysis_ids: ['epma-p01', 'la-p01'], methods: ['EPMA', 'LA-ICP-MS'], link_types: ['same_point'],
    placement_count: 1, created_at: '2026-09-15T10:24:00Z', placements: [{
      spatial_annotation_id: 'annotation-stable-p01', media_asset_id: 'media-stable-bse',
      media_display_name: 'KIV-2_A_BSE_01.tif', media_type: 'BSE', thin_section_id: 'section-kiv-2-a',
      thin_section_name: 'KIV-2-A', geometry: { kind: 'point', x_px: 5710, y_px: 4876 },
      image_width_px: 8192, image_height_px: 6144, cross_sample_exception: false, exception_reason: null,
      linked_at: '2026-09-15T10:30:00Z',
    }],
  }, {
    analytical_point_id: 'point-stable-p02', point_name: 'P-02', sample_name: 'OTHER',
    analysis_ids: ['epma-p01', 'la-p01'], methods: ['EPMA'], link_types: ['same_zone'],
    placement_count: 1, created_at: '2026-09-15T10:25:00Z', placements: [{
      spatial_annotation_id: 'annotation-cross-p02', media_asset_id: 'media-kiv-2-ppl',
      media_display_name: 'KIV-2_A_PPL_01.tif', media_type: 'PPL', thin_section_id: 'section-kiv-2-a',
      thin_section_name: 'KIV-2-A', geometry: { kind: 'square', x_px: 120, y_px: 240, width_px: 30, height_px: 30 },
      image_width_px: 2048, image_height_px: 1536, cross_sample_exception: true,
      exception_reason: 'Проверено по журналу шлифа', linked_at: '2026-09-15T10:31:00Z',
    }],
  }] };

  const operation = {
    operation_id: 'operation-stable-retire', action_kind: 'analytical_point.retire', actor: 'local-desktop-user',
    entity_type: 'analytical_point', entity_ids: { analytical_point_ids: ['point-stable-p01'], analysis_ids: ['epma-p01', 'la-p01'], spatial_annotation_ids: ['annotation-stable-p01'], media_asset_ids: ['media-stable-bse'] },
    outcome: 'applied', created_at: '2026-09-15T10:40:00Z',
  };
  render(<AnalysesWorkspace
    project={{ total: 2, source_count: 2, analyses }} analyticalPoints={analyticalPoints}
    operationJournal={{ total: 1, items: [operation] }} pointOperationNotice={{ operation, message: 'Связь Analytical Point «P-01» снята.' }}
    busy={false} onRefreshAnalyticalPoints={vi.fn()} onChangeAnalyticalPointMembership={onChangeMembership} onRemoveAnalyticalPointPlacement={onRemovePlacement} onRetireAnalyticalPoint={onRetire} onUndoOperation={onUndo}
  />);
  await user.click(screen.getByRole('button', { name: /Analytical Points 2/ }));

  expect(screen.getAllByText('Та же аналитическая точка').length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Размещена/).length).toBeGreaterThan(0);
  expect(screen.getByTitle('point-stable-p01')).toBeTruthy();
  expect(screen.getByText('KIV-2_EPMA.xlsx · лист Data · строка 9')).toBeTruthy();
  expect(screen.getAllByText('Point · X 5710 · Y 4876 px').length).toBeGreaterThan(0);
  expect(screen.getByText('Изображение: 8192 × 6144 px')).toBeTruthy();
  expect(screen.getByTitle('annotation-stable-p01')).toBeTruthy();
  expect(screen.getByTitle('media-stable-bse')).toBeTruthy();
  expect(screen.getByText('Operation Journal')).toBeTruthy();
  expect(screen.getByText('2 Analyses · 1 пространственных связей')).toBeTruthy();

  await user.click(screen.getByRole('button', { name: 'Изменить состав' }));
  let compositionDialog = screen.getByRole('dialog', { name: 'Изменить состав P-01' });
  await user.selectOptions(within(compositionDialog).getByRole('combobox', { name: 'Analysis для добавления' }), 'epma-other');
  expect(within(compositionDialog).getByText(/Analysis относится к Sample «OTHER»/)).toBeTruthy();
  await user.selectOptions(within(compositionDialog).getByRole('combobox', { name: 'Тип связи добавляемой Analysis' }), 'same_zone');
  await user.type(within(compositionDialog).getByRole('textbox', { name: 'Причина изменения состава' }), 'Общая зона подтверждена на изображении');
  await user.click(within(compositionDialog).getByRole('checkbox', { name: /Подтверждаю изменение одной Analysis/ }));
  await user.click(within(compositionDialog).getByRole('button', { name: 'Добавить Analysis' }));
  await waitFor(() => expect(onChangeMembership).toHaveBeenCalledWith({
    point: analyticalPoints.items[0], action: 'add', analysisId: 'epma-other', linkType: 'same_zone', reason: 'Общая зона подтверждена на изображении',
  }));

  await user.click(screen.getByRole('button', { name: 'Изменить состав' }));
  compositionDialog = screen.getByRole('dialog', { name: 'Изменить состав P-01' });
  await user.click(within(compositionDialog).getByRole('button', { name: 'Выбрать снятие Analysis' }));
  expect(within(compositionDialog).getByText(/должны остаться минимум две Analyses/)).toBeTruthy();
  expect(within(compositionDialog).getByRole('button', { name: 'Снять Analysis' }).disabled).toBe(true);
  await user.click(within(compositionDialog).getByRole('button', { name: 'Отмена' }));

  await user.click(screen.getByRole('button', { name: 'Снять размещение' }));
  const placementDialog = screen.getByRole('dialog', { name: 'Снять размещение P-01' });
  expect(within(placementDialog).getByText(/Spatial Annotation, Media Asset, Analytical Point, Analyses и Measurements останутся/)).toBeTruthy();
  expect(within(placementDialog).getByText(/KIV-2-A · Point · X 5710 · Y 4876 px/)).toBeTruthy();
  await user.type(within(placementDialog).getByRole('textbox', { name: 'Причина снятия размещения' }), 'Метка поставлена не на ту физическую точку');
  await user.click(within(placementDialog).getByRole('checkbox', { name: /Подтверждаю снятие только показанной связи/ }));
  await user.click(within(placementDialog).getByRole('button', { name: 'Снять размещение' }));
  await waitFor(() => expect(onRemovePlacement).toHaveBeenCalledWith(
    analyticalPoints.items[0], analyticalPoints.items[0].placements[0], 'Метка поставлена не на ту физическую точку',
  ));

  await user.click(screen.getByRole('button', { name: 'Разорвать связь' }));
  const unlinkDialog = screen.getByRole('dialog', { name: 'Разорвать связь P-01' });
  expect(within(unlinkDialog).getByText(/Analyses, Measurements, Source, Spatial Annotation и Media Asset останутся/)).toBeTruthy();
  const unlinkSubmit = within(unlinkDialog).getByRole('button', { name: 'Разорвать связь' });
  expect(unlinkSubmit.disabled).toBe(true);
  await user.type(within(unlinkDialog).getByRole('textbox', { name: 'Причина разрыва связи' }), 'Связаны разные физические точки');
  await user.click(within(unlinkDialog).getByRole('checkbox', { name: /Подтверждаю снятие только этой связи/ }));
  await user.click(unlinkSubmit);
  await waitFor(() => expect(onRetire).toHaveBeenCalledWith(analyticalPoints.items[0], 'Связаны разные физические точки'));

  await user.click(screen.getByRole('button', { name: 'Отменить' }));
  expect(onUndo).toHaveBeenCalledWith('operation-stable-retire');
  await user.click(screen.getByText('P-02'));
  expect(screen.getByText('Межобразцовое исключение: Проверено по журналу шлифа')).toBeTruthy();
  expect(screen.getAllByText('Square · X 120 · Y 240 px · 30 × 30 px').length).toBeGreaterThan(0);
  await user.click(screen.getByText('P-01'));
  await user.selectOptions(screen.getByRole('combobox', { name: 'Фильтр метода Analytical Points' }), 'LA-ICP-MS');
  expect(screen.getByText('1 из 2')).toBeTruthy();

  await user.click(screen.getByRole('checkbox', { name: 'Выбрать Analytical Point P-01' }));
  expect(screen.getByText('1 Analytical Points / 2 Analyses')).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Показать исходные Analyses' }));

  expect(screen.getByRole('checkbox', { name: 'Выбрать P-01-EPMA' }).checked).toBe(true);
  expect(screen.getByRole('checkbox', { name: 'Выбрать P-01-LA' }).checked).toBe(true);
});

test('automatic matches remain pending and manual decisions require a catalog label and reason', async () => {
  const onDecide = vi.fn();
  const user = userEvent.setup();
  const analysis = {analysis_id: 'manual-1', identity: {Analysis: 'A1'}, source_name: 'test.csv', sheet_name: 'Data', source_row_number: 2,
    reported_mineral: {value: 'olivine'}, mineral_verification: {status: 'consistent', prediction: 'olivine', confidence: 'high', issues: [], candidates: []}};
  render(<MineralsWorkspace project={{total: 1, analyses: [analysis], mineral_options: ['olivine', 'forsterite']}} busy={false} onDecide={onDecide} />);
  expect(screen.getByRole('button', {name: 'Требуют решения 1'})).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Приняты пользователем 0'})).toBeTruthy();
  await user.click(screen.getByText('Назначить другой минерал'));
  await user.type(screen.getByLabelText('Минерал из справочника'), 'forsterite');
  expect(screen.getByRole('button', {name: 'Сохранить ручное назначение'}).disabled).toBe(true);
  await user.type(screen.getByLabelText('Основание назначения'), 'Проверено по независимым данным');
  await user.click(screen.getByRole('button', {name: 'Сохранить ручное назначение'}));
  expect(onDecide).toHaveBeenCalledWith(analysis, 'forsterite', 'Проверено по независимым данным');
  await user.click(screen.getByRole('button', {name: 'Приняты пользователем 0'}));
  expect(screen.queryByRole('option')).toBeNull();
});

test('mineral queue supports roving keyboard focus', async () => {
  const user = userEvent.setup();
  const analyses = ['A1', 'A2', 'A3'].map((name) => ({
    analysis_id: name,
    identity: { Analysis: name },
    mineral_verification: { status: 'conflict', prediction: null, confidence: 'unresolved', issues: [], reasons: [] },
  }));

  render(<MineralsWorkspace project={{total: 3, analyses, mineral_options: []}} busy={false} onDecide={vi.fn()} />);
  const options = screen.getAllByRole('option');

  await user.click(options[0]);
  await user.keyboard('{ArrowDown}');
  expect(document.activeElement).toBe(screen.getAllByRole('option')[1]);

  await user.keyboard('{End}');
  expect(document.activeElement).toBe(screen.getAllByRole('option')[2]);

  await user.keyboard('{Home}');
  expect(document.activeElement).toBe(screen.getAllByRole('option')[0]);
});

test('stale decisions and missing inputs are visible even when rule reasons exist', () => {
  render(<MineralsWorkspace project={{total: 1, analyses: [{analysis_id: 'stale-1', identity: {Analysis: 'A2'},
    mineral_verification: {status: 'stale_assignment', prediction: 'olivine', confidence: 'high',
      issues: ['accepted_assignment_stale'], reasons: ['core_oxides_available'], missing_components: ['K2O'], excluded_inputs: ['F']}}]}} />);
  expect(screen.getByText(/Ранее принятое решение устарело/)).toBeTruthy();
  expect(screen.getByText(/не хватает: K2O/)).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Сбросить решение'})).toBeTruthy();
});

vi.mock("../src/desktopApi", () => {
  const recipe = {
    sections: [{
      block_id: "clean-data",
      sheet_name: "Data",
      header_row: 1,
      orientation: "rows_are_analyses",
      enabled: true,
      mappings: [],
    }],
    global_decisions: {},
  };
  const plan = {
    summary: {
      planned_analysis_count: 2,
      planned_measurement_count: 6,
      enabled_block_count: 1,
      duplicate_candidate_groups: 0,
    },
    warnings: [],
    planned_records: [
      { preview_id: "UI-1", sheet_name: "Data", row_number: 2, orientation: "rows_are_analyses", identity: ["UI-1"], measurements: [{ field: "SiO2", raw_token: "40.1", unit: "wt.%" }] },
      { preview_id: "UI-2", sheet_name: "Data", row_number: 3, orientation: "rows_are_analyses", identity: ["UI-2"], measurements: [{ field: "SiO2", raw_token: "39.8", unit: "wt.%" }] },
    ],
  };
  const complexRecords = [
    { preview_id: "C-1", sheet_name: "Summary", row_number: 3, orientation: "rows_are_analyses", identity: ["Spectrum 1"], measurements: [{ field: "SiO2", raw_token: "40.1", unit: "wt.%" }] },
    { preview_id: "C-2", sheet_name: "Summary", row_number: 4, orientation: "rows_are_analyses", identity: ["Spectrum 1"], measurements: [{ field: "SiO2", raw_token: "39.8", unit: "wt.%" }] },
  ];
  const complexWarnings = [
    { code: "UNIT_REQUIRES_REVIEW", blocking: true, sheet_name: "Summary", block_id: "summary-main", source_axis: "column", source_column_index: 1, source_header: "SiO2", canonical_field: "SiO2" },
    { code: "UNMAPPED_FIELD_REQUIRES_REVIEW", blocking: true, sheet_name: "Details", block_id: "details-1", source_axis: "column", source_column_index: 1, source_header: "Sigma" },
    { code: "UNMAPPED_FIELD_REQUIRES_REVIEW", blocking: true, sheet_name: "Details", block_id: "details-2", source_axis: "column", source_column_index: 1, source_header: "Sigma" },
  ];
  const complexCleanReasons = [
    { code: "CLEAN_TABLE_BLANK_HEADER", sheet_name: "Summary", source_axis: "column", source_column_index: 4 },
    { code: "CLEAN_TABLE_BLANK_HEADER", sheet_name: "Summary", source_axis: "column", source_column_index: 5 },
    { code: "CLEAN_TABLE_BLANK_HEADER", sheet_name: "Summary", source_axis: "column", source_column_index: 6 },
  ];
  const currentComplexRecipe = () => ({
    sections: [{
      block_id: "summary-main",
      sheet_name: "Summary",
      header_row: 2,
      data_start_row: 3,
      data_end_row: 4,
      orientation: "rows_are_analyses",
      enabled: true,
      mappings: [
        { source_axis: "column", source_column_index: 0, source_header: "Analysis", target_role: "identity", canonical_field: "Analysis", review_decision: "recognized" },
        uiState.unitApplied
          ? { source_axis: "column", source_column_index: 1, source_header: "SiO2", target_role: "measurement", canonical_field: "SiO2", unit: "wt.%", review_decision: "assigned" }
          : { source_axis: "column", source_column_index: 1, source_header: "SiO2", target_role: "ignore", canonical_field: "SiO2", suggested_target: "measurement", suggested_canonical_field: "SiO2", review_decision: "unresolved" },
      ],
    }, ...[1, 2].map((index) => ({
      block_id: `details-${index}`,
      sheet_name: "Details",
      header_row: index === 1 ? 2 : 10,
      data_start_row: index === 1 ? 3 : 11,
      data_end_row: index === 1 ? 8 : 16,
      orientation: "rows_are_analyses",
      enabled: uiState.detailsEnabled,
      mappings: [
        { source_axis: "column", source_column_index: 0, source_header: `Spectrum ${index}`, target_role: "identity", canonical_field: "Analysis", review_decision: "recognized" },
        { source_axis: "column", source_column_index: 1, source_header: "Sigma", target_role: "ignore", canonical_field: "Sigma", review_decision: "unresolved" },
      ],
    }))],
    global_decisions: uiState.duplicatesReviewed ? {
      duplicate_policy: "keep_all",
      duplicate_review: { decision: "keep_all", candidate_group_count: 1 },
    } : {},
  });
  const complexPlan = () => ({
    summary: {
      planned_analysis_count: 2,
      planned_measurement_count: uiState.unitApplied ? 2 : 0,
      enabled_block_count: uiState.detailsEnabled ? 3 : 1,
      duplicate_candidate_groups: uiState.unitApplied ? 1 : 0,
    },
    warnings: uiState.unitApplied ? [{ code: "DUPLICATE_CANDIDATES", preview_ids: [["C-1", "C-2"]] }] : [],
    planned_records: uiState.unitApplied ? complexRecords : [],
  });
  const emptyProject = { total: 0, source_count: 0, import_batch_count: 0, latest_import: null, analyses: [] };
  const measurementList = Array.from({ length: 16 }, (_, index) => ({
    field: index === 0 ? "SiO2" : `Trace-${index}`,
    raw_token: index === 0 ? "40.1" : String(index / 10),
    unit: index === 0 ? "wt.%" : "ppm",
    source_header: index === 0 ? "SiO2 wt.%" : `Trace-${index} ppm`,
    source_cell: `${String.fromCharCode(67 + index)}2`,
    method: index === 0 ? "EPMA" : "LA-ICP-MS",
  }));
  const importedProject = {
    total: 2,
    returned: 2,
    offset: 0,
    has_more: false,
    source_count: 1,
    import_batch_count: 1,
    latest_import: null,
    analyses: [{
      analysis_id: "analysis-ui-1",
      source_name: "Windows UI smoke",
      sheet_name: "Data",
      source_row_number: 2,
      source_orientation: "rows_are_analyses",
      identity: { Analysis: "UI-1", Sample: "KIV-2" },
      source_metadata: {},
      measurements: Object.fromEntries(measurementList.map((item) => [item.field, item])),
      measurement_list: measurementList,
    }, {
      analysis_id: "analysis-ui-2",
      source_name: "Windows UI smoke",
      sheet_name: "Data",
      source_row_number: 3,
      source_orientation: "rows_are_analyses",
      identity: { Analysis: "UI-2", Sample: "KIV-3" },
      source_metadata: { Comment: "control" },
      measurements: { SiO2: { raw_token: "39.8", unit: "wt.%", source_cell: "C3" } },
    }],
  };
  const mediaInspection = {
    items: ["BSE", "PPL", "XPL"].map((type) => ({
      source_path: `C:/fixtures/KIV-2_A_${type}_01.tif`,
      display_name: `KIV-2_A_${type}_01.tif`,
      source_fingerprint: `fingerprint-${type}`,
      mime_type: "image/tiff",
      format: "tiff",
      width_px: 640,
      height_px: 480,
      suggested_media_type: type,
      suggested_sample_name: "KIV-2",
      suggested_thin_section_name: "KIV-2-A",
      suggestion_basis: ["filename_modality_token", "filename_prefix", "filename_section_prefix"],
    })),
    duplicate_groups: [],
  };
  const analyticalPoints = {
    total: 2,
    sample_names: ["KIV-2", "OTHER"],
    items: [{
      analytical_point_id: "point-kiv-2-p07",
      point_name: "P-07",
      sample_id: "sample-kiv-2",
      sample_name: "KIV-2",
      analysis_ids: ["analysis-ui-1", "analysis-la-87"],
      analysis_members: [
        { analysis_id: "analysis-ui-1", method: "EPMA", source_name: "Windows UI smoke", sheet_name: "Data", source_row_number: 2, source_orientation: "rows_are_analyses" },
        { analysis_id: "analysis-la-87", method: "LA-ICP-MS", source_name: "KIV-2_LA.csv", sheet_name: "Trace", source_row_number: 87, source_orientation: "rows_are_analyses" },
      ],
      methods: ["EPMA", "LA-ICP-MS"],
      link_types: ["same_point"],
      placement_count: 0,
      created_at: "2026-09-15T10:24:00Z",
    }, {
      analytical_point_id: "point-other-p03",
      point_name: "P-03",
      sample_id: "sample-other",
      sample_name: "OTHER",
      analysis_ids: ["analysis-other-3"],
      methods: ["EPMA"],
      link_types: ["same_zone"],
      placement_count: 0,
      created_at: "2026-09-15T10:25:00Z",
    }],
  };
  const api = {
    isPetrolabDesktop: () => true,
    getProjectDatabasePath: vi.fn().mockResolvedValue("C:/PetroLab/project.sqlite"),
    listProjectAnalyses: vi.fn().mockImplementation(async (_path, _limit, _offset, analysisIds) => {
      const project = uiState.imported ? importedProject : emptyProject;
      if (!Array.isArray(analysisIds)) return { result: project };
      const requested = analysisIds.map((analysisId) => analysisId === "analysis-la-87" ? {
        analysis_id: "analysis-la-87", source_name: "KIV-2_LA.csv", sheet_name: "Trace", source_row_number: 87,
        source_orientation: "rows_are_analyses", identity: { Analysis: "P-07-LA", Sample: "KIV-2" }, source_metadata: {}, measurements: {}, measurement_list: [{ method: "LA-ICP-MS" }],
      } : project.analyses.find((analysis) => analysis.analysis_id === analysisId)).filter(Boolean);
      return { result: { ...project, total: requested.length, returned: requested.length, has_more: false, analyses: requested } };
    }),
    listProjectMineralIdentifications: vi.fn().mockImplementation(async () => {
      const analyses = uiState.imported ? importedProject.analyses : [];
      return { result: {
        total: analyses.length,
        returned: analyses.length,
        offset: 0,
        has_more: false,
        identifications: analyses.map((analysis, index) => ({
          analysis_id: analysis.analysis_id,
          source_id: "source-ui",
          source_name: analysis.source_name,
          sheet_name: analysis.sheet_name,
          source_row_number: analysis.source_row_number,
          status: index === 0 ? (uiState.mineralAccepted ? "verified" : "conflict") : "insufficient_input",
          reported_mineral: index === 0 ? "garnet" : null,
          reported_target: index === 0 ? "garnet" : null,
          prediction: index === 0 ? "clinopyroxene" : null,
          confidence: index === 0 ? "high" : "insufficient_input",
          input_fingerprint: `fingerprint-${analysis.analysis_id}`,
          accepted: index === 0 && uiState.mineralAccepted ? { target: "clinopyroxene", decision_kind: "accept_suggestion" } : null,
          candidates: index === 0 ? [{ target: "clinopyroxene", score: 9 }, { target: "garnet", score: 5 }] : [],
          reasons: index === 0 ? ["Ca-Mg-Fe pyroxene chemistry"] : [],
          ruleset_version: "test-ruleset",
        })),
        status_counts: analyses.length ? { [uiState.mineralAccepted ? "verified" : "conflict"]: 1, insufficient_input: Math.max(0, analyses.length - 1) } : {},
      } };
    }),
    decideProjectMineralAssignment: vi.fn().mockImplementation(async (_path, analysisId, verification, target) => {
      uiState.mineralAccepted = Boolean(target);
      return { result: { analysis_id: analysisId, decision: target ? { target } : null, verification } };
    }),
    pickImportFile: vi.fn().mockImplementation(async () => uiState.mode === "clean" ? "C:/fixtures/ui-clean-table.csv" : "C:/fixtures/complex-workbook.xlsx"),
    pickMediaFiles: vi.fn().mockResolvedValue(mediaInspection.items.map((item) => item.source_path)),
    pickMediaFolder: vi.fn().mockResolvedValue(mediaInspection.items.map((item) => item.source_path)),
    inspectMediaSources: vi.fn().mockImplementation(async () => ({ result: {
      ...mediaInspection,
      duplicate_groups: uiState.mediaDuplicates ? [[
        "C:/fixtures/KIV-2_A_BSE_01.tif",
        "C:/fixtures/KIV-2_A_PPL_01.tif",
      ]] : [],
    } })),
    listAnalyticalPoints: vi.fn().mockImplementation(async () => {
      const activeItems = analyticalPoints.items
        .filter((point) => !uiState.pointRetired || point.analytical_point_id !== 'point-kiv-2-p07')
        .map((point) => point.analytical_point_id === 'point-kiv-2-p07' && uiState.pointPlacementAvailable ? { ...point, placement_count: 1, placements: [{
          spatial_annotation_id: 'annotation-ui-p07', media_asset_id: 'media-ui-bse', media_display_name: 'KIV-2_A_BSE_01.tif', media_type: 'BSE',
          thin_section_id: 'section-ui-kiv-2-a', thin_section_name: 'KIV-2-A', geometry: { kind: 'point', x_px: 320, y_px: 240 },
          image_width_px: 640, image_height_px: 480, cross_sample_exception: false, exception_reason: null,
        }] } : point);
      return { result: uiState.pointCreated ? {
      ...analyticalPoints,
      total: activeItems.length + 1,
      items: [...activeItems, {
        analytical_point_id: 'point-created', sample_id: 'sample-created', sample_name: 'KIV-2', point_name: 'P-01',
        analysis_ids: ['analysis-ui-1', 'analysis-ui-2'], methods: ['EPMA'], link_types: ['same_zone'], placement_count: 0,
        created_at: '2026-09-15T10:26:00Z',
      }],
    } : { ...analyticalPoints, total: activeItems.length, items: activeItems } };
    }),
    listOperationJournal: vi.fn().mockImplementation(async () => ({ result: uiState.pointRetired ? { total: 1, items: [{
      operation_id: 'operation-retire-p07', action_kind: 'analytical_point.retire', actor: 'local-desktop-user', entity_type: 'analytical_point',
      entity_ids: { analytical_point_ids: ['point-kiv-2-p07'], analysis_ids: ['analysis-ui-1', 'analysis-la-87'], spatial_annotation_ids: [], media_asset_ids: [] },
      parameters: { reason: 'Связаны разные физические точки', point_name: 'P-07', sample_name: 'KIV-2' }, outcome: 'applied', created_at: '2026-09-15T10:40:00Z',
    }] } : { total: 0, items: [] } })),
    createAnalyticalPoint: vi.fn().mockImplementation(async (_path, sampleName, pointName, analysisIds, linkType) => {
      uiState.pointCreated = true;
      return { result: {
        analytical_point_id: 'point-created',
        sample_id: 'sample-created',
        sample_name: sampleName,
        point_name: pointName,
        analysis_ids: analysisIds,
        link_type: linkType,
      } };
    }),
    addAnalysisToAnalyticalPoint: vi.fn().mockImplementation(async (_path, point, analysisId, linkType, reason) => ({ result: {
      analytical_point_id: point.analytical_point_id, analysis_id: analysisId,
      analysis_ids: [...point.analysis_ids, analysisId], link_type: linkType, effect: 'analysis_added',
      operation: {
        operation_id: 'operation-add-analysis', action_kind: 'analytical_point.analysis.add', actor: 'local-desktop-user', entity_type: 'analytical_point',
        entity_ids: { analytical_point_ids: [point.analytical_point_id], analysis_ids: [...point.analysis_ids, analysisId], spatial_annotation_ids: [], media_asset_ids: [] },
        parameters: { reason, analysis_id: analysisId, link_type: linkType, point_name: point.point_name, sample_name: point.sample_name }, outcome: 'applied', created_at: '2026-09-15T10:38:00Z',
      },
    } })),
    removeAnalysisFromAnalyticalPoint: vi.fn().mockImplementation(async (_path, point, analysisId, reason) => ({ result: {
      analytical_point_id: point.analytical_point_id, analysis_id: analysisId,
      analysis_ids: point.analysis_ids.filter((id) => id !== analysisId), effect: 'analysis_removed',
      operation: {
        operation_id: 'operation-remove-analysis', action_kind: 'analytical_point.analysis.remove', actor: 'local-desktop-user', entity_type: 'analytical_point',
        entity_ids: { analytical_point_ids: [point.analytical_point_id], analysis_ids: point.analysis_ids.filter((id) => id !== analysisId), spatial_annotation_ids: [], media_asset_ids: [] },
        parameters: { reason, analysis_id: analysisId, point_name: point.point_name, sample_name: point.sample_name }, outcome: 'applied', created_at: '2026-09-15T10:39:00Z',
      },
    } })),
    removeSpatialAnnotationFromAnalyticalPoint: vi.fn().mockImplementation(async (_path, point, spatialAnnotationId, reason) => {
      uiState.pointPlacementAvailable = false;
      return { result: {
        analytical_point_id: point.analytical_point_id, spatial_annotation_id: spatialAnnotationId, media_asset_id: 'media-ui-bse',
        spatial_annotation_ids: [], effect: 'annotation_link_removed', operation: {
          operation_id: 'operation-remove-annotation', action_kind: 'analytical_point.annotation.remove', actor: 'local-desktop-user', entity_type: 'analytical_point',
          entity_ids: { analytical_point_ids: [point.analytical_point_id], analysis_ids: point.analysis_ids, spatial_annotation_ids: [], media_asset_ids: [] },
          parameters: { reason, spatial_annotation_id: spatialAnnotationId, media_asset_id: 'media-ui-bse', point_name: point.point_name, sample_name: point.sample_name }, outcome: 'applied', created_at: '2026-09-15T10:39:30Z',
        },
      } };
    }),
    retireAnalyticalPoint: vi.fn().mockImplementation(async (_path, point, reason) => {
      uiState.pointRetired = true;
      return { result: { analytical_point_id: point.analytical_point_id, sample_name: point.sample_name, point_name: point.point_name, operation: {
        operation_id: 'operation-retire-p07', action_kind: 'analytical_point.retire', actor: 'local-desktop-user', entity_type: 'analytical_point',
        entity_ids: { analytical_point_ids: [point.analytical_point_id], analysis_ids: point.analysis_ids, spatial_annotation_ids: [], media_asset_ids: [] },
        parameters: { reason, point_name: point.point_name, sample_name: point.sample_name }, outcome: 'applied', created_at: '2026-09-15T10:40:00Z',
      } } };
    }),
    undoOperation: vi.fn().mockImplementation(async (_path, operationId) => {
      uiState.pointRetired = false;
      if (operationId === 'operation-remove-annotation') uiState.pointPlacementAvailable = true;
      const effect = operationId === 'operation-add-analysis' ? 'analysis_removed' : operationId === 'operation-remove-annotation' ? 'annotation_link_restored' : 'restored';
      return { result: { target_operation_id: operationId, analytical_point_id: 'point-kiv-2-p07', effect, operation: { operation_id: 'operation-undo-p07', action_kind: 'operation.undo' } } };
    }),
    getMediaPreview: vi.fn().mockImplementation(async (sourcePath) => {
      if (uiState.mediaPreviewFailures > 0) {
        uiState.mediaPreviewFailures -= 1;
        throw new Error("Временный сбой preview.");
      }
      return { result: {
        source_path: sourcePath,
        source_fingerprint: mediaInspection.items.find((item) => item.source_path === sourcePath).source_fingerprint,
        source_width_px: 640,
        source_height_px: 480,
        preview_width_px: 640,
        preview_height_px: 480,
        preview_data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
      } };
    }),
    createMediaImportPlan: vi.fn().mockImplementation(async (_path, assignments) => {
      uiState.mediaPlacementCount = assignments.reduce((count, assignment) => count + assignment.placements.length, 0);
      return { result: {
        schema_version: 1,
        semantic_fingerprint: "media-plan",
        items: assignments.map((assignment, index) => ({
          ...mediaInspection.items[index],
          ...assignment,
          media_asset_id: `asset-${index}`,
          existing_media_asset_id: null,
          placements: assignment.placements.map((placement, placementIndex) => {
            const point = analyticalPoints.items.find((item) => item.analytical_point_id === placement.analytical_point_id);
            return { ...placement, spatial_annotation_id: `annotation-${index}-${placementIndex}`, point_name: point.point_name, point_sample_name: point.sample_name };
          }),
        })),
        warnings: assignments.filter((assignment) => assignment.placements.length === 0).map((assignment) => ({ code: "UNPLACED_MEDIA", message: `${assignment.source_path} has no placed Analytical Points.` })),
      } };
    }),
    applyMediaImportPlan: vi.fn().mockImplementation(async () => {
      uiState.mediaImported = true;
      return { result: { created_media_asset_count: 3, reused_media_asset_count: 0, spatial_annotation_count: uiState.mediaPlacementCount } };
    }),
    stageImportFile: vi.fn().mockImplementation(async (path) => ({ local_path: `C:/PetroLab/staging/${path.split("/").pop()}`, original_path: path })),
    clearImportStaging: vi.fn().mockResolvedValue(undefined),
    inspectImportSource: vi.fn().mockImplementation(async () => ({ result: uiState.mode === "clean"
      ? { source_format: "csv", source_fingerprint: "0123456789abcdef", sheets: [{ name: "Data" }] }
      : { source_format: "xlsx", source_fingerprint: "fedcba9876543210", sheets: [{ name: "Summary" }, { name: "Details" }] } })),
    classifyCleanTable: vi.fn().mockImplementation(async () => ({ result: uiState.mode === "clean"
      ? { mode: "clean_table_fast", clean_table_version: "1", recipe, sections: [{ sheet_name: "Data", analysis_fields: ["Analysis"], measurements: [{ field: "SiO2", unit: "wt.%" }] }], ignored_helper_sheets: [] }
      : { mode: "raw_review", reasons: complexCleanReasons } })),
    suggestImportRecipe: vi.fn().mockImplementation(async () => ({ result: { recipe: currentComplexRecipe(), warnings: complexWarnings } })),
    createImportPlan: vi.fn().mockImplementation(async () => ({ result: uiState.mode === "clean" ? plan : complexPlan() })),
    getImportBulkUnitScopes: vi.fn().mockImplementation(async () => ({ result: { scopes: uiState.unitApplied ? [] : [{ bulk_scope_id: "summary-unit", block_count: 1, field_count: 1, fields: ["SiO2"], sheet_names: ["Summary"], targets: [{ block_id: "summary-main", source_axis: "column", source_index: 1 }] }] } })),
    getImportBulkIgnoreScopes: vi.fn().mockImplementation(async () => ({ result: { scopes: uiState.detailsEnabled ? [{ bulk_scope_id: "details-ignore", block_count: 2, field_count: 2, fields: ["Sigma"], sheet_names: ["Details"] }] : [] } })),
    applyImportBulkIgnore: vi.fn(),
    applyImportBulkUnit: vi.fn().mockImplementation(async () => {
      uiState.unitApplied = true;
      return { result: { recipe: currentComplexRecipe(), applied_decision_count: 1 } };
    }),
    reviseImportSections: vi.fn().mockImplementation(async (_path, _recipe, decisions) => {
      if (decisions.some((decision) => decision.block_id.startsWith("details-") && decision.enabled === false)) uiState.detailsEnabled = false;
      return { result: { recipe: currentComplexRecipe() } };
    }),
    previewImportWindow: vi.fn().mockImplementation(async (_path, sheetName, startRow = 1) => ({ result: {
      source_path: "C:/PetroLab/staging/complex-workbook.xlsx",
      sheet_name: sheetName,
      start_row: startRow,
      end_row: startRow + 2,
      start_column: 0,
      end_column: 3,
      column_labels: ["A", "B", "C"],
      used_range: { rows: 20, columns: 3 },
      rows: [0, 1, 2].map((offset) => ({ row_number: startRow + offset, values: offset === 0 ? ["Analysis", "SiO2", "Sigma"] : [`Spectrum ${offset}`, "40.1", "0.2"] })),
    } })),
    reviewImportDuplicates: vi.fn().mockImplementation(async () => {
      uiState.duplicatesReviewed = true;
      return { result: { recipe: currentComplexRecipe(), plan: complexPlan(), duplicate_review: { candidate_group_count: 1 } } };
    }),
    applyImportPlan: vi.fn().mockImplementation(async () => {
      uiState.imported = true;
      return { result: { analysis_count: 2, measurement_count: 6, source_metadata_count: 0 } };
    }),
    reviseImportMappings: vi.fn(),
    retractLastImport: vi.fn(),
  };
  let sourceDescriptor;
  let revision = 0;
  let selectedBlock = "";
  const projectWorkspace = async () => {
    const classification = (await api.classifyCleanTable()).result;
    const currentRecipe = uiState.mode === "clean" ? recipe : currentComplexRecipe();
    const currentPlan = (await api.createImportPlan()).result;
    const source = { source_id: "source-1", ...sourceDescriptor, included: true, sheets: [] };
    const problems = [...(currentPlan.issues || []), ...(currentPlan.warnings || []),
      ...(uiState.mode === "clean" ? [] : complexCleanReasons),
      ...(uiState.mode === "clean" ? [] : complexWarnings.filter(w => w.code === "UNIT_REQUIRES_REVIEW" ? !uiState.unitApplied : uiState.detailsEnabled))];
    return { result: {
      session: { workspace_id: "workspace-1", draft_revision: revision, active_source_id: "source-1",
        active_block_id: selectedBlock || currentRecipe.sections[0].block_id, sources: [source],
        issues: problems.map((item, index) => ({ issue_id: String(index), code: item.code, source_id: "source-1", message_params: item, blocking: item.blocking || false,
          bulk_scope_id: item.code === "UNIT_REQUIRES_REVIEW" && !uiState.unitApplied
            ? "summary-unit"
            : item.code === "UNMAPPED_FIELD_REQUIRES_REVIEW" && uiState.detailsEnabled ? "details-ignore" : null })),
        readiness: { ready_to_commit: currentPlan.ready_to_commit !== false && (uiState.mode === "clean" || (uiState.unitApplied && !uiState.detailsEnabled && uiState.duplicatesReviewed)) },
      },
      active: { source_id: "source-1", inspection: (await api.inspectImportSource()).result, recipe: currentRecipe,
        plan: currentPlan, classification, issues: problems, decisions: [],
        bulk_unit_scopes: uiState.mode === "clean" ? [] : (await api.getImportBulkUnitScopes()).result.scopes,
        bulk_ignore_scopes: uiState.mode === "clean" ? [] : (await api.getImportBulkIgnoreScopes()).result.scopes,
      },
    } };
  };
  api.createImportWorkspace = vi.fn(async (sources) => {
    sourceDescriptor = sources[0]; revision = 0; selectedBlock = "";
    return projectWorkspace();
  });
  api.addWorkspaceSources = vi.fn();
  api.getImportWorkspace = vi.fn(projectWorkspace);
  api.discardImportWorkspace = vi.fn(async () => ({ result: { staged_paths: [sourceDescriptor.staged_path] } }));
  api.previewWorkspaceWindow = vi.fn(async (_workspace, _source, sheetName, startRow, rows, column, columns) =>
    api.previewImportWindow(sourceDescriptor.staged_path, sheetName, startRow, rows, column, columns));
  api.applyWorkspaceDecision = vi.fn(async (_workspace, _revision, _source, decision) => {
    if (decision.kind === "sections") await api.reviseImportSections(null, null, decision.decisions);
    if (decision.kind === "unit") await api.applyImportBulkUnit();
    if (decision.kind === "duplicates") await api.reviewImportDuplicates();
    if (decision.kind === "activate") selectedBlock = decision.block_id || selectedBlock;
    revision += 1;
    return projectWorkspace();
  });
  return api;

});

import { addAnalysisToAnalyticalPoint, applyImportPlan, applyMediaImportPlan, applyWorkspaceDecision, createAnalyticalPoint, createMediaImportPlan, createImportPlan, getMediaPreview, listAnalyticalPoints, listProjectAnalyses, pickImportFile, pickMediaFolder, removeSpatialAnnotationFromAnalyticalPoint, retireAnalyticalPoint, undoOperation } from "../src/desktopApi";
import { App } from "../src/App";
import { ImagesWorkspace } from "../src/ImagesWorkspace";

afterEach(() => {
  uiState.imported = false;
  uiState.mediaImported = false;
  uiState.mediaPlacementCount = 0;
  uiState.pointCreated = false;
  uiState.pointRetired = false;
  uiState.pointPlacementAvailable = false;
  uiState.mode = "clean";
  uiState.detailsEnabled = true;
  uiState.unitApplied = false;
  uiState.duplicatesReviewed = false;
  uiState.mineralAccepted = false;
  uiState.mediaDuplicates = false;
  uiState.mediaPreviewFailures = 0;
  vi.clearAllMocks();
  cleanup();
});

test('App persists an explicitly confirmed Analytical Point and refreshes its projection', async () => {
  uiState.imported = true;
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole('button', { name: 'Анализы' }));
  await user.click(await screen.findByRole('checkbox', { name: 'Выбрать UI-1' }));
  await user.click(screen.getByRole('checkbox', { name: 'Выбрать UI-2' }));
  await user.click(screen.getByRole('button', { name: 'Создать Analytical Point' }));
  expect(screen.getByText(/В исходных данных указаны разные Sample: KIV-2, KIV-3/)).toBeTruthy();
  await user.type(screen.getByRole('textbox', { name: 'Sample новой Analytical Point' }), 'KIV-2');
  await user.type(screen.getByRole('textbox', { name: 'Имя новой Analytical Point' }), 'P-01');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Тип связи Analyses' }), 'same_zone');
  await user.click(screen.getByRole('checkbox', { name: /Подтверждаю, что эти 2 Analyses/ }));
  await user.click(screen.getByRole('button', { name: 'Создать точку' }));

  await waitFor(() => expect(createAnalyticalPoint).toHaveBeenCalledWith(
    'C:/PetroLab/project.sqlite',
    'KIV-2',
    'P-01',
    ['analysis-ui-1', 'analysis-ui-2'],
    'same_zone',
  ));
  await waitFor(() => expect(listAnalyticalPoints).toHaveBeenCalledWith('C:/PetroLab/project.sqlite'));
  expect(await screen.findByText(/Analytical Point «P-01» создана из 2 Analyses/)).toBeTruthy();
});

test('App does not invite a duplicate create when the point projection refresh fails', async () => {
  uiState.imported = true;
  listAnalyticalPoints.mockResolvedValueOnce({ result: { total: 2, sample_names: ['KIV-2', 'OTHER'], items: [] } }).mockRejectedValueOnce(new Error('Временный сбой списка.'));
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole('button', { name: 'Анализы' }));
  await user.click(await screen.findByRole('checkbox', { name: 'Выбрать UI-1' }));
  await user.click(screen.getByRole('checkbox', { name: 'Выбрать UI-2' }));
  await user.click(screen.getByRole('button', { name: 'Создать Analytical Point' }));
  await user.type(screen.getByRole('textbox', { name: 'Sample новой Analytical Point' }), 'KIV-2');
  await user.type(screen.getByRole('textbox', { name: 'Имя новой Analytical Point' }), 'P-01');
  await user.selectOptions(screen.getByRole('combobox', { name: 'Тип связи Analyses' }), 'same_zone');
  await user.click(screen.getByRole('checkbox', { name: /Подтверждаю, что эти 2 Analyses/ }));
  await user.click(screen.getByRole('button', { name: 'Создать точку' }));

  expect(await screen.findByText(/Analytical Point «P-01» создана из 2 Analyses/)).toBeTruthy();
  expect(screen.getByText(/создана, но обновить список точек не удалось: Временный сбой списка/)).toBeTruthy();
  expect(screen.queryByRole('dialog', { name: 'Создать Analytical Point' })).toBeNull();
  expect(createAnalyticalPoint).toHaveBeenCalledTimes(1);
});

test('App retires one exact Analytical Point scope and restores it through Operation Journal', async () => {
  uiState.imported = true;
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole('button', { name: 'Анализы' }));
  await user.click(await screen.findByRole('button', { name: /Analytical Points 2/ }));
  await user.click(screen.getByRole('button', { name: 'Разорвать связь' }));
  const dialog = screen.getByRole('dialog', { name: 'Разорвать связь P-07' });
  await user.type(within(dialog).getByRole('textbox', { name: 'Причина разрыва связи' }), 'Связаны разные физические точки');
  await user.click(within(dialog).getByRole('checkbox', { name: /Подтверждаю снятие только этой связи/ }));
  await user.click(within(dialog).getByRole('button', { name: 'Разорвать связь' }));

  await waitFor(() => expect(retireAnalyticalPoint).toHaveBeenCalledWith(
    'C:/PetroLab/project.sqlite',
    expect.objectContaining({ analytical_point_id: 'point-kiv-2-p07', analysis_ids: ['analysis-ui-1', 'analysis-la-87'] }),
    'Связаны разные физические точки',
  ));
  expect(await screen.findByText(/Связь «P-07» снята обратимо/)).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Отменить' }));
  await waitFor(() => expect(undoOperation).toHaveBeenCalledWith('C:/PetroLab/project.sqlite', 'operation-retire-p07'));
  expect(await screen.findByText('Связь Analytical Point восстановлена по устойчивым ID.')).toBeTruthy();
  expect((await screen.findAllByText('P-07')).length).toBeGreaterThan(0);
});

test('App changes one Analytical Point membership and exposes immediate undo', async () => {
  uiState.imported = true;
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole('button', { name: 'Анализы' }));
  await user.click(await screen.findByRole('button', { name: /Analytical Points 2/ }));
  await user.click(screen.getByRole('button', { name: 'Изменить состав' }));
  const dialog = screen.getByRole('dialog', { name: 'Изменить состав P-07' });
  await user.selectOptions(within(dialog).getByRole('combobox', { name: 'Analysis для добавления' }), 'analysis-ui-2');
  await user.selectOptions(within(dialog).getByRole('combobox', { name: 'Тип связи добавляемой Analysis' }), 'same_zone');
  await user.type(within(dialog).getByRole('textbox', { name: 'Причина изменения состава' }), 'Общая зона подтверждена на BSE');
  await user.click(within(dialog).getByRole('checkbox', { name: /Подтверждаю изменение одной Analysis/ }));
  await user.click(within(dialog).getByRole('button', { name: 'Добавить Analysis' }));

  await waitFor(() => expect(addAnalysisToAnalyticalPoint).toHaveBeenCalledWith(
    'C:/PetroLab/project.sqlite',
    expect.objectContaining({ analytical_point_id: 'point-kiv-2-p07', analysis_ids: ['analysis-ui-1', 'analysis-la-87'] }),
    'analysis-ui-2',
    'same_zone',
    'Общая зона подтверждена на BSE',
  ));
  expect(await screen.findByText(/Состав «P-07» изменён обратимо: теперь 3 Analyses/)).toBeTruthy();
  await user.click(screen.getByRole('button', { name: 'Отменить' }));
  await waitFor(() => expect(undoOperation).toHaveBeenCalledWith('C:/PetroLab/project.sqlite', 'operation-add-analysis'));
  expect(await screen.findByText('Добавление Analysis отменено; исходная Analysis сохранена.')).toBeTruthy();
});

test('App removes one saved spatial link and restores it through Operation Journal', async () => {
  uiState.imported = true;
  uiState.pointPlacementAvailable = true;
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole('button', { name: 'Анализы' }));
  await user.click(await screen.findByRole('button', { name: /Analytical Points 2/ }));
  await user.click(screen.getByRole('button', { name: 'Снять размещение' }));
  const dialog = screen.getByRole('dialog', { name: 'Снять размещение P-07' });
  await user.type(within(dialog).getByRole('textbox', { name: 'Причина снятия размещения' }), 'Метка поставлена не на ту физическую точку');
  await user.click(within(dialog).getByRole('checkbox', { name: /Подтверждаю снятие только показанной связи/ }));
  await user.click(within(dialog).getByRole('button', { name: 'Снять размещение' }));

  await waitFor(() => expect(removeSpatialAnnotationFromAnalyticalPoint).toHaveBeenCalledWith(
    'C:/PetroLab/project.sqlite',
    expect.objectContaining({ analytical_point_id: 'point-kiv-2-p07' }),
    'annotation-ui-p07',
    'Метка поставлена не на ту физическую точку',
  ));
  expect(await screen.findByText(/Размещение «KIV-2_A_BSE_01.tif» снято обратимо/)).toBeTruthy();
  expect(screen.getAllByText('Без изображения').length).toBeGreaterThan(0);
  await user.click(screen.getByRole('button', { name: 'Отменить' }));
  await waitFor(() => expect(undoOperation).toHaveBeenCalledWith('C:/PetroLab/project.sqlite', 'operation-remove-annotation'));
  expect(await screen.findByText('Пространственная связь восстановлена по устойчивым ID.')).toBeTruthy();
  expect((await screen.findAllByText(/Размещена/)).length).toBeGreaterThan(0);
});

test('App loads every selected source Analysis by ID before leaving the point registry', async () => {
  uiState.imported = true;
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole('button', { name: 'Анализы' }));
  await user.click(await screen.findByRole('button', { name: /Analytical Points 2/ }));
  await user.click(screen.getByRole('checkbox', { name: 'Выбрать Analytical Point P-07' }));
  await user.click(screen.getByRole('button', { name: 'Показать исходные Analyses' }));

  await waitFor(() => expect(listProjectAnalyses).toHaveBeenLastCalledWith(
    'C:/PetroLab/project.sqlite', 2, 0, ['analysis-ui-1', 'analysis-la-87'],
  ));
  expect((await screen.findAllByText('P-07-LA')).length).toBeGreaterThan(0);
  expect(screen.getAllByText('KIV-2_LA.csv').length).toBeGreaterThan(0);
});

test("user confirms an image batch, places same- and cross-sample points, reviews and imports", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  expect(screen.getAllByText("KIV-2_A_BSE_01.tif").length).toBeGreaterThan(1);
  expect(screen.getByText("0 готово")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  expect(await screen.findByText("3 готово")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));

  await user.click(await screen.findByRole("button", { name: /^2\. KIV-2_A_PPL_01\.tif/ }));
  expect(await screen.findByText("2 / 3")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Другой Sample…" }));
  await user.click(screen.getByRole("button", { name: /P-03 EPMA OTHER/ }));
  fireEvent.keyDown(screen.getByRole("application"), { key: "Enter" });
  const crossSampleSave = await screen.findByRole("button", { name: "Сохранить привязку" });
  expect(crossSampleSave.disabled).toBe(true);
  await user.selectOptions(screen.getByRole("combobox", { name: "Причина межобразцового исключения" }), "image_covers_other_sample");
  await user.click(crossSampleSave);

  await user.click(screen.getByRole("button", { name: /^1\. KIV-2_A_BSE_01\.tif/ }));
  expect(await screen.findByText("1 / 3")).toBeTruthy();
  await user.click(await screen.findByRole("button", { name: /P-07/ }));
  fireEvent.keyDown(await screen.findByRole("application"), { key: "Enter" });
  expect(await screen.findByText("Point · 320, 240 px")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Сохранить привязку" }));
  expect(await screen.findByText("Размещение сохранено в черновике")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Далее: проверка" }));
  expect(await screen.findByRole("heading", { name: "Проверка импорта изображений" })).toBeTruthy();
  expect(screen.getByRole("img", { name: /Предпросмотр KIV-2_A_BSE_01\.tif/ })).toBeTruthy();
  expect(screen.queryByRole("application")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Завершить импорт изображений" }));

  await waitFor(() => expect(uiState.mediaImported).toBe(true));
  expect(await screen.findByRole("heading", { name: "Добавить изображения" })).toBeTruthy();
  expect(screen.getByText(/Импортировано изображений: 3/)).toBeTruthy();
  expect(screen.getByText(/Пространственных точек: 2/)).toBeTruthy();
});

test("saved point placement survives returning from image review", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  await user.click(await screen.findByRole("button", { name: /P-07/ }));
  fireEvent.keyDown(await screen.findByRole("application"), { key: "Enter" });
  await user.click(screen.getByRole("button", { name: "Сохранить привязку" }));
  expect((await screen.findByRole("status")).textContent).toContain("Размещение сохранено в черновике");

  await user.click(screen.getByRole("button", { name: "Далее: проверка" }));
  await user.click(await screen.findByRole("button", { name: "К размещению" }));

  expect((await screen.findByRole("status")).textContent).toContain("Размещение сохранено в черновике");
  expect(screen.getByText("Point · 320, 240 px")).toBeTruthy();
  expect(screen.getByText("1 размещено")).toBeTruthy();
});

test("removing a placement after review preserves the same point on another image", async () => {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));

  for (const file of [/^1\. KIV-2_A_BSE_01\.tif/, /^2\. KIV-2_A_PPL_01\.tif/]) {
    await user.click(screen.getByRole("button", { name: file }));
    await user.click(screen.getByRole("button", { name: /P-07 EPMA/ }));
    fireEvent.keyDown(await screen.findByRole("application"), { key: "Enter" });
    await user.click(screen.getByRole("button", { name: "Сохранить привязку" }));
  }

  let finishPlan;
  const planImplementation = createMediaImportPlan.getMockImplementation();
  createMediaImportPlan.mockImplementationOnce((...args) => new Promise((resolve) => {
    finishPlan = async () => resolve(await planImplementation(...args));
  }));
  await user.click(screen.getByRole("button", { name: "Далее: проверка" }));
  const remove = screen.getByRole("button", { name: "Снять только связь" });
  expect(remove.disabled).toBe(true);
  await user.click(remove);
  expect(screen.getByText("2 размещено")).toBeTruthy();
  await finishPlan();
  await user.click(await screen.findByRole("button", { name: "К размещению" }));
  await user.click(screen.getByRole("button", { name: "Снять только связь" }));
  expect(screen.queryByRole("button", { name: "Размещение P-07" })).toBeNull();
  expect(screen.getByText("1 размещено")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: /^1\. KIV-2_A_BSE_01\.tif/ }));
  expect(await screen.findByRole("button", { name: "Размещение P-07" })).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "Далее: проверка" }));
  await user.click(await screen.findByRole("button", { name: "Завершить импорт изображений" }));
  const appliedPlan = applyMediaImportPlan.mock.calls[0][1];
  expect(appliedPlan.items).toHaveLength(3);
  expect(appliedPlan.items.map((item) => item.placements.length)).toEqual([1, 0, 0]);
  expect(appliedPlan.items[0].placements[0]).toMatchObject({
    analytical_point_id: "point-kiv-2-p07",
    geometry: { kind: "point", x_px: 320, y_px: 240 },
  });
});

test("image file list supports arrow navigation without losing focus", async () => {
  render(<App />);

  await screen.findByRole("button", { name: "Изображения" }).then((button) => fireEvent.click(button));
  fireEvent.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });

  const first = screen.getByText(/1\. KIV-2_A_BSE_01\.tif/).closest("button");
  const second = screen.getByText(/2\. KIV-2_A_PPL_01\.tif/).closest("button");
  first.focus();
  fireEvent.keyDown(first, { key: "ArrowDown" });
  expect(second.getAttribute("aria-current")).toBe("true");
  expect(document.activeElement).toBe(second);
  fireEvent.keyDown(second, { key: "Home" });
  expect(first.getAttribute("aria-current")).toBe("true");
  expect(document.activeElement).toBe(first);

  fireEvent.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  fireEvent.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  const placementFiles = screen.getByRole("navigation", { name: "Изображения для размещения точек" });
  const placementButtons = placementFiles.querySelectorAll("button");
  placementButtons[0].focus();
  fireEvent.keyDown(placementButtons[0], { key: "ArrowDown" });
  expect(placementButtons[1].getAttribute("aria-current")).toBe("true");
  expect(document.activeElement).toBe(placementButtons[1]);
});

test("final image review calls out images without spatial points", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  await user.click(await screen.findByRole("button", { name: "Далее: проверка" }));

  expect((await screen.findByRole("status")).textContent).toContain("изображений без пространственных точек");
  expect(screen.getAllByRole("row").filter((row) => row.textContent.includes("Без точек"))).toHaveLength(3);
  const sourcePane = screen.getByText("Импортируемые изображения").closest("aside");
  expect(within(sourcePane).getAllByText("Без точек")).toHaveLength(3);
  const reviewRows = screen.getAllByRole("row").filter((row) => row.tagName === "BUTTON");
  expect(reviewRows[0].getAttribute("aria-current")).toBe("true");
  reviewRows[0].focus();
  fireEvent.keyDown(reviewRows[0], { key: "ArrowDown" });
  expect(document.activeElement).toBe(reviewRows[1]);
  expect(reviewRows[1].className).toContain("active");
  expect(reviewRows[1].getAttribute("aria-current")).toBe("true");
  expect(screen.getByRole("button", { name: "Завершить импорт изображений" }).disabled).toBe(false);
});

test("selecting a point focuses the canvas and Enter creates a centered square draft", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  await user.click(screen.getByRole("button", { name: "Square" }));
  await user.click(await screen.findByRole("button", { name: /P-07/ }));

  const canvas = await screen.findByRole("application");
  await waitFor(() => expect(document.activeElement).toBe(canvas));
  await user.keyboard("{Enter}");
  expect(await screen.findByText("Square · 291, 211 px · 58 × 58 px")).toBeTruthy();
});

test("dragging the canvas preserves rectangle and square geometry in source pixels", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  await user.click(screen.getByRole("button", { name: "Rectangle" }));
  await user.click(await screen.findByRole("button", { name: /P-07/ }));

  const canvas = await screen.findByRole("application");
  const boundsSpy = vi.spyOn(canvas, "getBoundingClientRect").mockReturnValue({ left: 0, top: 0, width: 640, height: 480, right: 640, bottom: 480 });
  const fireCanvasPointer = (type, pointerId, clientX, clientY) => {
    const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: 0, clientX, clientY });
    Object.defineProperty(event, "pointerId", { value: pointerId });
    fireEvent(canvas, event);
  };
  fireCanvasPointer("pointerdown", 0, 20, 20);
  fireCanvasPointer("pointermove", 0, 120, 100);
  expect(await screen.findByText("Rectangle · 20, 20 px · 100 × 80 px")).toBeTruthy();
  fireCanvasPointer("pointercancel", 0, 20, 20);
  fireCanvasPointer("pointerup", 0, 300, 220);
  expect(screen.queryByText(/Rectangle ·/)).toBeNull();
  fireCanvasPointer("pointerdown", 1, 100, 100);
  fireCanvasPointer("pointermove", 1, 300, 220);
  expect(boundsSpy).toHaveBeenCalledTimes(4);
  fireCanvasPointer("pointerup", 1, 300, 220);
  expect(boundsSpy).toHaveBeenCalledTimes(5);
  expect(await screen.findByText("Rectangle · 100, 100 px · 200 × 120 px")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "Сохранить привязку" }));
  await user.click(screen.getByRole("button", { name: "Square" }));
  const pointButton = screen.getAllByText("P-07").find((element) => element.closest(".point-candidate-list"))?.closest("button");
  await user.click(pointButton);
  fireCanvasPointer("pointerdown", 2, 100, 100);
  fireCanvasPointer("pointerup", 2, 300, 220);
  expect(await screen.findByText("Square · 100, 100 px · 120 × 120 px")).toBeTruthy();
});

test("user opens a recursively collected image folder as one batch", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать папку" }));

  expect(pickMediaFolder).toHaveBeenCalledOnce();
  expect(await screen.findByRole("heading", { name: "Назначь Sample и шлиф" })).toBeTruthy();
  expect(screen.getAllByText("KIV-2_A_BSE_01.tif").length).toBeGreaterThan(1);
  expect(screen.getByText("Выбрано: 3 из 3")).toBeTruthy();
});

test("an image folder without supported files explains why no batch opened", async () => {
  pickMediaFolder.mockResolvedValueOnce([]);
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать папку" }));

  expect(await screen.findByText("В выбранной папке и её вложенных папках нет PNG, JPEG, TIFF или BMP.")).toBeTruthy();
  expect(screen.getByRole("heading", { name: "Добавить изображения" })).toBeTruthy();
});

test("duplicate image rows can be excluded from the transient batch without touching source files", async () => {
  uiState.mediaDuplicates = true;
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });

  const summary = screen.getByLabelText("Сводка пакета изображений");
  expect(within(summary).getByText("2")).toBeTruthy();
  expect(within(summary).getByText("дубликатов")).toBeTruthy();
  const excludeButton = screen.getByRole("button", { name: "Исключить выбранные дубликаты (2)" });
  expect(excludeButton.disabled).toBe(false);

  await user.click(excludeButton);
  expect(screen.queryByRole("button", { name: "Исключить выбранные дубликаты (2)" })).toBeNull();
  expect(screen.getByText("Выбрано: 1 из 1")).toBeTruthy();
  expect(screen.getByText("0 готово")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "Вернуть в пакет" }));
  expect(screen.getByText("Выбрано: 1 из 3")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Исключить выбранные дубликаты (0)" }).disabled).toBe(true);
  await user.click(screen.getByRole("checkbox", { name: "Выбрано: 1 из 3" }));
  await user.click(screen.getByRole("button", { name: "Исключить выбранные дубликаты (2)" }));

  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  expect(await screen.findByText("1 / 1")).toBeTruthy();
});

test("a failed image preview can be retried without reimporting the batch", async () => {
  uiState.mediaPreviewFailures = 1;
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));

  expect(await screen.findByText("Временный сбой preview.")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Повторить preview" }));
  expect(await screen.findByRole("application")).toBeTruthy();
});

test("switching images keeps an unfinished preview request visible for the active image", async () => {
  let resolveFirstPreview;
  const firstPreview = new Promise((resolve) => { resolveFirstPreview = resolve; });
  getMediaPreview.mockImplementationOnce(() => firstPreview);
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  expect(await screen.findByText("Готовлю безопасный preview…")).toBeTruthy();

  await user.click(await screen.findByRole("button", { name: /^2\. KIV-2_A_PPL_01\.tif/ }));
  expect(await screen.findByRole("application")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: /^1\. KIV-2_A_BSE_01\.tif/ }));
  expect(screen.getByText("Готовлю безопасный preview…")).toBeTruthy();
  resolveFirstPreview({ result: {
    source_path: "C:/fixtures/KIV-2_A_BSE_01.tif",
    source_fingerprint: "fingerprint-BSE",
    source_width_px: 640,
    source_height_px: 480,
    preview_width_px: 640,
    preview_height_px: 480,
    preview_data_url: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB",
  } });
  expect(await screen.findByRole("application")).toBeTruthy();
});

test("a preview response from a replaced batch cannot overwrite the current batch", async () => {
  const sourcePath = "C:/fixtures/reused-name.tif";
  const oldInspection = { items: [{
    source_path: sourcePath,
    display_name: "reused-name.tif",
    source_fingerprint: "old-fingerprint",
    mime_type: "image/tiff",
    format: "tiff",
    width_px: 640,
    height_px: 480,
    suggested_media_type: "BSE",
    suggested_sample_name: "KIV-2",
    suggested_thin_section_name: "KIV-2-A",
  }], duplicate_groups: [] };
  const newInspection = { items: [{
    ...oldInspection.items[0],
    source_fingerprint: "new-fingerprint",
    suggested_sample_name: "KIV-3",
    suggested_thin_section_name: "KIV-3-A",
  }], duplicate_groups: [] };
  const oldPreviewData = "data:image/png;base64,old-preview";
  const newPreviewData = "data:image/png;base64,new-preview";
  let resolveOldPreview;
  const oldPreview = new Promise((resolve) => {
    resolveOldPreview = () => resolve({
      source_path: sourcePath,
      source_fingerprint: "old-fingerprint",
      source_width_px: 640,
      source_height_px: 480,
      preview_width_px: 640,
      preview_height_px: 480,
      preview_data_url: oldPreviewData,
    });
  });
  const onPreview = vi.fn()
    .mockImplementationOnce(() => oldPreview)
    .mockResolvedValueOnce({
      source_path: sourcePath,
      source_fingerprint: "new-fingerprint",
      source_width_px: 640,
      source_height_px: 480,
      preview_width_px: 640,
      preview_height_px: 480,
      preview_data_url: newPreviewData,
    });
  const noop = vi.fn();
  const user = userEvent.setup();
  const props = {
    points: { items: [] },
    busy: false,
    onChoose: noop,
    onChooseFolder: noop,
    onPreview,
    onPlan: noop,
    onApply: noop,
    onCancel: noop,
  };
  const { rerender } = render(<ImagesWorkspace {...props} inspection={oldInspection} />);
  await user.click(await screen.findByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  expect(await screen.findByText("Готовлю безопасный preview…")).toBeTruthy();

  rerender(<ImagesWorkspace {...props} inspection={newInspection} />);
  await user.click(await screen.findByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  expect(await screen.findByRole("application")).toBeTruthy();
  expect(screen.getByRole("img", { name: "BSE KIV-3" }).getAttribute("src")).toBe(newPreviewData);

  resolveOldPreview();
  await waitFor(() => expect(screen.getByRole("img", { name: "BSE KIV-3" }).getAttribute("src")).toBe(newPreviewData));
});

test("image assignment accepts a user-defined media type and applies it in bulk", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });

  const mediaType = screen.getByLabelText("Тип изображения");
  await user.clear(mediaType);
  await user.type(mediaType, "Cathodoluminescence");
  await user.click(screen.getByRole("button", { name: "Применить к выбранным (3)" }));

  expect(screen.getAllByText("Cathodoluminescence").length).toBeGreaterThan(0);
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));
  expect(await screen.findByText("KIV-2_A_BSE_01.tif (Cathodoluminescence)")).toBeTruthy();
});

test("switching images clears a point focus and returns to same-Sample scope", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Изображения" }));
  await user.click(screen.getByRole("button", { name: "Выбрать файлы" }));
  await screen.findByRole("heading", { name: "Назначь Sample и шлиф" });
  await user.click(screen.getByRole("button", { name: "Подтвердить предложения" }));
  await user.click(screen.getByRole("button", { name: "Продолжить: точки" }));

  await user.click(screen.getByRole("button", { name: "Другой Sample…" }));
  await user.click(screen.getByRole("button", { name: /P-03 EPMA OTHER/ }));
  expect(screen.getByText("Точка другого Sample")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: /^2\. KIV-2_A_PPL_01\.tif/ }));
  expect(screen.queryByText("Точка другого Sample")).toBeNull();
  expect(screen.getByRole("button", { name: "Другой Sample…" }).className).not.toContain("active");
  expect(screen.getByRole("button", { name: "Этот Sample" }).className).toContain("active");
});

test("user clicks through Clean Table import and sees the saved Analysis", async () => {
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  const importButton = await screen.findByRole("button", { name: "Импортировать таблицу" });
  expect(pickImportFile).toHaveBeenCalledOnce();

  await user.click(screen.getByRole("button", { name: "Предпросмотр результата" }));
  const preview = screen.getByRole("dialog", { name: "Что попадёт в проект" });
  await user.type(within(preview).getByRole("textbox", { name: "Поиск в результате импорта" }), "UI-2");
  expect(within(preview).getByText("UI-2")).toBeTruthy();
  expect(within(preview).queryByText("UI-1")).toBeNull();
  await user.click(within(preview).getByRole("button", { name: "Закрыть предпросмотр" }));

  await user.click(importButton);
  await screen.findByRole("heading", { name: "Анализы" });
  expect((await screen.findAllByText("Windows UI smoke")).length).toBeGreaterThan(1);
  expect(screen.getAllByText("UI-1").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Trace-15").length).toBeGreaterThan(0);

  await user.click(screen.getByRole("checkbox", { name: "Выбрать UI-1" }));
  expect(screen.getByText("1 выбрано")).toBeTruthy();

  const search = screen.getByRole("textbox", { name: "Поиск анализов" });
  await user.type(search, "KIV-3");
  const table = screen.getByRole("table");
  expect(within(table).getByText("UI-2")).toBeTruthy();
  expect(within(table).queryByText("UI-1")).toBeNull();
  await user.clear(search);
  expect(applyImportPlan).toHaveBeenCalledWith(
    "C:/PetroLab/project.sqlite",
    "C:/PetroLab/staging/ui-clean-table.csv",
    expect.any(Object),
  );
  await waitFor(() => expect(uiState.imported).toBe(true));
});

test("complex import always shows the source table and groups repeated structural issues", async () => {
  uiState.mode = "complex";
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  await screen.findByRole("heading", { name: "Импорт таблиц" });

  expect(screen.getByText("Исходная таблица")).toBeTruthy();
  const sourceTable = screen.getByRole("table");
  expect(within(sourceTable).getAllByText("Analysis").length).toBeGreaterThan(0);
  expect(within(sourceTable).getAllByText("SiO2").length).toBeGreaterThan(0);
  expect(within(sourceTable).getByText("Sigma")).toBeTruthy();
  expect(screen.getByText("Колонка с данными не имеет заголовка · 3 мест")).toBeTruthy();
});

test("post-import mineral queue keeps source, suggestion and accepted decision separate", async () => {
  uiState.imported = true;
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Минералы" }));
  expect(await screen.findByRole("listbox", { name: "Очередь проверки минералов" })).toBeTruthy();
  expect(screen.getByText("garnet")).toBeTruthy();
  expect(screen.getAllByText("clinopyroxene").length).toBeGreaterThan(0);
  await user.click(screen.getByRole("button", { name: "Принять предложение" }));
  await waitFor(() => expect(uiState.mineralAccepted).toBe(true));
  expect(await screen.findByText("принято")).toBeTruthy();
  expect(screen.getByText("исходный текст")).toBeTruthy();
});

test("Python identity blocker is visible, navigable and prevents saving", async () => {
  uiState.mode = "complex";
  createImportPlan.mockResolvedValueOnce({ result: {
    ready_to_commit: false,
    summary: { planned_analysis_count: 1, planned_measurement_count: 1, enabled_block_count: 1, duplicate_candidate_groups: 0 },
    planned_records: [], warnings: [],
    issues: [{ code: "ANALYSIS_IDENTITY_REQUIRED", blocking: true, sheet_name: "Summary", block_id: "summary-main", row_number: 3, source_column_index: 0 }],
  } });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  const issue = await screen.findByRole("button", { name: /Нет идентичности Analysis/ });
  await user.click(issue);
  expect(screen.getByText("Исходная таблица")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Импортировать после проверки" }).disabled).toBe(true);
  expect(applyImportPlan).not.toHaveBeenCalled();
});

test("the inspector shows one current question and collapses the remaining queue", async () => {
  uiState.mode = "complex";
  uiState.detailsEnabled = false;
  uiState.unitApplied = true;
  createImportPlan.mockResolvedValueOnce({ result: {
    ready_to_commit: false,
    summary: { planned_analysis_count: 1, planned_measurement_count: 1, enabled_block_count: 1, duplicate_candidate_groups: 0 },
    planned_records: [], warnings: [],
    issues: [
      { code: "ANALYSIS_IDENTITY_REQUIRED", blocking: true, sheet_name: "Summary", block_id: "summary-main", row_number: 3, source_column_index: 0 },
      { code: "ANALYSIS_IDENTITY_REQUIRED", blocking: true, sheet_name: "Summary", block_id: "summary-main", row_number: 4, source_column_index: 0 },
      { code: "ANALYSIS_IDENTITY_REQUIRED", blocking: true, sheet_name: "Summary", block_id: "summary-main", row_number: 5, source_column_index: 0 },
    ],
  } });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));

  await waitFor(() => expect(document.querySelector(".import-inspector-pane > .import-pane-label")?.textContent).toBe("3 вопроса"));
  const status = document.querySelector(".import-inspector-pane > .import-pane-label");
  expect(status?.getAttribute("role")).toBe("status");
  expect(status?.getAttribute("aria-live")).toBe("polite");
  expect(document.querySelectorAll(".import-inspector-pane > .import-issue-list .import-issue-row.blocking")).toHaveLength(1);
  const queueDisclosure = document.querySelector(".import-question-queue");
  expect(queueDisclosure?.open).toBe(false);
  expect(queueDisclosure?.querySelector("summary")?.textContent).toBe("Ещё 2 вопроса");
  queueDisclosure.querySelector("summary").focus();
  expect(document.activeElement).toBe(queueDisclosure.querySelector("summary"));
  await user.click(queueDisclosure.querySelector("summary"));
  expect(queueDisclosure.open).toBe(true);
  expect(queueDisclosure.querySelectorAll(".import-issue-row.blocking")).toHaveLength(2);
});

test("a server-issued bulk ignore appears only as the current question", async () => {
  uiState.mode = "complex";
  uiState.unitApplied = true;
  createImportPlan.mockResolvedValueOnce({ result: {
    ready_to_commit: false,
    summary: { planned_analysis_count: 2, planned_measurement_count: 2, enabled_block_count: 3, duplicate_candidate_groups: 0 },
    planned_records: [], warnings: [],
    issues: [{ code: "UNMAPPED_FIELD_REQUIRES_REVIEW", blocking: true, sheet_name: "Details", block_id: "details-1", source_axis: "column", source_column_index: 1, source_header: "Sigma" }],
  } });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));

  expect(await screen.findByRole("heading", { name: "Что делать с нераспознанными полями?" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Не импортировать 2 поля" })).toBeTruthy();
  expect(document.querySelector(".import-field-settings")?.open).toBe(false);
  await waitFor(() => expect(applyWorkspaceDecision.mock.calls.some((call) => call[3]?.kind === "activate" && call[3]?.block_id === "details-1")).toBe(true));
  await user.click(screen.getByRole("button", { name: "Не импортировать 2 поля" }));
  await waitFor(() => expect(applyWorkspaceDecision.mock.calls.some((call) => call[3]?.kind === "ignore" && call[3]?.bulk_scope_id === "details-ignore")).toBe(true));
});

test("user resolves a repeated complex workbook with sheet-level and grouped decisions", async () => {
  uiState.mode = "complex";
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "Выбрать файл" }));
  await screen.findByRole("heading", { name: "Импорт таблиц" });

  expect(screen.getByRole("button", { name: /Не импортировать лист Details/ })).toBeTruthy();
  expect(screen.getAllByText("Details").length).toBe(1);
  await waitFor(() => expect(screen.getByRole("button", { name: "Не импортировать лист Details" }).disabled).toBe(false));
  await user.click(screen.getByRole("button", { name: "Не импортировать лист Details" }));
  await waitFor(() => expect(uiState.detailsEnabled).toBe(false));

  const groupedUnit = await screen.findByRole("combobox", { name: "Единица для группы SiO2" });
  await waitFor(() => expect(groupedUnit.disabled).toBe(false));
  await user.selectOptions(groupedUnit, "wt.%");
  const applyUnit = screen.getByRole("button", { name: "Назначить 1 полю" });
  await waitFor(() => expect(applyUnit.disabled).toBe(false));
  await user.click(applyUnit);
  await waitFor(() => expect(uiState.unitApplied).toBe(true));

  await user.click(document.querySelector(".import-duplicate-settings > summary"));
  await user.click(await screen.findByRole("button", { name: "Проверено: оставить все записи" }));
  await waitFor(() => expect(uiState.duplicatesReviewed).toBe(true));

  const save = await screen.findByRole("button", { name: "Сохранить импорт в проект" });
  await user.click(screen.getByRole("button", { name: "Предпросмотр результата" }));
  expect(screen.getByRole("dialog", { name: "Что попадёт в проект" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Закрыть предпросмотр" }));
  await user.click(save);

  await screen.findByRole("heading", { name: "Анализы" });
  expect(applyImportPlan).toHaveBeenCalled();
});
