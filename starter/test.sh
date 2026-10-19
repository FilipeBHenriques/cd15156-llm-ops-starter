uv run python -c "
import chromadb
client = chromadb.PersistentClient(path='data/chroma')
try:
    client.delete_collection('cache')
    print('cache collection cleared')
except Exception as e:
    print(f'no cache collection to clear ({e})')
"
make seed-traces
make show-traces

curl -s http://localhost:8080/cost-dashboard | w3m -dump -T text/html