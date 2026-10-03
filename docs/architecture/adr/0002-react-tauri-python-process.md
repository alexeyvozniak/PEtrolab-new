# ADR-0002: React + Tauri + локальный Python process

- **Status:** Accepted for prototype
- **Date:** 2026-08-28

## Context

Нужен современный плотный UI, качественная Windows-упаковка и сохранение существующей Python-экосистемы научных расчётов.

## Decision

React является UI, Tauri — desktop shell и supervisor, локальный Python child process — application/scientific service. Начальный транспорт — versioned NDJSON по stdio. Localhost API, embedded Python и несколько backend-процессов не вводятся до доказанной необходимости.

## Consequences

Граница процессов требует явных DTO и обработки сбоев, зато UI не зависит от Python GUI, scientific core тестируется отдельно, а приложение не открывает сетевой порт.

