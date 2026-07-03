# I-SEM Electricity Market & Physical Grid Data Pipeline

## High-Level Overview
This project captures and stores Irish electricity market, grid dispatch, and weather data in a local SQLite database (`irish_grid.db`).

The pipeline ingests the last 3 days of ENTSO-E market and generation telemetry, enriches it with hourly Open-Meteo weather observations, and upserts hourly operational facts into a single `market_actuals` table.

---

## Current Project Files
- `fetch_data.py` — main ingestion pipeline and DB upsert logic
- `init_db.py` — creates the SQLite `market_actuals` schema
- `clear_db.py` — drops and rebuilds the local `market_actuals` table
- `Analytics.ipynb` — notebook for offline analysis and reporting
- `irish_grid.db` — local SQLite store containing the ingested records
- `README.md` — project documentation

---

## Architecture Design & Data Flow
1. **Database Initialization (`init_db.py`)**: Creates `irish_grid.db` and defines the `market_actuals` table with `timestamp` as the primary key.
2. **Data Ingestion (`fetch_data.py`)**: Pulls the last 3 days of hourly data from ENTSO-E and hourly weather from Open-Meteo, then consolidates it into a master hourly DataFrame.
3. **Data Enrichment**: Computes derived metrics such as SNSP-based transmission capacity and utilization percentage.
4. **Storage (`irish_grid.db`)**: Uses `INSERT OR REPLACE` to upsert `market_actuals`, preserving the latest values for each timestamp.
5. **Database Reset (`clear_db.py`)**: Drops the `market_actuals` table and runs `VACUUM` so the database can be rebuilt cleanly.

---

## Usage
1. Initialize the database schema:
   ```bash
   python init_db.py
   ```
2. Sync the pipeline and update the database:
   ```bash
   python fetch_data.py
   ```
3. Reset the database if needed:
   ```bash
   python clear_db.py
   ```

> Note: `fetch_data.py` currently uses an embedded ENTSO-E API key and queries Open-Meteo hourly temperature and 100m wind speed.

---

## Database Schema
The `market_actuals` table stores hourly operational records with the following columns:

| Column Name | Data Type | Description |
| :--- | :--- | :--- |
| `timestamp` | TEXT | UTC hourly timestamp, primary key |
| `price_eur_mwh` | REAL | Day-Ahead wholesale electricity price |
| `total_supply_mw` | REAL | Demand proxy derived from summed generation mix |
| `gen_gas_mw` | REAL | Fossil gas generation |
| `gen_coal_mw` | REAL | Fossil coal generation |
| `gen_oil_mw` | REAL | Fossil oil/distillate generation |
| `gen_hydro_mw` | REAL | Hydro generation |
| `gen_peat_mw` | REAL | Peat generation |
| `gen_biowaste_mw` | REAL | Biomass, waste, or other thermal renewable generation |
| `actual_wind_mw` | REAL | Actual wind generation |
| `actual_solar_mw` | REAL | Actual solar generation |
| `wind_speed_100m` | REAL | 100m wind speed from Open-Meteo |
| `temperature_2m` | REAL | 2m air temperature from Open-Meteo |
| `net_gb_flow_mw` | REAL | Net flow with GB (positive = import, negative = export) |
| `transmission_capacity_snsp` | REAL | 75% SNSP capacity threshold calculated from total supply |
| `transmission_capacity_utilization_pct` | REAL | Percent of SNSP capacity used by non-synchronous energy |

---

## Notes on Data Processing
- `total_supply_mw` is built from the sum of generation mix columns, acting as a demand proxy where direct demand queries are not available.
- `net_gb_flow_mw` is forward-filled for up to 3 hours to maintain continuity during missing cross-border flow data.
- `actual_solar_mw` is filled with `0` when solar estimates are missing.
- The code currently does not persist a separate `net_demand_mw` column; that calculation remains commented out in `fetch_data.py`.

---

## Analytical Focus
The project supports analysis of:
- price dynamics across the Irish market
- generation mix composition, including wind, solar, peat, biowaste, and conventional fuels
- interconnector flow patterns with Great Britain
- SNSP utilization and system stability margins
- weather correlations using 100m wind speed and 2m temperature
