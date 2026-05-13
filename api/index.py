import os
import json
import time
import math
import hmac
import hashlib
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import httpx
import jwt
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# App & CORS
# -----------------------------------------------------------------------------
app = FastAPI(title="ADU Copilot API", version="1.1.0-mvp")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOW_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
CREDIT_AUDIT = 30
CREDIT_ADVISE = 50
SIGNUP_CREDITS = int(os.getenv("SIGNUP_CREDITS", "100"))
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET") or ""
LS_WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET") or ""
# Los Angeles Department of Building and Safety — ADU approved standard plans (reference for users)
OFFICIAL_ADU_REFERENCE_URL = "https://dbs.lacity.gov/adu/approved-standard-plans"
OFFICIAL_ADU_WEBSITE="https://www.hcd.ca.gov/building-standards/adu/handbook"
client = genai.Client()

_memory_credits: Dict[str, int] = {}


def get_current_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """
    Resolve Supabase user id from Bearer JWT (sub). Requires SUPABASE_JWT_SECRET.
    Dev escape hatch: Authorization: Bearer dev:<any_user_id> when JWT secret is unset.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header (expected Bearer token).",
        )
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Empty bearer token.")

    if not SUPABASE_JWT_SECRET:
        if token.startswith("dev:"):
            uid = token[4:].strip()
            if not uid:
                raise HTTPException(
                    status_code=401,
                    detail="Dev token must be dev:<user_id> when SUPABASE_JWT_SECRET is not set.",
                )
            return uid
        raise HTTPException(
            status_code=503,
            detail="Server is not configured for auth (set SUPABASE_JWT_SECRET), or use dev:<user_id> token for local testing.",
        )

    try:
        payload = jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=401, detail="Token expired.") from e
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail="Invalid token.") from e

    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="Token missing sub claim.")
    return str(sub)


def _sb_headers() -> Dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def _sb_get_credits(user_id: str) -> Optional[int]:
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        return None
    url = f"{SUPABASE_URL}/rest/v1/user_credits"
    params = {"user_id": f"eq.{user_id}", "select": "credits"}
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.get(url, headers=_sb_headers(), params=params)
        if r.status_code != 200:
            raise HTTPException(
                status_code=502, detail="Failed to read credits from Supabase."
            )
        rows = r.json()
        if not rows:
            return None
        return int(rows[0]["credits"])


async def _sb_insert_credits(user_id: str, credits: int) -> int:
    url = f"{SUPABASE_URL}/rest/v1/user_credits"
    payload = {"user_id": user_id, "credits": credits}
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.post(url, headers=_sb_headers(), json=payload)
        if r.status_code not in (200, 201):
            raise HTTPException(
                status_code=502, detail="Failed to create credits row in Supabase."
            )
        rows = r.json()
        return int(rows[0]["credits"]) if rows else credits


async def _sb_patch_credits(user_id: str, new_balance: int) -> None:
    url = f"{SUPABASE_URL}/rest/v1/user_credits"
    params = {"user_id": f"eq.{user_id}"}
    async with httpx.AsyncClient(timeout=15.0) as http:
        r = await http.patch(
            url, headers=_sb_headers(), params=params, json={"credits": new_balance}
        )
        if r.status_code not in (200, 204):
            raise HTTPException(
                status_code=502, detail="Failed to update credits in Supabase."
            )


async def get_or_init_credits(user_id: str) -> int:
    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user id.")

    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        if user_id not in _memory_credits:
            _memory_credits[user_id] = SIGNUP_CREDITS
        return _memory_credits[user_id]

    existing = await _sb_get_credits(user_id)
    if existing is None:
        return await _sb_insert_credits(user_id, SIGNUP_CREDITS)
    return existing


async def deduct_credits(user_id: str, amount: int) -> int:
    balance = await get_or_init_credits(user_id)
    if balance < amount:
        raise HTTPException(
            status_code=402,
            detail=f"Insufficient credits (need {amount}, balance {balance}). Please purchase more credits.",
        )
    new_balance = balance - amount

    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        _memory_credits[user_id] = new_balance
        return new_balance

    await _sb_patch_credits(user_id, new_balance)
    return new_balance


# -----------------------------------------------------------------------------
# Pydantic
# -----------------------------------------------------------------------------
class ADUParameters(BaseModel):
    """
    Audit parameters aligned with extract JSON and California / LADBS-oriented checks.
    """

    adu_type: str = Field(
        ...,
        description="Detached | Attached | JADU (aliases accepted)",
    )
    proposed_adu_sqft: float
    primary_dwelling_sqft: Optional[float] = None
    rear_setback_ft: float = 0.0
    side_setback_ft: float = 0.0
    front_setback_ft: Optional[float] = None
    proposed_height_ft: float = 0.0
    is_near_transit: bool = False
    lot_size_sqft: Optional[float] = None
    is_jadu_within_primary_dwelling: Optional[bool] = None
    # Handbook-style supplemental fields
    stories: int = Field(1, ge=0, description="Proposed ADU stories (above-grade).")
    separation_from_primary_ft: Optional[float] = Field(
        None,
        description="Clear distance from new ADU to existing primary dwelling (detached ADU fire/access clearance).",
    )
    jadu_has_separate_entrance: Optional[bool] = Field(
        None,
        description="JADU: exterior access separate from primary unit (typical HCD/JADU requirement).",
    )
    owner_occupies_primary: Optional[bool] = Field(
        None,
        description="JADU: owner-occupancy attestation for primary dwelling (common local/JADU condition).",
    )
    min_ceiling_height_ft: Optional[float] = Field(
        None,
        description="Minimum finished ceiling height in ADU habitable space (CBC/HCD habitability).",
    )
    adu_bedroom_count: int = Field(
        0,
        ge=0,
        description="ADU bedrooms (0=studio/unknown). Attached max-size floor uses 850 sf unless >1 bedroom (1,000 sf).",
    )
    primary_structure_height_ft: Optional[float] = Field(
        None,
        description="Zoning/building height limit that applies to the primary dwelling (ft); caps attached ADU height per § 66321(b)(4)(D).",
    )
    adu_permitting_track: str = Field(
        "66314",
        description='Use "66314" for default state standards, or "66323_detached" for new detached ADU under Gov. Code § 66323(a)(2) (800 sf max per HCD table).',
    )
    jadu_shares_sanitation_with_primary: Optional[bool] = Field(
        None,
        description="JADU: whether sanitation is shared with the primary unit (owner-occupancy rules; AB 1154 / Gov. Code § 66333(b)).",
    )
    jadu_has_separate_bathroom: Optional[bool] = Field(
        None,
        description="JADU: separate bathroom from primary (if false, interior entrance to main living area may be required).",
    )
    jadu_interior_entrance_to_main: Optional[bool] = Field(
        None,
        description="JADU: interior entrance to the primary dwelling main living area (Gov. Code § 66333, subd. (e)(2)).",
    )


class AuditRequest(BaseModel):
    parameters: ADUParameters


class AdviseRequest(BaseModel):
    parameters: ADUParameters
    failed_items: List[Dict[str, Any]]


# -----------------------------------------------------------------------------
# ADU type normalization
# -----------------------------------------------------------------------------
def _norm_adu_type(raw: str) -> str:
    s = (raw or "").strip().lower()
    if s in ("detached", "独立", "独立式", "standalone"):
        return "Detached"
    if s in ("attached", "附建", "附建式", "addition"):
        return "Attached"
    if s in ("jadu", "初级", "初级adu"):
        return "JADU"
    return raw.strip()[:1].upper() + raw.strip()[1:] if raw else "Detached"


def _max_attached_sqft(primary: Optional[float], bedroom_count: int) -> Tuple[float, str]:
    """
    HCD ADU Handbook (Mar 2026), Size Requirements: attached shall not exceed 50% of
    primary floor area (Gov. Code § 66314, subd. (d)(4)); local max-size rules must still
    allow at least 850 sf, or 1,000 sf if more than one bedroom (Gov. Code § 66321, subd. (b)(2)).
    Pre-check uses cap = min(1,200, max(floor, 50% primary)) per handbook summary (p. 38–39).
    """
    if primary is None or primary <= 0:
        return (float("nan"), "Primary dwelling floor area is required to check the 50% cap.")
    half = 0.5 * primary
    floor = 1000.0 if bedroom_count > 1 else 850.0
    cap = min(1200.0, max(floor, half))
    return (
        cap,
        f"min(1,200 sf, max({floor:.0f} sf, 50% primary)) = {cap:.0f} sf",
    )


def _height_limit_detached(is_near_transit: bool) -> Tuple[float, str]:
    """Gov. Code § 66321(b)(4)(A)–(B); HCD Handbook p. 24."""
    base = 18.0 if is_near_transit else 16.0
    note = (
        "Up to 18 ft on a lot within one-half mile of a major transit stop or HQTC (§ 66321(b)(4)(B)), "
        "including allowance described for roof pitch aligned with primary dwelling."
        if is_near_transit
        else "At least 16 ft maximum height must be allowed for detached ADUs (§ 66321(b)(4)(A))."
    )
    return (base, note)


def _height_limit_attached(primary_zoning_height_ft: Optional[float]) -> Tuple[float, str]:
    """Gov. Code § 66321(b)(4)(D): up to 25 ft or primary dwelling height limit, whichever is lower."""
    ph = primary_zoning_height_ft
    cap = min(25.0, ph) if ph is not None and ph > 0 else 25.0
    note = (
        f"min(25 ft, primary zoning height {ph:.1f} ft) = {cap:.1f} ft"
        if ph is not None and ph > 0
        else "25 ft (no primary height provided — using state maximum for attached ADUs)"
    )
    return (cap, note)


def _is_66323_detached_track(params: ADUParameters, adu_type_norm: str) -> bool:
    return (
        adu_type_norm == "Detached"
        and (params.adu_permitting_track or "").strip().lower() == "66323_detached"
    )


def run_la_audit(params: ADUParameters) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Deterministic California pre-check aligned to HCD ADU Handbook (March 2026) and cited
    Government Code sections. Numeric thresholds follow the Handbook FAQ (sizes, setbacks,
    heights, JADU rules, impact-fee thresholds). All user-visible strings are English.
    """
    t = _norm_adu_type(params.adu_type)
    results: List[Dict[str, Any]] = []
    radar: List[Dict[str, Any]] = []

    def add_radar(axis: str, compliant: bool, weight: float = 1.0) -> None:
        radar.append(
            {
                "axis": axis,
                "value": 100.0 if compliant else 0.0,
                "max": 100.0,
                "weight": weight,
            }
        )

    # --- Floor area by ADU type (HCD ADU Handbook Mar 2026; Gov. Code §§ 66314, 66321, 66323) ---
    if t == "Detached":
        if _is_66323_detached_track(params, t):
            max_sq = 800.0
            cite = "Gov. Code § 66323, subd. (a)(2)(B) (HCD Handbook p. 16–17: new detached 66323 ADU, max 800 sf)"
        else:
            max_sq = 1200.0
            cite = "Gov. Code § 66314, subd. (d)(4) (up to 1,200 sf interior livable without compliant local cap; HCD Handbook p. 38)"
        ok = params.proposed_adu_sqft <= max_sq
        results.append(
            {
                "rule": "Detached ADU maximum interior livable space",
                "is_compliant": ok,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": f"≤ {max_sq:.0f} sq ft",
                "citation": cite,
            }
        )
        add_radar("Detached area", ok)
    elif t == "Attached":
        cap, cap_note = _max_attached_sqft(
            params.primary_dwelling_sqft, params.adu_bedroom_count
        )
        if math.isnan(cap):
            ok = False
            results.append(
                {
                    "rule": "Attached ADU floor area (primary size required)",
                    "is_compliant": False,
                    "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                    "required": cap_note,
                    "citation": "Gov. Code § 66314, subd. (d)(4); § 66321, subd. (b)(2)–(b)(3) (HCD Handbook p. 38–39)",
                }
            )
        else:
            ok = params.proposed_adu_sqft <= cap
            results.append(
                {
                    "rule": "Attached ADU maximum interior livable space",
                    "is_compliant": ok,
                    "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                    "required": f"≤ {cap:.0f} sq ft ({cap_note})",
                    "citation": "Gov. Code § 66314, subd. (d)(4); § 66321, subd. (b)(2) (HCD Handbook p. 38–39)",
                }
            )
        add_radar("Attached area", ok)
    elif t == "JADU":
        max_sq = 500.0
        ok_area = params.proposed_adu_sqft <= max_sq
        results.append(
            {
                "rule": "JADU maximum interior livable space",
                "is_compliant": ok_area,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": f"≤ {max_sq:.0f} sq ft",
                "citation": "Gov. Code § 66313, subd. (d); § 66333 (HCD Handbook p. 28)",
            }
        )
        in_dwelling = params.is_jadu_within_primary_dwelling
        if in_dwelling is None:
            results.append(
                {
                    "rule": "JADU must be contained within a single-family residence",
                    "is_compliant": False,
                    "actual": "Unknown",
                    "required": "Yes — entirely within existing or proposed single-family residence (not accessory structures only)",
                    "citation": "Gov. Code § 66333, subd. (d); HCD Handbook p. 28",
                }
            )
            ok_loc = False
        else:
            ok_loc = bool(in_dwelling)
            results.append(
                {
                    "rule": "JADU must be contained within a single-family residence",
                    "is_compliant": ok_loc,
                    "actual": "Yes" if ok_loc else "No",
                    "required": "Yes",
                    "citation": "Gov. Code § 66333, subd. (d); HCD Handbook p. 28",
                }
            )

        # § 66333(e)(2): if no separate bathroom, interior entrance to main living area required
        sb = params.jadu_has_separate_bathroom
        ie = params.jadu_interior_entrance_to_main
        if sb is True:
            ok_bath_ent = True
            results.append(
                {
                    "rule": "JADU bathroom / interior entrance (separate bathroom)",
                    "is_compliant": True,
                    "actual": "Separate bathroom indicated",
                    "required": "No additional interior-entrance requirement solely for sanitation (HCD Handbook p. 28).",
                    "citation": "Gov. Code § 66333, subd. (e); HCD Handbook p. 28",
                }
            )
        elif sb is False:
            ok_ent = ie is True
            results.append(
                {
                    "rule": "JADU interior entrance when no separate bathroom",
                    "is_compliant": ok_ent,
                    "actual": (
                        "Yes"
                        if ie is True
                        else ("No" if ie is False else "Unknown")
                    ),
                    "required": "Interior entrance to the primary dwelling main living area (when JADU lacks separate bathroom)",
                    "citation": "Gov. Code § 66333, subd. (e)(2); HCD Handbook p. 28",
                }
            )
            ok_bath_ent = ok_ent
        else:
            ok_bath_ent = True
            results.append(
                {
                    "rule": "JADU bathroom / interior entrance",
                    "is_compliant": True,
                    "actual": "Unknown",
                    "required": "Provide whether the JADU has a separate bathroom; if not, confirm interior entrance to main living area per § 66333(e)(2).",
                    "citation": "Gov. Code § 66333, subd. (e)(2); HCD Handbook p. 28",
                }
            )

        shares = params.jadu_shares_sanitation_with_primary
        own = params.owner_occupies_primary
        if shares is True:
            ok_own = own is True
            results.append(
                {
                    "rule": "JADU owner-occupancy (shared sanitation)",
                    "is_compliant": ok_own,
                    "actual": (
                        "Yes"
                        if own is True
                        else ("No" if own is False else "Unknown")
                    ),
                    "required": "Yes — owner must reside in the primary residence or the JADU when sanitation is shared (AB 1154, eff. Jan. 1, 2026)",
                    "citation": "Gov. Code § 66333, subd. (b); HCD Handbook p. 32, 45",
                }
            )
        elif shares is False:
            ok_own = True
            results.append(
                {
                    "rule": "JADU owner-occupancy (separate sanitation)",
                    "is_compliant": True,
                    "actual": "Sanitation not shared with primary",
                    "required": "Owner-occupancy is not required by state law when the JADU does not share sanitation (subject to narrow exceptions in § 66333(b)).",
                    "citation": "Gov. Code § 66333, subd. (b); HCD Handbook p. 32",
                }
            )
        else:
            ok_own = True
            results.append(
                {
                    "rule": "JADU owner-occupancy (sanitation not stated)",
                    "is_compliant": True,
                    "actual": "Unknown whether sanitation is shared",
                    "required": "Declare shared vs. separate sanitation — owner-occupancy is required when facilities are shared.",
                    "citation": "Gov. Code § 66333, subd. (b); HCD Handbook p. 32",
                }
            )

        results.append(
            {
                "rule": "JADU exterior access (informational)",
                "is_compliant": True,
                "actual": "See 66323 conversion rules for exterior access where applicable",
                "required": "State law does not require a separate exterior entrance for every JADU; access rules depend on configuration (HCD FAQ p. 28).",
                "citation": "Gov. Code §§ 66323, subd. (a)(1); 66333; HCD Handbook p. 16–17, 28",
            }
        )

        add_radar("JADU package", ok_area and ok_loc and ok_bath_ent and ok_own)
    else:
        results.append(
            {
                "rule": "ADU type",
                "is_compliant": False,
                "actual": params.adu_type,
                "required": "Detached | Attached | JADU",
                "citation": "—",
            }
        )
        add_radar("ADU type", False)

    # --- Minimum unit size (efficiency / CBC) — not JADU (already capped at 500 sf) ---
    if t in ("Detached", "Attached"):
        min_eff = 150.0
        ok_min = params.proposed_adu_sqft >= min_eff
        results.append(
            {
                "rule": "Minimum ADU floor area (efficiency unit lower bound)",
                "is_compliant": ok_min,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": f"≥ {min_eff:.0f} sq ft for a typical standalone efficiency unit (local ordinance may not prohibit efficiency units this small; HSC § 17958.1)",
                "citation": "HCD ADU Handbook p. 38 (efficiency units); HSC § 17958.1",
            }
        )
        add_radar("Minimum ADU size", ok_min)

    # --- Stories: state law does not cap number of stories (HCD Handbook p. 24) ---
    results.append(
        {
            "rule": "ADU stories (state law)",
            "is_compliant": True,
            "actual": f"{params.stories} story(ies)",
            "required": "No statutory maximum number of stories; local agency must allow at least two stories if height/building standards can accommodate (HCD Handbook p. 24).",
            "citation": "Gov. Code § 66321, subd. (b)(4)(D); HCD Handbook p. 24",
        }
    )
    add_radar("Stories (info)", True)

    # --- Rear / side setbacks: agencies may not require more than 4 ft (§ 66314(d)(7)) ---
    rear_ok = params.rear_setback_ft >= 4.0
    results.append(
        {
            "rule": "Rear lot line setback (state maximum required)",
            "is_compliant": rear_ok,
            "actual": f"{params.rear_setback_ft:.1f} ft",
            "required": "≥ 4 ft from rear lot line (local agency may not require more than 4 ft for attached/detached ADU; HCD Handbook p. 37)",
            "citation": "Gov. Code § 66314, subd. (d)(7); HCD Handbook p. 37",
        }
    )
    add_radar("Rear setback", rear_ok)

    side_ok = params.side_setback_ft >= 4.0
    results.append(
        {
            "rule": "Side lot line setback (state maximum required)",
            "is_compliant": side_ok,
            "actual": f"{params.side_setback_ft:.1f} ft",
            "required": "≥ 4 ft from side lot line (same standard; HCD Handbook p. 37)",
            "citation": "Gov. Code § 66314, subd. (d)(7); HCD Handbook p. 37",
        }
    )
    add_radar("Side setback", side_ok)

    fs = params.front_setback_ft
    results.append(
        {
            "rule": "Front setback / 800 sf entitlement (local)",
            "is_compliant": True,
            "actual": f"{fs:.1f} ft" if fs is not None else "Not provided",
            "required": "Front setbacks may apply locally but cannot preclude an ADU of at least 800 sf with 4-ft rear/side setbacks (Gov. Code § 66321, subd. (b)(3); HCD Handbook p. 37).",
            "citation": "Gov. Code § 66321, subd. (b)(3); HCD Handbook p. 37",
        }
    )
    add_radar("Front setback (info)", True)

    # --- Height: detached vs attached (HCD Handbook p. 24) ---
    if t == "Attached":
        h_max, h_note = _height_limit_attached(params.primary_structure_height_ft)
    elif t == "JADU":
        h_max, h_note = (
            float("inf"),
            "Height is limited by the existing single-family envelope (conversions; HCD Handbook p. 39–40).",
        )
    else:
        h_max, h_note = _height_limit_detached(params.is_near_transit)

    if t == "JADU":
        height_ok = True
        results.append(
            {
                "rule": "ADU height (JADU)",
                "is_compliant": True,
                "actual": f"{params.proposed_height_ft:.1f} ft proposed",
                "required": h_note,
                "citation": "Gov. Code § 66323, subd. (a)(1); HCD Handbook p. 39–40",
            }
        )
    else:
        height_ok = params.proposed_height_ft <= h_max
        results.append(
            {
                "rule": "Maximum ADU height (state minimum local must allow)",
                "is_compliant": height_ok,
                "actual": f"{params.proposed_height_ft:.1f} ft",
                "required": f"≤ {h_max:.0f} ft ({h_note})",
                "citation": "Gov. Code § 66321, subd. (b)(4); HCD Handbook p. 24",
            }
        )
    add_radar("Height", height_ok if t != "JADU" else True)

    # --- Structure separation: state ADU law is silent; verify under CBC / local objective standards ---
    sep = params.separation_from_primary_ft
    results.append(
        {
            "rule": "Separation between ADU and other structures on the lot",
            "is_compliant": True,
            "actual": f"{sep:.1f} ft" if sep is not None else "Not provided",
            "required": "State ADU Law does not set a minimum distance between structures; comply with Building/Fire Code and any objective local standards (HCD Handbook p. 37).",
            "citation": "HCD ADU Handbook p. 37; Gov. Code § 66314, subd. (d)(8)",
        }
    )
    add_radar("Structure separation (info)", True)

    # --- Lot size (HCD: no minimum lot size for ADUs) ---
    lot = params.lot_size_sqft
    if lot is not None and lot > 0:
        small_lot = lot < 3600
        results.append(
            {
                "rule": "Lot area (informational)",
                "is_compliant": True,
                "actual": f"{lot:.0f} sq ft"
                + (" — smaller lots may still permit ADUs; confirm utilities and access." if small_lot else ""),
                "required": "Local governments may not impose minimum lot size requirements for ADUs (Gov. Code § 66314, subd. (b)(1); HCD Handbook p. 38).",
                "citation": "Gov. Code § 66314, subd. (b)(1); HCD Handbook p. 38",
            }
        )
    else:
        results.append(
            {
                "rule": "Lot area (informational)",
                "is_compliant": True,
                "actual": "Not provided",
                "required": "Minimum lot size standards may not be applied to ADUs under state law.",
                "citation": "Gov. Code § 66314, subd. (b)(1); HCD Handbook p. 38",
            }
        )
    add_radar("Lot area (info)", True)

    ch = params.min_ceiling_height_ft
    if ch is None:
        results.append(
            {
                "rule": "Minimum habitable ceiling height",
                "is_compliant": True,
                "actual": "Not provided",
                "required": "Habitable space must comply with California Residential Code; typical living areas require at least 7 ft ceiling height (CRC; confirm room type).",
                "citation": "2025 CRC / HCD ADU Handbook (habitability); HCD Glossary p. 6",
            }
        )
        add_radar("Ceiling height", True)
    else:
        ceiling_ok = ch >= 7.0
        results.append(
            {
                "rule": "Minimum habitable ceiling height (pre-check)",
                "is_compliant": ceiling_ok,
                "actual": f"{ch:.2f} ft",
                "required": "≥ 7 ft 0 in for habitable space per typical CRC Table R304 (verify kitchen/bath/bedroom rules)",
                "citation": "2025 California Residential Code; HCD ADU Handbook",
            }
        )
        add_radar("Ceiling height", ceiling_ok)

    # --- Impact fees (SB 543 / Gov. Code § 66311.5) ---
    if t != "JADU":
        fee_exempt = params.proposed_adu_sqft <= 750.0
        results.append(
            {
                "rule": "School / impact fees (750 sf threshold)",
                "is_compliant": True,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": (
                    "ADUs with ≤ 750 sf interior livable space: impact fees shall not be imposed (Gov. Code § 66311.5); larger ADUs — fees must be proportionate to primary dwelling."
                    if fee_exempt
                    else "> 750 sf — impact fees, if any, must be proportionate to burden vs. primary dwelling (HCD Handbook p. 45–46)."
                ),
                "citation": "Gov. Code § 66311.5, subds. (a)–(d); HCD Handbook p. 45–46",
            }
        )
    else:
        results.append(
            {
                "rule": "School / impact fees (JADU)",
                "is_compliant": True,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": "JADUs ≤ 500 sf: follow § 66311.5 fee rules and assessable-space provisions (HCD Handbook p. 45–46).",
                "citation": "Gov. Code § 66311.5; HCD Handbook p. 45–46",
            }
        )
    add_radar("Impact fees (info)", True)

    parking_exempt = params.is_near_transit
    results.append(
        {
            "rule": "Parking standards (transit and other exemptions)",
            "is_compliant": True,
            "actual": (
                "Within one-half mile walking distance of public transit (or other § 66322(a) criteria): parking standards shall not be imposed."
                if parking_exempt
                else "Transit proximity not declared — review Gov. Code § 66322(a) list (historic districts, tandem, car share, etc.); parking may not exceed one space per unit or bedroom, whichever is less."
            ),
            "required": "See Gov. Code §§ 66322(a) (exemptions), 66314, subd. (d)(10) (parking cap); HCD Handbook p. 33.",
            "citation": "Gov. Code §§ 66322, 66314, subd. (d)(10); HCD Handbook p. 33",
        }
    )
    add_radar("Parking guidance", True)

    return results, radar


