import psycopg2
import os
import dotenv

dotenv.load_dotenv()

postgres_db = os.environ.get('POSTGRES_DB')
postgres_password = os.environ.get('POSTGRES_PASSWORD')

query = """
CREATE TABLE IF NOT EXISTS view_times (
  session_id UUID,
  item_id UUID,
  time_spent INTEGER
);

WITH update_fct_cte AS (
  SELECT
    session_id::UUID,
    item_id::UUID,
    evnt_stamp,
    evt_type,
    LEAD(evnt_stamp) OVER (PARTITION BY session_id ORDER BY evnt_stamp) AS next_evnt_stamp
  FROM public.fct_hourly_metric
)
INSERT INTO view_times (session_id, item_id, time_spent)
SELECT
  session_id,
  item_id,
  (next_evnt_stamp - evnt_stamp)::INTEGER AS time_spent
FROM update_fct_cte
WHERE
  next_evnt_stamp IS NOT NULL
  AND evt_type = 'view';

DELETE FROM view_times WHERE session_id IS NULL;
"""

try:
    connection = psycopg2.connect(host="localhost", user="root", port=5432, database=postgres_db, password=postgres_password)
    cursor = connection.cursor()
    cursor.execute(query)
    connection.commit()
    print("Update fct_hourly_metric query executed successfully")

except Exception as e:
    print("Error:", e)
    
finally:
    if cursor:
        cursor.close()
    if connection:
        connection.close()

"""
Commands this like can be used to check the results of this script in pgAdmin:

--- SELECT * FROM view_times ORDER BY time_spent DESC;
--- SELECT * FROM fct_hourly_metric;

--- SELECT * FROM fct_hourly_metric WHERE session_id = '00d00454-27f0-449f-bd17-4ae7ac99558c';
--- item 8eb99e10-cd8d-4d75-b551-e938eedd5f1a was 3 seconds.
--- Manual check: CORRECT

--- SELECT * FROM fct_hourly_metric WHERE session_id = '00d5f29b-60c3-4d8a-ae3e-f3cdf50809d9';
--- item 30ea6ba3-f493-4b73-8397-b7e89a49e3ae was 0 seconds.
--- Manual check: CORRECT

--- SELECT * FROM fct_hourly_metric WHERE session_id IS NULL AND item_id = 'b85ce10e-db94-4571-b774-f2066f30109d';
--- item b85ce10e-db94-4571-b774-f2066f30109d has no session_id and 17958 seconds;
--- Manual check: The CTE query creates partions on session_id, so it creates a huge session_id = NULL partition
--- which results in sessionless views invalidly having a 'next view' in the 'session' - and so arbitrary and crazy view time calculations.
--- SOLUTION: DELETE the view rows in this table that have no session_id.

"""