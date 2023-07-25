import redis
import os

redis_password = os.environ.get('REDIS_PASSWORD')

r = redis.Redis(host="localhost", port=6379, db=1, password=redis_password, decode_responses=True)
random_key = r.randomkey()
random_item = r.hgetall(random_key)
print("random_item['id']", random_item['id'])
