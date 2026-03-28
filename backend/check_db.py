import httpx

r = httpx.get('http://localhost:19000/v1/models', headers={'Authorization': 'Bearer modelmesh_local_dev_key'})
data = r.json()
print(f"Models: {len(data['data'])}")

r2 = httpx.get('http://localhost:19000/v1/providers', headers={'Authorization': 'Bearer modelmesh_local_dev_key'})
print(f"Providers: {len(r2.json()['data'])}")

r3 = httpx.get('http://localhost:19000/v1/personas', headers={'Authorization': 'Bearer modelmesh_local_dev_key'})
print(f"Personas: {len(r3.json()['data'])}")