"""
Quick diagnostic: shows ALL accounts and their details from OpenD.
Run: python diagnose_accounts.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from moomoo import (
    OpenSecTradeContext,
    RET_OK,
    TrdEnv,
    TrdMarket,
    SecurityFirm,
)
import config

print("=" * 60)
print("MooMoo Account Diagnostic")
print("=" * 60)

# Show all available SecurityFirm values
print("\nAvailable SecurityFirm values:")
for attr in dir(SecurityFirm):
    if not attr.startswith("_"):
        try:
            val = getattr(SecurityFirm, attr)
            if not callable(val):
                print(f"  SecurityFirm.{attr} = {val}")
        except:
            pass

# Try all known SecurityFirm values
firms_to_try = []
for attr in ["FUTUINC", "FUTUSECURITIES", "FUTUSG", "FUTUAU", "MOOMOO", "MOOMOO_US"]:
    if hasattr(SecurityFirm, attr):
        firms_to_try.append((attr, getattr(SecurityFirm, attr)))

if not firms_to_try:
    # Fallback: try the ones we know exist
    firms_to_try = [
        ("FUTUINC", SecurityFirm.FUTUINC),
        ("FUTUSECURITIES", SecurityFirm.FUTUSECURITIES),
    ]

for firm_name, firm_enum in firms_to_try:
    print(f"\n--- Trying SecurityFirm.{firm_name} ---")
    try:
        ctx = OpenSecTradeContext(
            host=config.OPEND_HOST,
            port=config.OPEND_PORT,
            security_firm=firm_enum,
        )
        ret, data = ctx.get_acc_list()
        if ret == RET_OK:
            print(f"  Found {len(data)} account(s):")
            print(data.to_string(index=False))
        else:
            print(f"  get_acc_list failed: {data}")
        ctx.close()
    except Exception as e:
        print(f"  Error: {e}")

# Also try without SecurityFirm
print(f"\n--- Trying without SecurityFirm ---")
try:
    ctx = OpenSecTradeContext(
        host=config.OPEND_HOST,
        port=config.OPEND_PORT,
    )
    ret, data = ctx.get_acc_list()
    if ret == RET_OK:
        print(f"  Found {len(data)} account(s):")
        print(data.to_string(index=False))
        print(f"\n  Columns: {list(data.columns)}")
    else:
        print(f"  get_acc_list failed: {data}")
    ctx.close()
except Exception as e:
    print(f"  Error: {e}")

print("\n" + "=" * 60)
print("NEXT STEPS:")
print("1. Complete US OpenAPI disclaimer agreement:")
print("   https://risk-disclosure.us.moomoo.com/index?agreementNo=USOT0027")
print("2. Restart OpenD after completing the agreement")
print("3. Run this diagnostic again")
print("=" * 60)
