import sqlite3
import pandas as pd
import numpy as np
import requests
from entsoe import EntsoePandasClient


# Configuration
API_KEY = 'c2568f16-1a73-46d6-ba10-8bdd6d9575e2'
client = EntsoePandasClient(api_key=API_KEY)
Zone = 'IE_SEM'  # Ireland


def run_pipeline():
    # Fetch data from ENTSO-E and lock pipeline to the last 3 days for efficient daily incremental updates
    start = pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=3)
    end = pd.Timestamp.now(tz='UTC')

    print(f"🔄 Syncing grid data from {start} to {end}...")

    #Query the All-Island Irish Market Prices from the ENTSO-E API
    # 'IE_SEM' is the specific market code for the Integrated Single Electricity Market (SEM) in Ireland


    try:
    

        # Getting Irish Day Ahead Prices from the ENTSO-E API and converting to a DataFrame
        prices = client.query_day_ahead_prices(Zone, start=start, end=end).to_frame(name='price_eur_mwh')
        prices.index = prices.index.tz_convert('UTC')  # Convert to Dublin timezone


        # Generation Mix (To isolate Wind Output)
        gen_mix = client.query_generation(Zone, start=start, end=end)
        gen_mix.index = gen_mix.index.tz_convert('UTC') # Convert to Dublin timezone


        # Isolate cleanly matching fuel types (omitting consumption and grid adjustments)
        generation_cols = [
            c for c in gen_mix.columns 
            if 'Consumption' not in str(c) 
            and 'Exchange' not in str(c)
        ]
        

        # Filter SPECIFICALLY from the clean generation pool
        gas_cols   = [c for c in generation_cols if 'Fossil Gas' in str(c)]
        coal_cols  = [c for c in generation_cols if 'Fossil Hard Coal' in str(c)]
        oil_cols   = [c for c in generation_cols if 'Fossil Oil' in str(c) or 'Distillate' in str(c)]
        peat_cols  = [c for c in generation_cols if 'Fossil Peat' in str(c)] # <--- Added explicitly
        hydro_cols = [c for c in generation_cols if 'Hydro' in str(c)]
        wind_cols  = [c for c in generation_cols if 'Wind' in str(c)]
        solar_cols = [c for c in generation_cols if 'Solar' in str(c)]
        # This captures the remaining green thermal assets (like Edenderry's new biomass profile)
        bio_waste_cols = [c for c in generation_cols if 'Biomass' in str(c) or 'Waste' in str(c) or 'Other' in str(c)]

        # Resample each stream into hourly means using clean horizontal sums
        gas_hourly   = gen_mix[gas_cols].sum(axis=1, min_count=1).to_frame(name='gen_gas_mw').resample('h').mean()
        coal_hourly  = gen_mix[coal_cols].sum(axis=1, min_count=1).to_frame(name='gen_coal_mw').resample('h').mean()
        oil_hourly   = gen_mix[oil_cols].sum(axis=1, min_count=1).to_frame(name='gen_oil_mw').resample('h').mean()
        peat_hourly  = gen_mix[peat_cols].sum(axis=1, min_count=1).to_frame(name='gen_peat_mw').resample('h').mean() # <--- Added
        hydro_hourly = gen_mix[hydro_cols].sum(axis=1, min_count=1).to_frame(name='gen_hydro_mw').resample('h').mean()
        wind_hourly  = gen_mix[wind_cols].sum(axis=1, min_count=1).to_frame(name='actual_wind_mw').resample('h').mean()
        solar_hourly = gen_mix[solar_cols].sum(axis=1, min_count=1).to_frame(name='actual_solar_mw').resample('h').mean()
        biowaste_hourly  = gen_mix[bio_waste_cols].sum(axis=1, min_count=1).to_frame(name='gen_biowaste_mw').resample('h').mean()

    
        
        
        #wind = gen_mix[wind_cols].sum(axis=1).to_frame(name='actual_wind_mw')
        #solar = gen_mix[solar_cols].sum(axis=1).to_frame(name='actual_solar_mw')
        
        
        #wind_hourly = wind.resample('h').mean()  # Resample to hourly data
        #solar_hourly = solar.resample('h').mean()  # Resample to hourly data


        # Getting Total System Load (Demand) (TSL) from the ENTSO-E API and converting to a DataFrame
        # Summing up the gen mix as a demand proxy due to lack of query data
        # Extract Actual Demand/Load proxy out of the working Generation Mix 
        # (The sum of all generation columns tells us exactly what the real-time system demand was)
        demand_proxy = gen_mix[generation_cols].sum(axis=1, min_count=1).to_frame(name='total_supply_mw')
        demand_proxy_hourly = demand_proxy.resample('h').mean()


        # Rename columns explicitly after resampling
        demand_proxy_hourly.columns = ['total_supply_mw']
        wind_hourly.columns = ['actual_wind_mw']
        solar_hourly.columns = ['actual_solar_mw']


        # Interconnector Flows (Net exchange with Great Britain)
        # Negative = Exporting to GB, Positive = Importing from GB
        flows = client.query_crossborder_flows('GB', Zone, start=start, end=end).to_frame(name='net_gb_flow_mw')
        flows.index = flows.index.tz_convert('UTC') # Convert to Dublin timezone
        flows_hourly = flows.resample('h').mean()  # Standardize flows index cleanly


        # Fetching the weather data for the same period from Open-meteo API
        start_date_str = start.strftime('%Y-%m-%d')
        end_date_str = end.strftime('%Y-%m-%d')


        # Fetching wind speed data targeting the West of Ireland (Wind Capital)
        # We are asking for wind speed at 100m height (where industrial wind turbine hubs sit)



        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude=53.35&longitude=-9.05" # Galway coordinates
            f"&hourly=temperature_2m,wind_speed_100m" # hourly temp & wind speed measured 2 metres and 100 metres above ground level respectively
            f"&start_date={start_date_str}&end_date={end_date_str}"
            f"&timezone=UTC"
        )


        # --- FIX: Changed url base to archive-api ---
        #url = (
            #f"https://archive-api.open-meteo.com/v1/archive?"
            #f"latitude=53.35&longitude=-9.05"  # Galway coordinates
            #f"&hourly=temperature_2m,wind_speed_100m"
            #f"&start_date={start_date_str}&end_date={end_date_str}"
            #f"&timezone=UTC"
        #)



        response = requests.get(url).json()


        # Parsing Json into a clean Pandas DataFrame
        weather_df = pd.DataFrame(response['hourly'])
        weather_df['time'] = pd.to_datetime(weather_df['time'], utc=True)
        weather_df.set_index('time', inplace=True)
        weather_df.index = weather_df.index.tz_convert('UTC')

        # Create an empty blueprint frame anchored strictly to the validated prices index
        master_df = pd.DataFrame(index=prices.index)
        master_df.index.name = 'timestamp'


        # Explicitly map grid columns by matching primary key timestamps
        master_df['price_eur_mwh'] = prices['price_eur_mwh']
        master_df['total_supply_mw'] = demand_proxy_hourly['total_supply_mw']
        master_df['actual_wind_mw']  = wind_hourly['actual_wind_mw']
        master_df['actual_solar_mw'] = solar_hourly['actual_solar_mw']
        master_df['net_gb_flow_mw']  = flows_hourly['net_gb_flow_mw']

        # Map Every Fuel Type Explicitly
        master_df['gen_gas_mw']      = gas_hourly['gen_gas_mw']
        master_df['gen_coal_mw']     = coal_hourly['gen_coal_mw']
        master_df['gen_oil_mw']      = oil_hourly['gen_oil_mw']
        master_df['gen_hydro_mw']    = hydro_hourly['gen_hydro_mw']
        master_df['gen_peat_mw']     = peat_hourly['gen_peat_mw'] # <--- Added
        master_df['gen_biowaste_mw'] = biowaste_hourly['gen_biowaste_mw']
        

        # Apply data cleaning guardrails safely on the master dataframe
        master_df['net_gb_flow_mw']  = master_df['net_gb_flow_mw'].ffill(limit=3)
        master_df['actual_solar_mw'] = master_df['actual_solar_mw'].fillna(0)


        # Explicitly map weather parameters into their designated columns
        master_df['temperature_2m']  = weather_df['temperature_2m']
        master_df['wind_speed_100m'] = weather_df['wind_speed_100m']

        # Calculate Net Demand last using explicit master_df columns
        #master_df['net_demand_mw']   = master_df['total_supply_mw'] - master_df['actual_wind_mw'] - master_df['actual_solar_mw']

        # FACTUAL TRANSMISSION CAPACITY ENGINEERING
        master_df['transmission_capacity_snsp'] = master_df['total_supply_mw'] * 0.75
        total_non_sync = (
            master_df['actual_wind_mw'].fillna(0) + 
            master_df['actual_solar_mw'].fillna(0) + 
            master_df['net_gb_flow_mw'].clip(lower=0).fillna(0)
        )
        
        master_df['transmission_capacity_utilization_pct'] = np.where(
            master_df['total_supply_mw'] > 500.0,
            (total_non_sync / master_df['transmission_capacity_snsp']) * 100, 
            np.nan
        )


        # Format DataFrame Index for SQLite Storage (Strings work best for timestamps in SQLite)
        master_df.index = master_df.index.strftime('%Y-%m-%d %H:%M:%S')
        master_df.index.name = 'timestamp'
        master_df = master_df.reset_index()


        # Database Upsert Commit
        conn = sqlite3.connect('irish_grid.db')


        # Using a temporary table to handle the Upsert cleanly via pandas
        master_df.to_sql('temp_market_actuals', conn, if_exists='replace', index=False)

        cursor = conn.cursor()
        
        # Explicitly declare matching destination columns to avoid position shifts
        cursor.execute('''
            INSERT OR REPLACE INTO market_actuals (
                timestamp, price_eur_mwh, total_supply_mw, gen_gas_mw, gen_coal_mw, gen_oil_mw, gen_hydro_mw, gen_peat_mw, gen_biowaste_mw,
                actual_wind_mw, actual_solar_mw, wind_speed_100m, temperature_2m, 
                net_gb_flow_mw,transmission_capacity_snsp, 
                transmission_capacity_utilization_pct
            ) 
            SELECT 
                timestamp, price_eur_mwh, total_supply_mw, gen_gas_mw, gen_coal_mw, gen_oil_mw, gen_hydro_mw, gen_peat_mw, gen_biowaste_mw,
                actual_wind_mw, actual_solar_mw, wind_speed_100m, temperature_2m, 
                net_gb_flow_mw,transmission_capacity_snsp, 
                transmission_capacity_utilization_pct 
            FROM temp_market_actuals
        ''')

        cursor.execute('DROP TABLE temp_market_actuals')
        conn.commit()
        conn.close()
        
        print("💾 Database securely updated with the latest operational hours!")

        
        
    except Exception as e:
        print(f"❌ Pipeline sync failed: {e}")


if __name__ == "__main__":
    run_pipeline()
