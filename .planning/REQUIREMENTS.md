# Requirements: NFL Data Platform — Bronze Expansion

**Defined:** 2026-03-08
**Core Value:** A rich NFL data lake powering both fantasy football projections and game outcome predictions

## v1 Requirements

### Infrastructure Prerequisites

- [ ] **INFRA-01**: Bronze ingestion script works locally without AWS credentials (local-first with S3 as optional)
- [x] **INFRA-02**: Season validation is dynamic (current year + 1) instead of hardcoded 2025
- [x] **INFRA-03**: Adapter layer isolates all nfl-data-py import_* calls into a single module for future nflreadpy migration
- [ ] **INFRA-04**: Bronze CLI uses registry/dispatch pattern instead of if/elif chain (supports 15+ data types)
- [x] **INFRA-05**: Per-data-type season availability config (NGS starts 2016, PFR starts 2018, etc.)

### Play-by-Play Data

- [ ] **PBP-01**: Full PBP ingested with ~80 curated columns including EPA, WPA, CPOE, air yards, success rate
- [ ] **PBP-02**: PBP processes one season at a time to manage memory (not all seasons at once)
- [ ] **PBP-03**: PBP uses column subsetting via columns parameter (not all 390 columns)
- [ ] **PBP-04**: PBP ingested for seasons 2020-2025 in Bronze layer

### Advanced Stats

- [ ] **ADV-01**: NGS data ingested for 3 stat types (passing, rushing, receiving) for seasons 2016-2025
- [ ] **ADV-02**: PFR weekly stats ingested for 4 sub-types (pass, rush, rec, def) for seasons 2018-2025
- [ ] **ADV-03**: PFR seasonal stats ingested for 4 sub-types for seasons 2018-2025
- [ ] **ADV-04**: QBR data ingested (weekly + seasonal) for seasons 2006-2025
- [ ] **ADV-05**: Depth charts ingested for seasons 2020-2025

### Context Data

- [ ] **CTX-01**: Draft picks data ingested for seasons 2000-2025
- [ ] **CTX-02**: Combine data ingested for seasons 2000-2025

### Documentation

- [ ] **DOC-01**: NFL Data Dictionary updated to reflect all new Bronze data types with actual column names
- [ ] **DOC-02**: NFL Game Prediction Data Model updated to mark implemented vs planned tables
- [ ] **DOC-03**: Bronze Layer Data Inventory updated to reflect actual 40+ files across all data types
- [ ] **DOC-04**: Data model implementation guide updated with realistic phase status

### Validation

- [ ] **VAL-01**: validate_data() in NFLDataFetcher supports all new data types with required column checks
- [ ] **VAL-02**: All new fetch methods have error handling for API timeouts and empty responses
- [ ] **VAL-03**: Tests added for new fetch methods (minimum 1 per data type)

## v2 Requirements

### Silver Layer for Game Prediction
- **SLV-01**: Team-week EPA aggregates (rolling offensive/defensive EPA per play)
- **SLV-02**: Exponentially weighted rolling metrics for team performance
- **SLV-03**: Matchup feature generation (team A offense vs team B defense)

### ML Pipeline
- **ML-01**: Feature engineering pipeline producing 200+ ML features per game
- **ML-02**: Random Forest / XGBoost model training with leave-one-season-out validation
- **ML-03**: Target 65%+ accuracy, <3.5 point spread MAE

### Migration
- **MIG-01**: Migrate from nfl-data-py to nflreadpy when feature parity confirmed

## Out of Scope

| Feature | Reason |
|---------|--------|
| Officials/referee data | Minimal game prediction value per research |
| Full weather API | PBP already includes temp/wind; separate pipeline adds ~2pp for high complexity |
| FTN charting data | Only 3 seasons of history, insufficient for ML training |
| Win totals (import_win_totals) | Source flagged as "in flux" by nflverse; unreliable |
| SC Lines (import_sc_lines) | Verify PBP spread_line/total_line sufficiency first; likely redundant |
| Neo4j graph layer | Deferred until prediction model is validated |
| S3 sync | AWS credentials expired; local-first workflow |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 1 | Pending |
| INFRA-02 | Phase 1 | Complete |
| INFRA-03 | Phase 1 | Complete |
| INFRA-04 | Phase 1 | Pending |
| INFRA-05 | Phase 1 | Complete |
| PBP-01 | Phase 2 | Pending |
| PBP-02 | Phase 2 | Pending |
| PBP-03 | Phase 2 | Pending |
| PBP-04 | Phase 2 | Pending |
| ADV-01 | Phase 3 | Pending |
| ADV-02 | Phase 3 | Pending |
| ADV-03 | Phase 3 | Pending |
| ADV-04 | Phase 3 | Pending |
| ADV-05 | Phase 3 | Pending |
| CTX-01 | Phase 3 | Pending |
| CTX-02 | Phase 3 | Pending |
| DOC-01 | Phase 4 | Pending |
| DOC-02 | Phase 4 | Pending |
| DOC-03 | Phase 4 | Pending |
| DOC-04 | Phase 4 | Pending |
| VAL-01 | Phase 3 | Pending |
| VAL-02 | Phase 3 | Pending |
| VAL-03 | Phase 3 | Pending |

**Coverage:**
- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0

---
*Requirements defined: 2026-03-08*
*Last updated: 2026-03-08 after research synthesis*
