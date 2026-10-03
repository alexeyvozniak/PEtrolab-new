# Контрольный test-run Streamlit v1 для legacy-аудита

**Версия v1:** `e7bf36f46a6c049bc0dfb767483611e892503e41`  
**Дата:** 2026-08-30  
**Изоляция:** новый временный каталог `PETROLAB_DATA_DIR`, без рабочей базы пользователя  
**Интерпретатор:** отдельное audit-окружение Python с зависимостями v1

## Результат

- Исполнено: 65 файлов.
- Прошло: 60.
- Завершилось ошибкой: 5.
- Дополнительно обнаружено: два ожидаемых отдельных regression-файла отсутствуют; cloud browser не открыл локальный Streamlit port.

Три теста из `tests/` запускались с `PYTHONPATH=.`. Без этого Python добавляет в `sys.path` только подпапку `tests/` и создаёт ложный `ModuleNotFoundError: petrolab`.

## Прошли

1. `tests_column_schema.py`
2. `tests_import_atomic.py`
3. `tests_import_schema.py`
4. `tests_import_semantics.py`
5. `tests_import_staging.py`
6. `tests_manual_import_blocks.py`
7. `tests_quick_import.py`
8. `tests_source_sync_conflicts.py`
9. `tests_analysis_drafts.py`
10. `tests_analysis_service.py`
11. `tests_v0158_table_views.py`
12. `tests_v0158_selection_export.py`
13. `tests_v0158_row_display_states.py`
14. `tests_formulae.py`
15. `tests_formula_workflow.py`
16. `tests_formula_input_validation.py`
17. `tests_formula_fingerprint.py`
18. `tests_user_derived.py`
19. `tests_mineral_recognition_v1.py`
20. `tests_mineral_recognition_extended.py`
21. `tests_alkaline_mineral_recognition.py`
22. `tests_amphibole_ima.py`
23. `tests_point_formulae.py`
24. `tests_measurement_registry.py`
25. `tests_analytical_sessions.py`
26. `tests_statistics.py`
27. `tests_density_clustering.py`
28. `tests_group_envelopes.py`
29. `tests_group_styles.py`
30. `tests_cluster_xy_handoff.py`
31. `tests_manual_fields.py`
32. `tests_smart_recommendations.py`
33. `tests_smart_plot_start.py`
34. `tests_v0158_axis_ranges.py`
35. `tests_grain_profiles.py`
36. `tests_thermobarometry.py`
37. `tests_thermodynamics.py`
38. `tests_partition_import.py`
39. `tests_partition_germ_basanite.py`
40. `tests_article_tables.py`
41. `tests_publication_composer.py`
42. `tests_publication_manifest.py`
43. `tests_figure_composer.py`
44. `tests_project_archive.py`
45. `tests_project_archive_scope.py`
46. `tests_selective_exchange.py`
47. `tests_collaboration.py`
48. `tests_global_search.py`
49. `tests_linked_multi_panel_v0154.py`
50. `tests_linked_petrography.py`
51. `tests_linked_petrography_storage.py`
52. `tests_slides.py`
53. `tests_image_service.py`
54. `tests_v0158_plot_spec_handoff.py`
55. `tests_v0158_panel_manager.py`
56. `tests/test_linked_panels_encoding.py`
57. `tests/test_linked_panels_mixed_views.py`
58. `tests/test_publication_bridge.py`
59. `tests_rock_workspace.py`
60. `tests_rock_semantics.py`

## Завершились ошибкой

1. `tests_import_service.py`: fixture не передаёт ставшее обязательным решение `FeO`/`FeOt`; preflight корректно блокирует импорт.
2. `tests_advanced_recipe_state.py`: проверяет точное равенство исходному словарю, тогда как реализация добавляет `_scientific_context`; тест и контракт восстановления разошлись.
3. `tests_grain_profile_hardening.py`: импортирует удалённую приватную функцию `_exact_order`.
4. `tests_v0160_task_first_navigation.py`: ожидает список навигации до Product Design rebuild.
5. `tests_v0151_silent_errors.py`: ожидает удалённую колонку SQLite `entity_link_source`.

## Не являются прошедшими проверками

- `tests_edit_undo.py`: файл отсутствует; наличие `petrolab/edit_undo.py` не заменяет regression test.
- `tests_outliers.py`: файл отсутствует; наличие `petrolab/outliers.py` не заменяет regression test.
- Browser flow: заблокирован инфраструктурой доступа к локальному Streamlit port; скриншоты не получены и UX-аудит по ним не заявлен.
