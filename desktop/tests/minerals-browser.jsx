// Synthetic UI-only fixture; no native picker, database or scientific calculations.
// This entrypoint is excluded from the production build.
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MineralsWorkspace } from '../src/MineralsWorkspace';
import '../src/styles.css';

const initial = [
  ['P-07', 'garnet', 'olivine', 'conflict'],
  ['P-08', 'phlogopite', 'trioctahedral mica', 'consistent'],
  ['P-09', '', null, 'insufficient_input'],
].map(([name, reported, prediction, status], index) => ({
  analysis_id: `qa-${index}`, identity: { Analysis: name, Sample: '19KL23' },
  source_name: 'Контрольные составы.csv', sheet_name: 'Лист 1', source_row_number: index + 2,
  reported_mineral: { value: reported },
  mineral_verification: {
    status, reported_mineral: reported, reported_target: index === 1 ? 'trioctahedral mica' : reported || null,
    prediction, confidence: prediction ? 'high' : 'unresolved', accepted: null,
    input_fingerprint: `qa-${index}`, ruleset_version: 'QA fixture',
    candidates: prediction ? [{ target: prediction, score: 9, reasons: [] }] : [],
    reasons: [], issues: prediction ? [] : ['incomplete_major_element_input'],
  },
}));

function Fixture() {
  const [analyses, setAnalyses] = useState(initial);
  return <><header style={{padding: 12}}>PetroLab · Минералы · синтетический UI-сценарий, без записи в проект</header>
    <MineralsWorkspace project={{analyses, total: analyses.length, has_more: false, mineral_options: ['forsterite', 'olivine', 'phlogopite', 'garnet']}} busy={false}
      onRefresh={() => {}} onLoadMore={() => {}} onAddData={() => {}}
      onDecide={(analysis, target, reason) => setAnalyses(rows => rows.map(row => row.analysis_id !== analysis.analysis_id ? row : {
        ...row, mineral_verification: {...row.mineral_verification,
          status: target ? 'verified' : initial.find(item => item.analysis_id === row.analysis_id).mineral_verification.status,
          accepted: target ? {target, reason} : null,
        },
      }))} />
  </>;
}
createRoot(document.getElementById('root')).render(<Fixture />);
