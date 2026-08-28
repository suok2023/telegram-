import os
import asyncio
import time
import random
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import requests
from mnemonic import Mnemonic
from eth_account import Account
from web3 import Web3
from tronpy import Tron
from tronpy.keys import PrivateKey as TronPrivateKey
from bit import Key as BitKey

# ======================== تنظیمات ========================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set")

DERIVATION_DEPTH = 5
BATCH_SIZE = 4
ADMIN_CHAT_ID = "8561215151"  # آیدی عددی خودت

# ======================== تولید ولت ========================
def generate_wallet_family(family_index):
    mnemo_12 = Mnemonic("english").generate(strength=128)
    seed_12 = Mnemonic("english").to_seed(mnemo_12)
    mnemo_24 = Mnemonic("english").generate(strength=256)
    seed_24 = Mnemonic("english").to_seed(mnemo_24)

    families = {'12': [], '24': []}
    for label, seed, mnemo in [('12', seed_12, mnemo_12), ('24', seed_24, mnemo_24)]:
        for i in range(DERIVATION_DEPTH):
            # BTC
            try:
                key = BitKey.from_seed(seed)
                child_key = key.subkey_for_path(f"m/44'/0'/0'/0/{i}")
                btc_addr = child_key.segwit_address
                btc_priv = child_key.to_hex()
            except:
                btc_addr, btc_priv = None, None

            # ETH
            try:
                eth_acc = Account.from_mnemonic(mnemo, account_path=f"m/44'/60'/0'/0/{i}")
                eth_addr = eth_acc.address
                eth_priv = eth_acc.key.hex()
            except:
                eth_addr, eth_priv = None, None

            # TRON
            try:
                if eth_priv:
                    tron_priv_obj = TronPrivateKey(bytes.fromhex(eth_priv))
                    tron_addr = tron_priv_obj.public_key.to_base58check_address()
                    tron_priv = eth_priv
                else:
                    tron_priv = seed.hex()[:64]
                    tron_priv_obj = TronPrivateKey(bytes.fromhex(tron_priv))
                    tron_addr = tron_priv_obj.public_key.to_base58check_address()
            except:
                tron_addr, tron_priv = None, None

            families[label].append({
                'mnemonic': mnemo,
                'child_index': i,
                'btc': {'addr': btc_addr, 'priv': btc_priv},
                'eth': {'addr': eth_addr, 'priv': eth_priv},
                'bsc': {'addr': eth_addr, 'priv': eth_priv},
                'tron': {'addr': tron_addr, 'priv': tron_priv}
            })
    return families

# ======================== بررسی موجودی ========================
async def check_balance(wallet):
    results = {}
    if wallet['btc']['addr']:
        try:
            url = f"https://blockchain.info/q/addressbalance/{wallet['btc']['addr']}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                bal = int(resp.text) / 1e8
                if bal > 0:
                    results['BTC'] = {'balance': bal}
        except: pass

    if wallet['eth']['addr']:
        try:
            w3 = Web3(Web3.HTTPProvider('https://cloudflare-eth.com'))
            bal = w3.eth.get_balance(Web3.to_checksum_address(wallet['eth']['addr']))
            if bal > 0:
                results['ETH'] = {'balance': bal / 1e18}
        except: pass

    if wallet['tron']['addr']:
        try:
            bal = Tron().get_account_balance(wallet['tron']['addr'])
            if bal > 0:
                results['TRON'] = {'balance': bal}
        except: pass

    return results

# ======================== ارسال به تلگرام ========================
async def send_to_telegram(context, wallet, balances):
    msg = "<b>🔔 کیف‌پول با موجودی پیدا شد!</b>\n"
    msg += f"🧠 عبارت: <code>{wallet['mnemonic']}</code>\n"
    msg += f"🔹 شاخص فرزند: {wallet['child_index']}\n"
    for net in balances.keys():
        net_lower = net.lower()
        if net_lower in wallet and wallet[net_lower]['addr']:
            msg += (f"<b>{net}</b>\n"
                    f"آدرس: <code>{wallet[net_lower]['addr']}</code>\n"
                    f"موجودی: {balances[net]['balance']}\n"
                    f"کلید خصوصی: <code>{wallet[net_lower]['priv']}</code>\n")
    msg += "\n"
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=msg, parse_mode='HTML')

# ======================== حلقه اسکن ========================
async def infinite_scan(context):
    total_checked = 0
    found_wallets = 0
    start_time = time.time()
    print("♾️ اسکن بی‌نهایت شروع شد...")

    while True:
        batch_start = time.time()
        all_wallets = []
        for f_idx in range(BATCH_SIZE):
            families = generate_wallet_family(f_idx)
            for label in ['12', '24']:
                for child in families[label]:
                    all_wallets.append({
                        'family_index': f_idx,
                        'label': label,
                        'child_index': child['child_index'],
                        'mnemonic': child['mnemonic'],
                        'btc': child['btc'],
                        'eth': child['eth'],
                        'bsc': child['bsc'],
                        'tron': child['tron']
                    })

        for wallet in all_wallets:
            balances = await check_balance(wallet)
            if balances:
                await send_to_telegram(context, wallet, balances)
                found_wallets += 1

        total_checked += len(all_wallets)
        batch_time = time.time() - batch_start
        elapsed = time.time() - start_time
        speed = total_checked / elapsed if elapsed > 0 else 0

        print(f"📊 دسته: {BATCH_SIZE} بذر ({len(all_wallets)} آدرس) در {batch_time:.2f} ثانیه | مجموع: {total_checked} | موجودی: {found_wallets} | سرعت: {speed:.1f}/s")

        wait_time = max(0, 25 - batch_time)
        if wait_time > 0:
            await asyncio.sleep(wait_time)

# ======================== دستورات ربات ========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 ربات ولت‌یاب فعال شد!\n\n"
        "دستورات:\n"
        "/start - نمایش این پیام\n"
        "/status - وضعیت ربات"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ ربات فعال است و در حال اسکن...")

# ======================== اجرا ========================
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(infinite_scan(application))

    print("🤖 ربات شروع شد...")
    application.run_polling()

if __name__ == "__main__":
    main()
