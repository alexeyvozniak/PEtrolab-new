# ADR-0005: Spatial Annotation и Media Link

- **Status:** Accepted
- **Date:** 2026-08-28

## Context

Анализы и фотографии нужно связывать с очень маленькими зонами шлифа при большом увеличении, не смешивая изображение, точку и Analysis.

## Decision

Point, Rectangle и Square являются вариантами Spatial Annotation и сохраняются в исходных координатах изображения независимо от zoom. Analysis–Annotation и Media–Annotation — отдельные обратимые связи. Фокус на аннотации не меняет Selection; для этого есть явная команда «Добавить связанные анализы к отбору».

## Consequences

Одна область может иметь несколько методов анализа и несколько медиафайлов. Снятие связи не удаляет Analysis, Spatial Annotation или Media Asset.

