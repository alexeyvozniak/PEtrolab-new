export const MINERAL_STATUS_LABELS = {
  consistent: "совпадает",
  verified: "принято",
  conflict: "конфликт",
  missing_reported: "нет названия",
  low_confidence: "неоднозначно",
  insufficient_input: "мало данных",
  unrecognized_reported: "нужно проверить",
  not_checked: "не проверен",
  reported_only: "только исходное название",
  manually_assigned: "назначено вручную",
  manual_unresolved: "проверьте ручное название",
  stale_assignment: "решение устарело",
};

export const MINERAL_CONFIDENCE_LABELS = {
  high: "высокая",
  medium: "средняя",
  ambiguous: "неоднозначная",
  unresolved: "не определена",
  insufficient_input: "недостаточно данных",
};

const REASON_LABELS = {
  manual_label_unrecognized: "Ручное название сохранено, но не найдено в справочнике. Уточните назначение.",
  accepted_assignment_stale: "Ранее принятое решение устарело после изменения состава или версии правил.",
  duplicate_component: "Один компонент присутствует в составе несколько раз.",
  incomplete_major_element_input: "Не хватает обязательных основных компонентов или формы железа.",
  invalid_numeric_input: "В одном из обязательных компонентов некорректное числовое значение.",
  missing_component_field: "Для одного из измерений не определён компонент.",
  missing_or_censored_input: "Обязательный компонент отсутствует или указан как предел обнаружения.",
  overlapping_iron_basis: "Одновременно указаны несовместимые варианты суммарного железа.",
  unresolved_iron_form: "Форма железа требует явного решения.",
  reported_target_differs: "Минерал из исходной таблицы не совпадает с предложением классификатора.",
  ca_mg_ratio_supports_clinopyroxene: "Соотношение Ca и Mg поддерживает состав клинопироксена.",
  core_oxides_available: "Для проверки доступны основные оксиды.",
  iron_basis_feot: "Железо передано как суммарное FeOt.",
};

export function mineralStatusLabel(value) {
  return MINERAL_STATUS_LABELS[value] || value || "—";
}

export function mineralConfidenceLabel(value) {
  return MINERAL_CONFIDENCE_LABELS[value] || value || "—";
}

export function mineralReasonLabel(value) {
  if (REASON_LABELS[value]) return REASON_LABELS[value];
  if (value?.startsWith("competing candidate: ")) {
    return `Есть близкий кандидат: ${value.slice("competing candidate: ".length)}.`;
  }
  if (value?.includes("_")) {
    return `Дополнительное ограничение правил: ${value.replaceAll("_", " ")}.`;
  }
  return value || "Основание не передано классификатором.";
}

export function reportedMineral(analysis) {
  const value = analysis?.reported_mineral;
  if (value && typeof value === "object") return value.value || "";
  return value || analysis?.source_metadata?.Mineral || "";
}

export function mineralStatus(analysis) {
  return analysis?.mineral_verification?.status || (reportedMineral(analysis) ? "reported_only" : "not_checked");
}