EXTRACT_JSON_SCHEMA: Dict[str, Any] = {
    "type": "OBJECT",
    "properties": {
        "project_address": {"type": "STRING"},
        "apn": {"type": "STRING"},
        "lot_size_sqft": {"type": "NUMBER"},
        "primary_dwelling_sqft": {"type": "NUMBER"},
        "adu_type": {"type": "STRING", "description": "Detached | Attached | JADU"},
        "proposed_adu_sqft": {"type": "NUMBER"},
        "rear_setback_ft": {"type": "NUMBER"},
        "side_setback_ft": {"type": "NUMBER"},
        "front_setback_ft": {"type": "NUMBER"},
        "proposed_height_ft": {"type": "NUMBER"},
        "is_near_transit": {"type": "BOOLEAN"},
        "is_jadu_within_primary_dwelling": {"type": "BOOLEAN"},
        "stories": {"type": "NUMBER"},
        "separation_from_primary_ft": {
            "type": "NUMBER",
            "description": "Detached ADU: distance to primary dwelling in feet; use 0 if unknown",
        },
        "jadu_has_separate_entrance": {"type": "BOOLEAN"},
        "adu_bedroom_count": {"type": "NUMBER"},
        "primary_structure_height_ft": {"type": "NUMBER"},
        "adu_permitting_track": {
            "type": "STRING",
            "description": "66314 (default) or 66323_detached for new detached ADU under § 66323(a)(2)",
        },
        "jadu_shares_sanitation_with_primary": {"type": "BOOLEAN"},
        "jadu_has_separate_bathroom": {"type": "BOOLEAN"},
        "jadu_interior_entrance_to_main": {"type": "BOOLEAN"},
        "owner_occupies_primary": {"type": "BOOLEAN"},
        "min_ceiling_height_ft": {"type": "NUMBER"},
        "roof_type_notes": {"type": "STRING"},
    },
    "required": [
        "project_address",
        "adu_type",
        "proposed_adu_sqft",
        "rear_setback_ft",
        "side_setback_ft",
        "proposed_height_ft",
        "is_near_transit",
    ],
}


