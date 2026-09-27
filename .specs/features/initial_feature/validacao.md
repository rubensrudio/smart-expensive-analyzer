# Validações pré-entrega (geradas por check_plan.py — não editar à mão)

## Mapa de ondas (calculado)

| Onda | Tasks | Risco máx | Gatilhos previstos | QA previsto |
|---|---|---|---|---|
| 1 | TASK-001 | médio | — | — |
| 2 | TASK-002, TASK-003, TASK-004, TASK-006 | médio | — | — |
| 3 | TASK-005, TASK-011, TASK-013, TASK-015 | médio | G2 CT-6 | PADRAO |
| 4 | TASK-007, TASK-008, TASK-009, TASK-014 | médio | G2 CT-5,CT-6,CT-4,CT-23,CT-7 | PADRAO |
| 5 | TASK-010, TASK-016, TASK-017 | médio | G2 CT-6,CT-13 | PADRAO |
| 6 | TASK-012, TASK-018, TASK-020, TASK-021 | médio | G2 CT-9,CT-3,CT-23,CT-7,CT-10 | PADRAO |
| 7 | TASK-019 | alto | G1 TASK-019 | RIGOROSO |
| 8 | TASK-024 | alto | G1 TASK-024 | RIGOROSO |
| 9 | TASK-026 | alto | G1 TASK-026 | RIGOROSO |
| 10 | TASK-027 | alto | G1 TASK-027; G3 (1 história(s) P1) | RIGOROSO |
| 11 | TASK-029 | alto | G1 TASK-029; G3 (1 história(s) P1) | RIGOROSO |
| 12 | TASK-022, TASK-023, TASK-030 | médio | G2 CT-9,CT-23,CT-7 | PADRAO |
| 13 | TASK-025 | alto | G1 TASK-025; G3 (1 história(s) P1) | RIGOROSO |
| 14 | TASK-028 | alto | G1 TASK-028; G3 (1 história(s) P1) | RIGOROSO |
| 15 | TASK-031, TASK-032 | baixo | G3 (1 história(s) P1) | PADRAO |

Caminho crítico: TASK-001 → TASK-004 → TASK-005 → TASK-007 → TASK-010 → TASK-018 → TASK-022 → TASK-025 → TASK-032 (9 tasks)
G4 (gate cego) e G5 (retry) só são conhecidos na execução.

## Cobertura de requisitos

