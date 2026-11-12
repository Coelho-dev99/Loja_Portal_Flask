import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

try:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    print("Conexao OK!")
    conn.close()
except UnicodeDecodeError as e:
    # O PostgreSQL respondeu em portugues (cp1252) e o psycopg2 nao
    # conseguiu ler os acentos. Aqui mostramos a mensagem real.
    print("O PostgreSQL recusou a conexao. Mensagem real:")
    print(e.object.decode("cp1252", errors="replace"))
except Exception as e:
    print("Erro:", e)