@app.post("/api/extract")
async def extract_data(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

    tmp_path = ""
    gemini_name: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        gemini_file = client.files.upload(file=tmp_path)
        gemini_name = gemini_file.name
        while "PROCESSING" in str(getattr(gemini_file, "state", "")):
            time.sleep(1)
            gemini_file = client.files.get(name=gemini_file.name)

        prompt = (
            "You are a California ADU intake assistant. Extract fields from this Project Data Sheet PDF. "
            "Use US customary units (feet, square feet). Use 0 or false when unknown. "
            "adu_type must be exactly one of: Detached, Attached, JADU. "
            "All free-text fields must be in English."
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt, gemini_file],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EXTRACT_JSON_SCHEMA,
            ),
        )
        data = json.loads(response.text or "{}")
        return {"status": "success", "data": data, "credits_charged": 0}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e!s}") from e
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        if gemini_name:
            try:
                client.files.delete(name=gemini_name)
            except Exception:
                pass


@app.post("/api/audit")
async def run_audit(
    request: AuditRequest,
    user_id: str = Depends(get_current_user_id),
):
    new_balance = await deduct_credits(user_id, CREDIT_AUDIT)
    params = request.parameters
    audit_results, radar = run_la_audit(params)
    failed = [r for r in audit_results if not r.get("is_compliant")]

    return {
        "status": "success",
        "audit_results": audit_results,
        "radar": radar,
        "failed_count": len(failed),
        "failed_items": failed,
        "credits_deducted": CREDIT_AUDIT,
        "credits_remaining": new_balance,
        "market": "Los Angeles, CA",
        "official_reference_url": OFFICIAL_ADU_REFERENCE_URL,
        "official_reference_website": OFFICIAL_ADU_WEBSITE,
    }