| ID do spec | Task(s) | Status |
|---|---|---|
| `SEA-01` | TASK-005, TASK-030, TASK-031 | ✅ |
| `SEA-02` | TASK-012, TASK-032 | ✅ |
| `SEA-03` | TASK-002 | ✅ |
| `SEA-04` | TASK-001, TASK-031 | ✅ |
| `SEA-05` | TASK-003 | ✅ |
| `SEA-06` | TASK-003 | ✅ |
| `SEA-35` | TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029, TASK-032 | ✅ |
| `SEA-07` | TASK-019, TASK-024 | ✅ |
| `SEA-08` | TASK-019, TASK-024 | ✅ |
| `SEA-09` | TASK-004, TASK-013, TASK-014 | ✅ |
| `SEA-10` | TASK-014 | ✅ |
| `SEA-11` | TASK-008, TASK-011, TASK-021, TASK-025 | ✅ |
| `SEA-12` | TASK-021, TASK-025 | ✅ |
| `SEA-13` | TASK-008, TASK-011, TASK-025 | ✅ |
| `SEA-14` | TASK-019 | ✅ |
| `SEA-36` | TASK-014 | ✅ |
| `SEA-37` | TASK-014 | ✅ |
| `SEA-38` | TASK-001, TASK-014 | ✅ |
| `SEA-39` | TASK-004, TASK-006, TASK-008, TASK-014 | ✅ |
| `SEA-40` | TASK-011, TASK-025 | ✅ |
| `SEA-41` | TASK-009, TASK-014, TASK-019 | ✅ |
| `SEA-42` | TASK-019, TASK-024 | ✅ |
| `SEA-43` | TASK-009, TASK-019, TASK-024 | ✅ |
| `SEA-44` | TASK-008, TASK-019 | ✅ |
| `SEA-45` | TASK-019, TASK-024 | ✅ |
| `SEA-67` | TASK-008, TASK-011, TASK-025 | ✅ |
| `SEA-68` | TASK-008, TASK-025 | ✅ |
| `SEA-15` | TASK-020, TASK-026 | ✅ |
| `SEA-16` | TASK-020, TASK-026 | ✅ |
| `SEA-17` | TASK-013, TASK-019 | ✅ |
| `SEA-18` | TASK-020, TASK-027 | ✅ |
| `SEA-19` | TASK-013 | ✅ |
| `SEA-46` | TASK-013 | ✅ |
| `SEA-47` | TASK-007, TASK-013 | ✅ |
| `SEA-48` | TASK-007, TASK-020, TASK-027 | ✅ |
| `SEA-49` | TASK-020, TASK-027 | ✅ |
| `SEA-50` | TASK-020, TASK-027 | ✅ |
| `SEA-51` | TASK-007, TASK-020, TASK-026 | ✅ |
| `SEA-52` | TASK-005, TASK-013 | ✅ |
| `SEA-53` | TASK-007, TASK-020, TASK-026 | ✅ |
| `SEA-20` | TASK-015, TASK-023, TASK-028 | ✅ |
| `SEA-21` | TASK-008, TASK-023, TASK-028 | ✅ |
| `SEA-22` | TASK-015, TASK-023, TASK-028 | ✅ |
| `SEA-23` | TASK-023, TASK-028 | ✅ |
| `SEA-24` | TASK-023, TASK-028 | ✅ |
| `SEA-25` | TASK-008, TASK-023 | ✅ |
| `SEA-26` | TASK-015 | ✅ |
| `SEA-54` | TASK-015, TASK-016, TASK-017, TASK-023, TASK-028 | ✅ |
| `SEA-55` | TASK-015, TASK-023, TASK-028 | ✅ |
| `SEA-56` | TASK-015, TASK-023, TASK-028 | ✅ |
| `SEA-57` | TASK-011, TASK-018, TASK-023, TASK-028 | ✅ |
| `SEA-27` | TASK-009, TASK-018, TASK-029 | ✅ |
| `SEA-28` | TASK-017 | ✅ |
| `SEA-29` | TASK-017, TASK-018 | ✅ |
| `SEA-30` | TASK-009, TASK-018 | ✅ |
| `SEA-31` | TASK-009, TASK-018, TASK-029 | ✅ |
| `SEA-58` | TASK-002, TASK-017 | ✅ |
| `SEA-59` | TASK-002, TASK-017 | ✅ |
| `SEA-60` | TASK-018, TASK-019 | ✅ |
| `SEA-32` | TASK-016 | ✅ |
| `SEA-33` | TASK-016 | ✅ |
| `SEA-34` | TASK-016 | ✅ |
| `SEA-61` | TASK-023, TASK-028 | ✅ |
| `SEA-62` | TASK-016, TASK-023 | ✅ |
| `SEA-63` | TASK-022, TASK-025 | ✅ |
| `SEA-64` | TASK-020 | ✅ |
| `SEA-65` | TASK-022 | ✅ |
| `SEA-66` | TASK-022 | ✅ |
| `SEA-90` | TASK-014, TASK-024 | ✅ |
| `SEA-91` | TASK-014, TASK-024 | ✅ |
| `SEA-92` | TASK-014, TASK-024 | ✅ |
| `SEA-93` | TASK-021, TASK-025 | ✅ |
| `SEA-94` | TASK-025 | ✅ |
| `SEA-95` | TASK-023, TASK-028 | ✅ |
| `SEA-96` | TASK-017, TASK-029 | ✅ |
| `SEA-97` | TASK-003, TASK-010, TASK-019 | ✅ |
| `SEA-98` | TASK-019 | ✅ |
| `SEA-99` | TASK-011 | ✅ |
| `SEA-100` | TASK-003, TASK-011 | ✅ |
| `SEA-101` | TASK-008, TASK-023 | ✅ |
| `SEA-102` | TASK-019 | ✅ |
| `SEA-103` | TASK-019 | ✅ |
| `SEA-104` | TASK-019, TASK-024 | ✅ |
| `SEA-105` | TASK-011 | ✅ |
| `SEA-106` | TASK-008, TASK-019 | ✅ |
| `SEA-107` | TASK-009, TASK-019 | ✅ |
| `SEA-108` | TASK-001, TASK-002 | ✅ |
| `SEA-109` | TASK-022 | ✅ |
| `SEA-110` | TASK-014 | ✅ |

