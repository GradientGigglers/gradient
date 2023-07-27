#%%
import psycopg2
import socket
import time
#%%
p = psycopg2.connect(host="localhost", user="root", port=5433, database="gradient_gigglers_postgres_db", password="g345T£4tg324G3G325G345G4TEGQedfwerqk3t6uykw234234gfqwegq")
# %%
def check_connection_status(host, port):
  s = socket.socket()
  try:
    print(f"Checking {host} connection status")
    s.connect((host, port))
  except Exception as e:
    s.close()
    print(f"No, {host} connection is not yet open. Retry in 5sec.")
    time.sleep(5)
    return check_connection_status(host, port)
  print(f"Ok, {host} connection is open!")
  s.close()
# %%
check_connection_status("localhost", 5433)
# %%