@app.post("/api/advise")
async def get_advice(
    request: AdviseRequest,
    user_id: str = Depends(get_current_user_id),
):
    new_balance = await deduct_credits(user_id, CREDIT_ADVISE)

    params_json = request.parameters.model_dump()
    failed = request.failed_items
    prompt = f"""You are a California ADU compliance advisor. Using the failed audit items and project parameters below, produce actionable remediation guidance in **English** only.

Project parameters (JSON):
{json.dumps(params_json, ensure_ascii=False, indent=2)}

Failed audit items (JSON):
{json.dumps(failed, ensure_ascii=False, indent=2)}

Structure your answer with Markdown headings and bullets:
1) Practical fixes per failed rule (setbacks, height, area, JADU § 66333 bathroom/entrance and owner-occupancy when sanitation is shared, 66323 vs 66314 size tracks, ceiling height, etc.)
2) Cite relevant state baselines (e.g., attached cap min(1,200, max(850 or 1,000 sf, 50% primary)), detached 1,200 sf under § 66314 or 800 sf under § 66323(a)(2), 4-ft rear/side maximum required setback, detached 16/18 ft and attached up to 25 ft vs primary height, § 66322 parking exemptions) and note when LADBS local standards may differ
3) List any missing fields or sheets needed for plan check

Tone: concise, professional."""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[prompt],
        )
        advice_text = response.text or ""
    except Exception as e:
        if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
            _memory_credits[user_id] = new_balance + CREDIT_ADVISE
        else:
            bal = await get_or_init_credits(user_id)
            await _sb_patch_credits(user_id, bal + CREDIT_ADVISE)
        raise HTTPException(
            status_code=502, detail=f"Advice generation failed: {e!s}"
        ) from e

    return {
        "status": "success",
        "advice": advice_text,
        "credits_deducted": CREDIT_ADVISE,
        "credits_remaining": new_balance,
    }