Cobertura: 89/89

## Dependências

| Task | Depende de | Onda | Ondas das dependências |
|---|---|---|---|
| TASK-001 | — | 1 | — |
| TASK-002 | TASK-001 | 2 | 1 |
| TASK-003 | TASK-001 | 2 | 1 |
| TASK-004 | TASK-001 | 2 | 1 |
| TASK-005 | TASK-002, TASK-004 | 3 | 2, 2 |
| TASK-006 | TASK-001 | 2 | 1 |
| TASK-007 | TASK-004, TASK-005, TASK-006 | 4 | 2, 3, 2 |
| TASK-008 | TASK-004, TASK-005, TASK-006 | 4 | 2, 3, 2 |
| TASK-009 | TASK-004, TASK-005, TASK-006 | 4 | 2, 3, 2 |
| TASK-010 | TASK-002, TASK-005, TASK-007, TASK-008, TASK-009 | 5 | 2, 3, 4, 4, 4 |
| TASK-011 | TASK-003, TASK-006 | 3 | 2, 2 |
| TASK-012 | TASK-002, TASK-003, TASK-005, TASK-010 | 6 | 2, 2, 3, 5 |
| TASK-013 | TASK-006 | 3 | 2 |
| TASK-014 | TASK-001, TASK-003, TASK-006, TASK-013 | 4 | 1, 2, 2, 3 |
| TASK-015 | TASK-006 | 3 | 2 |
| TASK-016 | TASK-006, TASK-015 | 5 | 2, 3 |
| TASK-017 | TASK-006, TASK-015 | 5 | 2, 3 |
| TASK-018 | TASK-010, TASK-017 | 6 | 5, 5 |
| TASK-019 | TASK-003, TASK-010, TASK-013, TASK-014, TASK-018 | 7 | 2, 5, 3, 4, 6 |
| TASK-020 | TASK-003, TASK-010, TASK-013 | 6 | 2, 5, 3 |
| TASK-021 | TASK-003, TASK-010, TASK-013 | 6 | 2, 5, 3 |
| TASK-022 | TASK-002, TASK-010, TASK-013, TASK-018 | 12 | 2, 5, 3, 6 |
| TASK-023 | TASK-010, TASK-015, TASK-016 | 12 | 5, 3, 5 |
| TASK-024 | TASK-011, TASK-012, TASK-014, TASK-019 | 8 | 3, 6, 4, 7 |
| TASK-025 | TASK-011, TASK-012, TASK-021, TASK-022 | 13 | 3, 6, 6, 12 |
| TASK-026 | TASK-011, TASK-012, TASK-020 | 9 | 3, 6, 6 |
| TASK-027 | TASK-011, TASK-012, TASK-020 | 10 | 3, 6, 6 |
| TASK-028 | TASK-011, TASK-012, TASK-023 | 14 | 3, 6, 12 |
| TASK-029 | TASK-011, TASK-012, TASK-018 | 11 | 3, 6, 6 |
| TASK-030 | TASK-005, TASK-012 | 12 | 3, 6 |
| TASK-031 | TASK-030 | 15 | 12 |
| TASK-032 | TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029 | 15 | 8, 13, 9, 10, 14, 11 |

## Contratos (produtor × consumidores)

