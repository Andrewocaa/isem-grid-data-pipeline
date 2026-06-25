import sqlite3

def initialize_database():
    # Connect to the database (creates 'irish_grid.db' automatically if it doesn't exist)
    conn = sqlite3.connect('irish_grid.db')
    cursor = conn.cursor()

    # Create the 'market_actuals' table if it doesn't exist with unique constraint on timestamp
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_actuals (
            timestamp TEXT PRIMARY KEY,
            price_eur_mwh REAL,
            demand_mw REAL,
            actual_wind_mw REAL,
            actual_solar_mw REAL,
            wind_speed_100m REAL,
            temperature_2m REAL,
            net_gb_flow_mw REAL,
            net_demand_mw REAL
        )
    ''')
    
    conn.commit()
    conn.close()
    print("🚀 SQLite Database 'irish_grid.db' initialized with strict primary keys successfully!")

if __name__ == "__main__":
    initialize_database()