@app.get("/api/credits")
async def read_credits(user_id: str = Depends(get_current_user_id)):
    c = await get_or_init_credits(user_id)
    return {"user_id": user_id, "credits": c}


@app.post("/api/webhooks/lemonsqueezy")
async def lemonsqueezy_webhook(request: Request):
    raw = await request.body()
    if LS_WEBHOOK_SECRET:
        sig = request.headers.get("X-Signature") or ""
        mac = hmac.new(
            LS_WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(mac, sig):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    meta = payload.get("meta") or {}
    evt = meta.get("event_name")
    data = payload.get("data") or {}
    attrs = data.get("attributes") or {}

    custom = attrs.get("custom_data") or meta.get("custom_data") or {}
    user_id = custom.get("user_id") or custom.get("supabase_user_id")
    raw_credits = custom.get("credits") or attrs.get("total_credits") or 0
    try:
        credits_to_add = int(raw_credits) if raw_credits is not None else 0
    except (TypeError, ValueError):
        credits_to_add = 0

    if not user_id:
        return {"ok": True, "ignored": True, "reason": "no user_id in custom_data"}

    paid_states = ("paid", "completed", "success")
    status = (attrs.get("status") or "").lower()
    if evt and "order" in str(evt).lower() and status and status not in paid_states:
        return {"ok": True, "ignored": True, "reason": f"status {status}"}

    if credits_to_add <= 0:
        for key in ("variant_name", "first_order_item_name"):
            name = str(attrs.get(key) or "")
            if "500" in name:
                credits_to_add = 500
                break

    if credits_to_add <= 0:
        return {"ok": True, "ignored": True, "reason": "no credits_to_add"}

    cur = await get_or_init_credits(str(user_id))
    new_bal = cur + credits_to_add
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        _memory_credits[str(user_id)] = new_bal
    else:
        await _sb_patch_credits(str(user_id), new_bal)

    return {
        "ok": True,
        "user_id": str(user_id),
        "credits_added": credits_to_add,
        "balance": new_bal,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "adu-copilot"}
