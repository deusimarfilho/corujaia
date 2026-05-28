import requests

API_KEY = "YEYBJBE-HZ24RMS-GGCSCM2-Z4JR33C"
url = "http://localhost:3001/api/v1/workspace/sbdi_coin/chat"
headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
payload = {
    "message": (
        "O nome CÍCERO PEREIRA LIMA DE SOUSA aparece em algum documento indexado? "
        "Liste TODOS os arquivos onde ele é citado e cite o trecho."
    ),
    "mode": "query",
}
r = requests.post(url, headers=headers, json=payload, timeout=90)
print("status:", r.status_code)
if r.ok:
    d = r.json()
    print("response:", (d.get("textResponse") or "")[:2000])
    print("sources:", len(d.get("sources") or []))
    for s in (d.get("sources") or [])[:5]:
        print(" -", s.get("title") or s.get("docSource"))
else:
    print(r.text[:500])
