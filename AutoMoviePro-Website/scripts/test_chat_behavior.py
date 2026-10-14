import urllib.request
import json
import ssl
import sys

sys.stdout.reconfigure(encoding='utf-8')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://193.203.184.176/api/marketing-chat.php'
sess_id = 'test_sess_' + str(int(json.loads('12345678')))

def call_chat(msg, history=None):
    payload = {
        'message': msg,
        'action': 'chat' if msg else 'greet',
        'lang': 'bn',
        'agent_id': 'ayesha',
        'agent_name': 'আয়েশা (Ayesha)',
        'agent_role': 'সিনিয়র কাস্টমার কনসালট্যান্ট',
        'session_id': sess_id,
        'history': history or []
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers={'Host': 'automoviepro.com', 'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    )
    with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))

print("=== 1. TEST GREETING (Initial Turn) ===")
res1 = call_chat("")
print("Agent:", res1.get('agent_name'))
print("Greeting:", res1.get('reply'))
history = [
    {'role': 'assistant', 'content': res1.get('reply', '')}
]

print("\n=== 2. TEST FOLLOW-UP TURN (Checking No Repeated Salam) ===")
user_msg2 = "koyta engine ase apnader ar dam koto?"
res2 = call_chat(user_msg2, history)
reply2 = res2.get('reply', '')
print("User:", user_msg2)
print("Reply 2:", reply2)
has_repeated_salam = 'আসসালামু আলাইকুম' in reply2
print("Repeated Salam detected:", has_repeated_salam, "(Should be False!)")
print("Mentions 3 official engines:", ('৩,৯৯৯' in reply2 or '৩৯৯৯' in reply2) and ('২,৯৯৯' in reply2 or '২৯৯৯' in reply2) and ('১,৯৯৯' in reply2 or '১৯৯৯' in reply2))

history.append({'role': 'user', 'content': user_msg2})
history.append({'role': 'assistant', 'content': reply2})

print("\n=== 3. TEST OFF-TOPIC DEFLECTION ===")
user_msg3 = "apnar bari kothay? apnar boyos koto?"
res3 = call_chat(user_msg3, history)
reply3 = res3.get('reply', '')
print("User:", user_msg3)
print("Reply 3:", reply3)
print("Deflects personal questions politely:", any(k in reply3 for k in ['ব্যক্তিগত', 'সফটওয়্যার', 'প্যাকেজ', 'অটোমেশন', 'AutoMovie Pro', 'সাহায্য']))
