import psycopg2
import datetime
import redis
import os

redis_password = os.environ.get('REDIS_PASSWORD')
postgres_db = os.environ.get('POSTGRES_DB')
postgres_password = os.environ.get('POSTGRES_PASSWORD')

r = redis.Redis(host="localhost", port=6379, db=1, password=redis_password)
connection = psycopg2.connect(host="localhost", user="root", port=5432, database=postgres_db, password=postgres_password)


with connection:
  cur = connection.cursor("sync_redis_cursor")
  cur.execute("SELECT item_key, created_at, user_id, type FROM items;")
  batch_size = 5000
  curr_counter = 0

  while True:
    print("BATCH:", curr_counter)
    items = cur.fetchmany(batch_size)
    if not items: break
    curr_counter += 1
    pipe = r.pipeline()

    for item in items:
      item_key, created_at, user_id, type = item
      datetime_obj =  datetime.datetime.strptime(str(created_at), '%Y-%m-%d %H:%M:%S')
      unix_timestamp = int(datetime_obj.timestamp())
      item_key_redis = f"item:{item_key}"
      pipe.hset(item_key_redis, mapping={"id": item_key, "user": user_id, "type": type, "unix": unix_timestamp})

    pipe.execute()
  cur.close()