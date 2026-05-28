import requests, re

token = re.search(r'TOKEN=(.+)', open('auth_token.txt').read()).group(1).strip()
headers = {'Authorization': 'Bearer ' + token}

for img in ['test_real1.jpg', 'test_real2.jpg', 'test_real3.jpg']:
    with open(img, 'rb') as f:
        r = requests.post(
            'http://localhost:8000/api/v1/deepfake/detect',
            headers=headers,
            files={'file': (img, f, 'image/jpeg')}
        )
    print('\n=== ' + img + ' ===')
    print('Status HTTP : ' + str(r.status_code))
    if not r.text:
        print('Réponse vide — serveur arrêté ou crash')
        continue
    try:
        d = r.json()
    except Exception:
        print('Réponse brute : ' + r.text[:300])
        continue
    print('Manipule  : ' + str(d.get('is_manipulated')))
    print('Confiance : ' + str(round(d.get('confidence', 0) * 100, 1)) + '%')
    print('Verdict   : ' + str(d.get('verdict')))
    if d.get('error'):
        print('Erreur    : ' + str(d.get('error')))
