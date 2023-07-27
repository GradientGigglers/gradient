import os
import psycopg2

postgres_db = os.environ.get('POSTGRES_DB')
postgres_password = os.environ.get('POSTGRES_PASSWORD')

connection = psycopg2.connect(host="localhost", user="root", port=5432, database=postgres_db, password=postgres_password)