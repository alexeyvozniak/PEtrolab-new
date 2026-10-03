import { CheckCircle, Warning } from "@phosphor-icons/react";
import "./importDuplicateReview.css";

function recordOrigin(record) {
  return record.orientation === "columns_are_analyses"
    ? `${record.sheet_name} · колонка ${record.source_column_number}`
    : `${record.sheet_name} · строка ${record.row_number}`;
}

function recordSummary(record) {
  const identity = (record.identity || []).filter(Boolean).join(" · ") || "без распознанного идентификатора";
  const fields = (record.measurements || []).map((item) => {
    const context = item.method || item.measurement_set;
    return context ? `${item.field} (${context})` : item.field;
  }).join(", ") || "без Measurement";
  return { identity, fields };
}

export function ImportDuplicateReview({ plan, recipe, busy, onKeepAll }) {
  const warning = plan?.warnings?.find((item) => item.code === "DUPLICATE_CANDIDATES");
  const groups = warning?.preview_ids || [];
  if (!groups.length) return null;

  const records = new Map((plan?.planned_records || []).map((record) => [record.preview_id, record]));
  const review = recipe?.global_decisions?.duplicate_review;
  const reviewed = recipe?.global_decisions?.duplicate_policy === "keep_all"
    && review?.decision === "keep_all"
    && review?.candidate_group_count === groups.length;

  return (
    <div className={`duplicate-review${reviewed ? " duplicate-reviewed" : ""}`}>
      <div className="duplicate-review-head">
        <div>
          <b>{reviewed ? "Совпадения проверены" : "Нужно проверить возможные совпадения"}</b>
          <span>
            PetroLab ничего не объединяет автоматически. Одинаковая идентичность может означать повтор, а может — дополнительные данные другого блока или метода.
          </span>
        </div>
        <span className="duplicate-review-status">
          {reviewed ? <><CheckCircle size={18} weight="fill" /> оставить все</> : <><Warning size={18} weight="fill" /> {groups.length} групп</>}
        </span>
      </div>

      <div className="duplicate-groups">
        {groups.map((group, groupIndex) => (
          <section className="duplicate-group" key={`duplicate-${groupIndex}`}>
            <strong>Группа {groupIndex + 1}</strong>
            <div>
              {group.map((previewId) => {
                const record = records.get(previewId);
                if (!record) return <div className="duplicate-record" key={previewId}><span>{previewId}</span></div>;
                const summary = recordSummary(record);
                return (
                  <div className="duplicate-record" key={previewId}>
                    <span>{recordOrigin(record)}</span>
                    <b>{summary.identity}</b>
                    <small>{summary.fields}</small>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>

      {!reviewed && (
        <div className="duplicate-review-action">
          <div>
            <b>В этой версии безопасное решение — только оставить все записи.</b>
            <span>Удаление отдельных повторов появится позже с отдельной provenance. Сейчас PetroLab не будет молча выбрасывать строки.</span>
          </div>
          <button className="primary-button" onClick={onKeepAll} disabled={busy}>
            Проверено: оставить все записи
          </button>
        </div>
      )}
    </div>
  );
}