| Contrato | Produtor | Consumidores |
|---|---|---|
| CT-1 | TASK-002 | TASK-005, TASK-010, TASK-012, TASK-019, TASK-022 |
| CT-2 | TASK-001 | TASK-002, TASK-014 |
| CT-3 | TASK-003 | TASK-011, TASK-012, TASK-014, TASK-019, TASK-020, TASK-021 |
| CT-4 | TASK-004 | TASK-005, TASK-007, TASK-008, TASK-009, TASK-012 |
| CT-5 | TASK-005 | TASK-007, TASK-008, TASK-009, TASK-030 |
| CT-6 | TASK-006 | TASK-007, TASK-008, TASK-009, TASK-011, TASK-013, TASK-014, TASK-015, TASK-016, TASK-017, TASK-018, TASK-023 |
| CT-7 | TASK-006 | TASK-007, TASK-008, TASK-009, TASK-010, TASK-018, TASK-020, TASK-021, TASK-022, TASK-023 |
| CT-8 | TASK-007 | TASK-010 |
| CT-9 | TASK-010 | TASK-012, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023 |
| CT-10 | TASK-013 | TASK-014, TASK-020, TASK-021 |
| CT-11 | TASK-013 | TASK-019, TASK-022 |
| CT-12 | TASK-014 | TASK-019, TASK-024 |
| CT-13 | TASK-015 | TASK-016, TASK-017, TASK-023 |
| CT-14 | TASK-016 | TASK-023 |
| CT-15 | TASK-017 | TASK-018 |
| CT-16 | TASK-018 | TASK-019, TASK-022, TASK-029 |
| CT-17 | TASK-019 | TASK-024 |
| CT-18 | TASK-020 | TASK-026, TASK-027 |
| CT-19 | TASK-021 | TASK-025 |
| CT-20 | TASK-022 | TASK-025 |
| CT-21 | TASK-023 | TASK-028 |
| CT-22 | TASK-011 | TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029 |
| CT-23 | TASK-005 | TASK-007, TASK-008, TASK-009, TASK-010, TASK-012, TASK-018, TASK-019, TASK-020, TASK-021, TASK-022, TASK-023 |
| CT-24 | TASK-008 | TASK-010 |
| CT-25 | TASK-009 | TASK-010 |
| CT-26 | TASK-012 | TASK-024, TASK-025, TASK-026, TASK-027, TASK-028, TASK-029, TASK-030, TASK-032 |
| CT-27 | — (existente/externo) | — |

## Granularidade e testes

| Task | Produção | Teste | Testes | Paralelo-seguro | Agente |
|---|---|---|---|---|---|
| TASK-001 | 2 | 1 | unit | sim | hm-engineer |
| TASK-002 | 2 | 2 | unit | sim | hm-engineer |
| TASK-003 | 2 | 1 | unit | sim | hm-engineer |
| TASK-004 | 2 | 1 | unit | sim | hm-engineer |
| TASK-005 | 2 | 2 | integration | sim | hm-engineer |
| TASK-006 | 2 | 1 | unit | sim | hm-engineer |
| TASK-007 | 2 | 1 | integration | sim | hm-engineer |
| TASK-008 | 1 | 1 | integration | sim | hm-engineer |
| TASK-009 | 2 | 1 | integration | sim | hm-engineer |
| TASK-010 | 2 | 1 | integration | sim | hm-engineer |
| TASK-011 | 2 | 2 | unit | sim | hm-engineer |
| TASK-012 | 1 | 1 | integration | sim | hm-engineer |
| TASK-013 | 2 | 2 | unit | sim | hm-engineer |
| TASK-014 | 2 | 2 | unit | sim | hm-engineer |
| TASK-015 | 1 | 1 | unit | sim | hm-engineer |
| TASK-016 | 1 | 1 | unit | sim | hm-engineer |
| TASK-017 | 1 | 1 | unit | sim | hm-engineer |
| TASK-018 | 1 | 1 | integration | sim | hm-engineer |
| TASK-019 | 1 | 1 | integration | sim | hm-engineer |
| TASK-020 | 2 | 2 | integration | sim | hm-engineer |
| TASK-021 | 1 | 1 | integration | sim | hm-engineer |
| TASK-022 | 1 | 1 | integration | sim | hm-engineer |
| TASK-023 | 1 | 1 | integration | sim | hm-engineer |
| TASK-024 | 2 | 1 | integration | sim | hm-engineer |
| TASK-025 | 2 | 1 | integration | sim | hm-engineer |
| TASK-026 | 2 | 1 | integration | sim | hm-engineer |
| TASK-027 | 2 | 1 | integration | sim | hm-engineer |
| TASK-028 | 2 | 1 | integration | sim | hm-engineer |
| TASK-029 | 2 | 1 | integration | sim | hm-engineer |
| TASK-030 | 1 | 1 | unit | sim | hm-engineer |
| TASK-031 | 2 | 1 | unit | sim | hm-engineer |
| TASK-032 | 1 | 1 | integration | sim | hm-engineer |
