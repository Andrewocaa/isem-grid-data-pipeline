import sqlite3

def wipe_database():
    print("⏳ Connecting to irish_grid.db...")
    conn = sqlite3.connect('irish_grid.db')
    cursor = conn.cursor()
    
    try:
        # This completely drops the table and clears out all data rows
        print("💥 Dropping table 'market_actuals'...")
        cursor.execute("DROP TABLE IF EXISTS market_actuals")
        
        # Optional: Drop the temporary table too just in case it's lingering
        cursor.execute("DROP TABLE IF EXISTS temp_market_actuals")
        
        # Re-index the database file to shrink its file size back to 0 KB
        cursor.execute("VACUUM")
        
        conn.commit()
        print("🏁 Database wiped completely clean! It is now a blank canvas.")
        
    except Exception as e:
        print(f"❌ Failed to clear database: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    wipe_database()