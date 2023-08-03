import confluent_kafka
import prometheus_client
import psycopg2
import datetime
import json
import utils
import os

postgres_db = os.environ.get('POSTGRES_DB')
postgres_password = os.environ.get('POSTGRES_PASSWORD')

utils.check_connection_status("postgres", 5432)
p = psycopg2.connect(host="postgres", user="root", port=5432, database=postgres_db, password=postgres_password)
k = confluent_kafka.Consumer(
    {"bootstrap.servers": "kafka:29092", "group.id": "logs-group-1", "auto.offset.reset": "earliest"})
k.subscribe(["logs"])
p.autocommit = True

PG_INSERTS = prometheus_client.Counter("pg_inserts", "Postgres Inserts")
PG_ERRORS = prometheus_client.Counter("pg_errors", "Postgres Errors")

cursor = p.cursor()

def accumulate_item_analytics(cursor, item_key, total_views, total_time_spent, last_viewed, followed_by_stop_count):
    # Accumulate values in item_analytics table
    accumulate_query = """
        INSERT INTO item_analytics (
            item_key,
            total_views,
            total_time_spent,
            last_viewed,
            followed_by_stop_count
        ) VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (item_key)
        DO UPDATE
        SET
            total_views = item_analytics.total_views + EXCLUDED.total_views,
            total_time_spent = item_analytics.total_time_spent + EXCLUDED.total_time_spent,
            last_viewed = GREATEST(item_analytics.last_viewed, EXCLUDED.last_viewed),
            followed_by_stop_count = item_analytics.followed_by_stop_count + EXCLUDED.followed_by_stop_count;
    """

    try:
        cursor.execute(accumulate_query, (item_key, total_views, total_time_spent, last_viewed, followed_by_stop_count))
        num_updated_rows = cursor.rowcount
        print("Accumulated", num_updated_rows, "rows in item_analytics")
    except Exception as e:
        print("Error during accumulation:", e)

def update_time_spent_for_session(cursor):
    # Update the time_spent in the fct_hourly_metric table using the calculated time difference
    update_query = """
        WITH example_with_next_evt AS (
        SELECT
            session_id,
            evnt_stamp,
            item_id,
            evt_type,
            LEAD(evnt_stamp) OVER (PARTITION BY session_id ORDER BY evnt_stamp) AS next_evt_unix
        FROM fct_hourly_metric
        )

        SELECT
        session_id,
        item_id,
        next_evt_unix - evnt_stamp AS time_spent
        FROM example_with_next_evt
        WHERE
        evt_type = 'view';
    """

    try:
        cursor.execute(update_query)
        num_updated_rows = cursor.rowcount
        print("Updated", num_updated_rows)
    except Exception as e:
        print("Error during update for session:", e)


def insert_to_postgres(store):

    # store = [evt_log for evt_log in store if evt_log.get("session") is not None and evt_log.get("ts") is not None]

    insert_query = """
        INSERT INTO fct_hourly_metric (
            date_stamp,
            time_stamp,
            evnt_stamp,
            user_id,
            session_id,
            evt_type,
            item_id
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    insert_data = []

    store = sorted(store, key=lambda x: (x["session"], x["ts"]))

    for evt_log in store:
        cur_date = datetime.datetime.fromtimestamp(evt_log["ts"])

        insert_data.append((
            cur_date.date(),
            cur_date.replace(minute=0, second=0, microsecond=0),
            evt_log.get("ts"),
            evt_log.get("user_id"),
            evt_log.get("session"),
            evt_log.get("type"),
            evt_log.get("item_id")
        ))

    try:
        cursor.executemany(insert_query, insert_data)
        PG_INSERTS.inc(len(insert_data))
    except Exception as e:
        PG_ERRORS.inc()
        print("Worker error", e)


    print("Inserted", len(insert_data), "rows")

def accumulate_item_analytics(cursor, store):
    for evt_log in store:
        accumulate_query = """
            INSERT INTO item_analytics (
                item_key,
                total_views,
                total_time_spent,
                last_viewed,
                followed_by_stop_count
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (item_key)
            DO UPDATE
            SET
                total_views = item_analytics.total_views + %s,
                total_time_spent = item_analytics.total_time_spent + %s,
                last_viewed = GREATEST(item_analytics.last_viewed, %s),
                followed_by_stop_count = item_analytics.followed_by_stop_count + %s;
        """

    item_key = evt_log.get("item_id")
    time_spent = evt_log.get("time_spent", 0)
    followed_by_stop = evt_log.get("followed_by_stop", False)
    ts = datetime.datetime.fromtimestamp(evt_log.get("ts")).strftime('%Y-%m-%d %H:%M:%S')

    try:
        cursor.execute(accumulate_query, (
            item_key,
            1,  # Increment total_views by 1 for each event log
            time_spent,
            ts,
            1 if followed_by_stop else 0,  # Increment followed_by_stop_count by 1 if True, otherwise 0
            1,  # Increment total_views again for update clause
            time_spent,  # Increment total_time_spent again for update clause
            ts,  # Use the same timestamp for the GREATEST function
            1 if followed_by_stop else 0,  # Increment followed_by_stop_count again for update clause
        ))
        print("Accumulated", cursor.rowcount, "rows in item_analytics")
    except Exception as e:
        print("Error during accumulation:", e)

def main():
    store = []
    while True:
        msg = k.poll(1.0)
        if msg is None: continue
        if msg.error(): continue
        raw_res = msg.value().decode("utf-8")
        cur_res = json.loads(raw_res)
        store.append(cur_res)
        if len(store) > 20:
            accumulate_item_analytics(cursor, store)
            store = []




if __name__ == "__main__":
    prometheus_client.start_http_server(9965)
    main()
