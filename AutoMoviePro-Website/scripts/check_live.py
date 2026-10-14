import urllib.request
import ssl
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    'https://193.203.184.176/',
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'}
)

with urllib.request.urlopen(req, context=ctx) as r:
    html = r.read().decode('utf-8', errors='ignore')

print("--- LIVE HTML VERIFICATION ---")
print("ampChatLauncher in HTML:", 'id="ampChatLauncher"' in html)
print("ampChoiceCard in HTML:", 'id="ampChoiceCard"' in html)
print("ampStartLiveAgentBtn in HTML:", 'id="ampStartLiveAgentBtn"' in html)
print("ampDirectWaBtn in HTML:", 'id="ampDirectWaBtn"' in html)
print("ampConnectingOverlay in HTML:", 'id="ampConnectingOverlay"' in html)
print("ampChatPanel in HTML:", 'id="ampChatPanel"' in html)
print("ampChatBack in HTML:", 'id="ampChatBack"' in html)

js_req = urllib.request.Request(
    'https://193.203.184.176/assets/js/marketing-chat.js',
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'}
)
with urllib.request.urlopen(js_req, context=ctx) as r:
    js_text = r.read().decode('utf-8', errors='ignore')

print("\n--- LIVE JS VERIFICATION ---")
print("startConnectingSequence in live JS:", 'startConnectingSequence' in js_text)
print("openChoiceCard in live JS:", 'openChoiceCard' in js_text)
print("openLiveChat in live JS:", 'openLiveChat' in js_text)

css_req = urllib.request.Request(
    'https://193.203.184.176/assets/css/site.css',
    headers={'Host': 'automoviepro.com', 'User-Agent': 'Mozilla/5.0'}
)
with urllib.request.urlopen(css_req, context=ctx) as r:
    css_text = r.read().decode('utf-8', errors='ignore')

print("\n--- LIVE CSS VERIFICATION ---")
print("amp-chat-launcher in CSS:", '.amp-chat-launcher' in css_text)
print("amp-choice-card in CSS:", '.amp-choice-card' in css_text)
print("amp-connecting-overlay in CSS:", '.amp-connecting-overlay' in css_text)
