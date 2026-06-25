import sqlite3
import pandas as pd
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
        wind_cols = [c for c in gen_mix.columns if 'Wind' in str(c)]
        wind = gen_mix[wind_cols].sum(axis=1).to_frame(name='actual_wind_mw')
        wind_hourly = wind.resample('h').mean()  # Resample to hourly data

        # Isolate Solar Columns and sum them up
        solar_cols = [col for col in gen_mix.columns if 'Solar' in str(col)]
        solar = gen_mix[solar_cols].sum(axis=1).to_frame(name='actual_solar_mw')
        solar_hourly = solar.resample('h').mean()  # Resample to hourly data

        # Getting Total System Load (Demand) (TSL) from the ENTSO-E API and converting to a DataFrame
        # Summing up the gen mix as a demand proxy due to lack of query data
        # Extract Actual Demand/Load proxy out of the working Generation Mix 
        # (The sum of all generation columns tells us exactly what the real-time system demand was)
        demand_proxy = gen_mix.sum(axis=1).to_frame(name='demand_mw')
        demand_proxy_hourly = demand_proxy.resample('h').mean()  # Resample to hourly data

        # Rename columns explicitly after resampling
        demand_proxy_hourly.columns = ['demand_mw']
        wind_hourly.columns = ['actual_wind_mw']
        solar_hourly.columns = ['actual_solar_mw']

        # Interconnector Flows (Net exchange with Great Britain)
        # Negative = Exporting to GB, Positive = Importing from GB
        flows = client.query_crossborder_flows('GB', Zone, start=start, end=end).to_frame(name='net_gb_flow_mw')
        flows.index = flows.index.tz_convert('UTC') # Convert to Dublin timezone

        # Merge all infto a single Clean DataFrame

        irish_grid_df = prices.join([demand_proxy_hourly, wind_hourly, solar_hourly, flows], how='left')

        # Fill any missing values with forward fill method
        irish_grid_df['net_gb_flow_mw'] = irish_grid_df['net_gb_flow_mw'].ffill(limit=3)  # Forward fill for up to 3 hours
        irish_grid_df['actual_solar_mw'] = irish_grid_df['actual_solar_mw'].fillna(0)  # Fill NaN values with 0

        # Calculate our residual load insight
        irish_grid_df['net_demand_mw'] = irish_grid_df['demand_mw'] - irish_grid_df['actual_wind_mw'] - irish_grid_df['actual_solar_mw']

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

        response = requests.get(url).json()

        # Parsing Json into a clean Pandas DataFrame
        weather_df = pd.DataFrame(response['hourly'])
        weather_df['time'] = pd.to_datetime(weather_df['time'], utc=True)
        weather_df.set_index('time', inplace=True)

        # Open-Meteo weather data is already UTC, but let's be absolutely explicit
        weather_df.index = weather_df.index.tz_convert('UTC')

        # Join the grid dataframe and the weather dataframe on their matching UTC indices
        master_df = irish_grid_df.join(weather_df, how='left')

        # Format DataFrame Index for SQLite Storage (Strings work best for timestamps in SQLite)
        master_df.index = master_df.index.strftime('%Y-%m-%d %H:%M:%S')
        master_df.index.name = 'timestamp'
        master_df = master_df.reset_index()

        # Database Upsert Commit
        conn = sqlite3.connect('irish_grid.db')

        # Using a temporary table to handle the Upsert cleanly via pandas
        master_df.to_sql('temp_market_actuals', conn, if_exists='replace', index=False)

        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO market_actuals 
            SELECT * FROM temp_market_actuals
        ''')

        cursor.execute('DROP TABLE temp_market_actuals')
        conn.commit()
        conn.close()
        
        print("💾 Database securely updated with the latest operational hours!")
        
    except Exception as e:
        print(f"❌ Pipeline sync failed: {e}")

if __name__ == "__main__":
    run_pipeline()
