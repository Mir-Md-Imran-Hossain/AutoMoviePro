"""
AutoMovie Pro - PaymentApp SMS Parser Engine
Extracts Transaction ID, Amount, Sender, and Timestamp from bKash, Nagad, and Rocket SMS.
Designed to run on the cashier/agent phones (Zahid Pharmacy / Simi Drug House).
"""

import re
import time
from typing import Dict, Any, Optional


class PaymentSMSParser:
    """
    Robust regex engine for Bangladeshi Mobile Financial Services SMS.
    """

    @staticmethod
    def parse_sms(sender: str, message: str) -> Optional[Dict[str, Any]]:
        sender_upper = sender.upper()
        msg = message.strip()

        # 1. bKash Cash In / Cash Out Detection
        # Sample: "Cash In Tk 2,999.00 from 01711223344 successful. Fee Tk 0.00. Balance Tk ... TrxID BL82KA9191 at 21/09/2026 14:30"
        # Or: "You have received Tk 2,999.00 from 01711223344. Ref ... TrxID 9A82J811..."
        if "BKASH" in sender_upper or "bKash" in message or "TrxID" in message:
            trx_match = re.search(r'TrxID\s+([A-Z0-9]+)', msg, re.IGNORECASE)
            amt_match = re.search(r'Tk\s+([\d,]+\.?\d*)', msg, re.IGNORECASE)
            from_match = re.search(r'from\s+(01\d{9})', msg, re.IGNORECASE)

            if trx_match and amt_match:
                amount_str = amt_match.group(1).replace(',', '')
                return {
                    "provider": "bkash",
                    "txn_id": trx_match.group(1).upper(),
                    "amount": float(amount_str),
                    "sender_phone": from_match.group(1) if from_match else None,
                    "sender_last_digits": from_match.group(1)[-4:] if from_match else None,
                    "raw_message": msg,
                    "timestamp": time.time()
                }

        # 2. Nagad Cash In / Cash Out Detection
        # Sample: "Cash In Received. Amount: Tk 2,999.00. Sender: 01611223344. TxnID: 72JH891A..."
        if "NAGAD" in sender_upper or "Nagad" in message or "TxnID" in message:
            trx_match = re.search(r'TxnID:\s*([A-Z0-9]+)', msg, re.IGNORECASE)
            amt_match = re.search(r'Amount:\s*Tk\s*([\d,]+\.?\d*)', msg, re.IGNORECASE)
            from_match = re.search(r'Sender:\s*(01\d{9})', msg, re.IGNORECASE)

            if trx_match and amt_match:
                amount_str = amt_match.group(1).replace(',', '')
                return {
                    "provider": "nagad",
                    "txn_id": trx_match.group(1).upper(),
                    "amount": float(amount_str),
                    "sender_phone": from_match.group(1) if from_match else None,
                    "sender_last_digits": from_match.group(1)[-4:] if from_match else None,
                    "raw_message": msg,
                    "timestamp": time.time()
                }

        # 3. Rocket Detection
        if "ROCKET" in sender_upper or "16216" in sender:
            trx_match = re.search(r'TxnId:\s*([A-Z0-9]+)', msg, re.IGNORECASE)
            amt_match = re.search(r'Tk\s*([\d,]+\.?\d*)', msg, re.IGNORECASE)
            from_match = re.search(r'From\s*(01\d{9})', msg, re.IGNORECASE)

            if trx_match and amt_match:
                amount_str = amt_match.group(1).replace(',', '')
                return {
                    "provider": "rocket",
                    "txn_id": trx_match.group(1).upper(),
                    "amount": float(amount_str),
                    "sender_phone": from_match.group(1) if from_match else None,
                    "sender_last_digits": from_match.group(1)[-4:] if from_match else None,
                    "raw_message": msg,
                    "timestamp": time.time()
                }

        return None

    @staticmethod
    def push_to_gateway(gateway_url: str, parsed_data: Dict[str, Any], timeout_sec: int = 10) -> Dict[str, Any]:
        """
        Dispatches parsed SMS directly to central AutoMovie Pro website gateway.
        """
        import urllib.request
        import json

        req_data = json.dumps(parsed_data).encode("utf-8")
        req = urllib.request.Request(
            gateway_url,
            data=req_data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout_sec) as response:
                res_body = response.read().decode("utf-8")
                return json.loads(res_body)
        except Exception as e:
            return {"ok": False, "error": str(e)}
