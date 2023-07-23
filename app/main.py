import confluent_kafka
import fastapi
import redis
import uuid
import json
import time
import os
import random


redis_password = os.environ.get('REDIS_PASSWORD')


app = fastapi.FastAPI()


@app.on_event("startup")
async def startup_event():
  app.state.r = redis.Redis(host="redis", port=6379, db=0, password=redis_password, encoding='utf-8')
  app.state.k = confluent_kafka.Producer({"bootstrap.servers": "kafka:29092"})


@app.on_event("shutdown")
def shutdown_event():
  app.state.k.flush()


@app.get("/")
def read_root(request: fastapi.Request):
  app.state.r.incr("test_counter")
  user_id = request.headers.get("User")
  session = request.headers.get("Session")
  # get length of item_data table for random number generation
  item_data_length = app.state.r.hlen('item_data')
  # pull item_id from the table format is bytes
  item_id_b = app.state.r.hget('item_data', random.randint(0,item_data_length-1))
  # convert item_id into utf-8 to send to user
  item_id = item_id_b.decode('utf-8')
  ts = int(time.time())

  print(f"User {user_id} in session {session} requested an item at {ts}")

  # add to the user reco history of seen items
  # but also to session history to leverage in
  # session recommendations
  reco_info = {"item_id": item_id, "ts": ts}
  app.state.r.xadd(f"x:{user_id}", reco_info, maxlen=90, approximate=True)
  app.state.r.xadd(f"x:{user_id}:{session}", reco_info, maxlen=30, approximate=True)

  # package current interaction and just produce
  # it i.e. to send to kafka servers just yet,
  # get some more and and send it all together
  # every 5 interactions
  log_msg = json.dumps({"type": "reco", "user_id": user_id, "session": session, "item_id": item_id, "ts": ts})
  app.state.k.produce("logs", log_msg)
  if (len(app.state.k) > 5): app.state.k.flush()

  # finally return the item_id to the user
  return item_id


@app.post("/evt")
def get_evt(request: fastapi.Request):
  user_id = request.headers.get("User")
  session = request.headers.get("Session")
  event = request.headers.get("Event")
  ts = int(time.time())
  
  print(f"Incoming /evt - User: {user_id}, Session: {session}, Event: {event}, Time: {ts}")

  # add to session history to leverage in
  # session recommendations
  app.state.r.xadd(f"x:{user_id}:{session}", {"ts": ts})

  # package end session event and send it
  # to kafka servers directly, no batching
  log_msg = json.dumps({"type": "evt", "user_id": user_id, "session": session, "ts": ts})
  app.state.k.produce("logs", log_msg)
  app.state.k.flush()

  # just a string is good enough, 200
  return "ok"



@app.post("/item")
async def create_item(data: str = fastapi.Body(None)):
  app.state.r.set("test", data)
  return {"status": "success"}