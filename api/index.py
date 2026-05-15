import os
import json
import math
import hmac
import hashlib
import asyncio
import logging
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import jwt
from jwt import PyJWKClient
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import tempfile

from openai import AsyncOpenAI
from pypdf import PdfReader
from google import genai
from google.genai import types

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("adu-copilot")

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
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or ""
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or ""
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
CREDIT_AUDIT = 30
CREDIT_ADVISE = 50
SIGNUP_CREDITS = int(os.getenv("SIGNUP_CREDITS", "100"))
SUPABASE_URL = (os.getenv("SUPABASE_URL") or "").rstrip("/")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET") or ""
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY") or ""
SUPABASE_JWKS_URL = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
LS_WEBHOOK_SECRET = os.getenv("LEMONSQUEEZY_WEBHOOK_SECRET") or ""
# Los Angeles Department of Building and Safety — ADU approved standard plans (reference for users)
OFFICIAL_ADU_WEBSITE="https://www.hcd.ca.gov/building-standards/adu/handbook"
deepseek = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
gemini_client: Optional[genai.Client] = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

logger.info(f"Gemini: {'available' if gemini_client else 'not configured'}, model={GEMINI_MODEL}")
logger.info(f"DeepSeek client ready — model={DEEPSEEK_MODEL}, base_url={DEEPSEEK_BASE_URL}")
logger.info(f"Supabase URL configured: {'yes' if SUPABASE_URL else 'no'}")
logger.info(f"JWT auth via JWKS: {'yes' if (SUPABASE_ANON_KEY and SUPABASE_JWKS_URL) else 'no'}")

_memory_credits: Dict[str, int] = {}


def get_current_user_id(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> str:
    """
    Resolve Supabase user id from Bearer JWT (sub).
    Supports both new Supabase ES256 (JWKS) and legacy HS256 tokens.
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

    # Try ES256 via JWKS first (new Supabase signing keys)
    if SUPABASE_ANON_KEY and SUPABASE_JWKS_URL:
        try:
            jwks_client = PyJWKClient(
                SUPABASE_JWKS_URL,
                headers={"apikey": SUPABASE_ANON_KEY},
                cache_keys=True,
            )
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256"],
                options={"verify_aud": False},
            )
            sub = payload.get("sub")
            if sub:
                return str(sub)
        except Exception:
            pass  # Fall through to HS256

    # Fall back to legacy HS256
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


# -----------------------------------------------------------------------------
# Audit i18n dictionary
# -----------------------------------------------------------------------------
_AUDIT_I18N = {
    # Floor area rules
    "rule.detached_area": {
    "en": "Detached ADU maximum interior livable space",
    "zh": "独立式 ADU 最大可居住面积",
    },

    "rule.attached_area_missing": {
        "en": "Attached ADU floor area (primary size required)",
        "zh": "附属 ADU 面积（需要主屋面积数据）",
    },
    "rule.attached_area": {
        "en": "Attached ADU maximum interior livable space",
        "zh": "附属式 ADU 最大可居住面积",
    },
    "rule.jadu_area": {
        "en": "JADU maximum interior livable space",
        "zh": "JADU 最大室内居住面积",
    },
    # JADU rules
    "rule.jadu_contained": {
        "en": "JADU must be contained within a single-family residence",
        "zh": "JADU 必须位于独户住宅内部",
    },
    "rule.jadu_bathroom_separate": {
        "en": "JADU bathroom / interior entrance (separate bathroom)",
        "zh": "JADU 卫生间 / 内部入口（独立卫生间）",
    },
    "rule.jadu_bathroom_entrance": {
        "en": "JADU interior entrance when no separate bathroom",
        "zh": "JADU 无独立卫生间时的内部入口要求",
    },
    "rule.jadu_bathroom_unknown": {
        "en": "JADU bathroom / interior entrance",
        "zh": "JADU 卫生间 / 内部入口",
    },
    "rule.jadu_owner_shared": {
        "en": "JADU owner-occupancy (shared sanitation)",
        "zh": "JADU 业主自住要求（共用卫生设施）",
    },
    "rule.jadu_owner_separate": {
        "en": "JADU owner-occupancy (separate sanitation)",
        "zh": "JADU 业主自住要求（独立卫生设施）",
    },
    "rule.jadu_owner_unknown": {
        "en": "JADU owner-occupancy (sanitation not stated)",
        "zh": "JADU 业主自住要求（卫生设施未声明）",
    },
    "rule.jadu_exterior": {
        "en": "JADU exterior access (informational)",
        "zh": "JADU 外部通道（参考项）",
    },
    # Other rules
    "rule.adu_type": {
        "en": "ADU type",
        "zh": "ADU 类型",
    },
    "rule.min_size": {
        "en": "Minimum ADU floor area (efficiency unit lower bound)",
        "zh": "ADU 最小面积（效率单元下限）",
    },
    "rule.stories": {
        "en": "ADU stories (state law)",
        "zh": "ADU 层数（州法律）",
    },
    "rule.rear_setback": {
        "en": "Rear lot line setback (state maximum required)",
        "zh": "后院退距（州法规最大要求）",
    },

    "rule.side_setback": {
        "en": "Side lot line setback (state maximum required)",
        "zh": "侧院退距（州法规最大要求）",
    },

    "rule.front_setback": {
        "en": "Front setback / 800 sf entitlement (local)",
        "zh": "前院退距 / 800 平方英尺法定权益（地方规定）",
    },
    "rule.height": {
        "en": "Maximum ADU height (state minimum local must allow)",
        "zh": "ADU 最大允许高度（州法规最低保障）",
    },
    "rule.height": {
        "en": "Maximum ADU height (state minimum local must allow)",
        "zh": "ADU 最大高度（州规定地方必须允许的最低值）",
    },
    "rule.separation": {
        "en": "Separation between ADU and other structures on the lot",
        "zh": "ADU 与地块内其他建筑的间距",
    },
     "rule.lot_area": {
        "en": "Lot area (informational)",
        "zh": "地块面积（参考项）",
    },
    "rule.ceiling_missing": {
        "en": "Minimum habitable ceiling height",
        "zh": "最低可居住层高",
    },
    "rule.ceiling": {
        "en": "Minimum habitable ceiling height (pre-check)",
        "zh": "最低可居住净高（预检查）",
    },
    "rule.impact_detached": {
        "en": "School / impact fees (750 sf threshold)",
        "zh": "学校与开发影响费（750 平方英尺阈值）",
    },
    "rule.impact_jadu": {
        "en": "School / impact fees (JADU)",
        "zh": "学校 / 影响费（JADU）",
    },
    "rule.parking": {
        "en": "Parking standards (transit and other exemptions)",
        "zh": "停车要求（公共交通及其他豁免）",
    },
    # Radar axis labels
    "radar.detached_area": {"en": "Detached area", "zh": "独立 ADU 面积"},
    "radar.attached_area": {"en": "Attached area", "zh": "附属 ADU 面积"},
    "radar.jadu_package": {"en": "JADU package", "zh": "JADU 综合"},
    "radar.adu_type": {"en": "ADU type", "zh": "ADU 类型"},
    "radar.min_size": {"en": "Minimum ADU size", "zh": "ADU 最小面积"},
    "radar.stories": {"en": "Stories (info)", "zh": "层数（参考项）"},
    "radar.rear_setback": {"en": "Rear setback", "zh": "后退退距"},
    "radar.side_setback": {"en": "Side setback", "zh": "侧边退距"},
    "radar.front_setback": {"en": "Front setback (info)", "zh": "前院退距（参考项）"},
    "radar.height": {"en": "Height", "zh": "高度"},
    "radar.separation": {"en": "Structure separation (info)", "zh": "建筑间距（参考项）"},
    "radar.lot_area": {"en": "Lot area (info)", "zh": "地块面积（参考项）"},
    "radar.ceiling": {"en": "Ceiling height", "zh": "层高"},
    "radar.impact_fees": {"en": "Impact fees (info)", "zh": "开发影响费（参考项）"},
    "radar.parking": {"en": "Parking guidance", "zh": "停车指南"},
    # Citations (reusable)
    "cite.detached_66314": {
        "en": "Gov. Code § 66314, subd. (d)(4) (up to 1,200 sf interior livable without compliant local cap; HCD Handbook p. 38)",
        "zh": "加州政府法规 § 66314(d)(4)（无合规地方上限时为 1,200 平方英尺室内居住面积；HCD 手册 p. 38）",
    },
    "cite.detached_66323": {
        "en": "Gov. Code § 66323, subd. (a)(2)(B) (HCD Handbook p. 16–17: new detached 66323 ADU, max 800 sf)",
        "zh": "加州政府法规 § 66323(a)(2)(B)（HCD 手册 p. 16-17：新建独立 66323 ADU，最大 800 平方英尺）",
    },
    "cite.attached": {
        "en": "Gov. Code § 66314, subd. (d)(4); § 66321, subd. (b)(2)–(b)(3) (HCD Handbook p. 38–39)",
        "zh": "加州政府法规 § 66314(d)(4)；§ 66321(b)(2)-(b)(3)（HCD 手册 p. 38-39）",
    },
    "cite.jadu_area": {
        "en": "Gov. Code § 66313, subd. (d); § 66333 (HCD Handbook p. 28)",
        "zh": "加州政府法规 § 66313(d)；§ 66333（HCD 手册 p. 28）",
    },
    "cite.jadu_contained": {
        "en": "Gov. Code § 66333, subd. (d); HCD Handbook p. 28",
        "zh": "加州政府法规 § 66333(d)；HCD 手册 p. 28",
    },
    "cite.jadu_sanitation": {
        "en": "Gov. Code § 66333, subd. (e); HCD Handbook p. 28",
        "zh": "加州政府法规 § 66333(e)；HCD 手册 p. 28",
    },
    "cite.jadu_owner": {
        "en": "Gov. Code § 66333, subd. (b); HCD Handbook p. 32, 45",
        "zh": "加州政府法规 § 66333(b)；HCD 手册 p. 32, 45",
    },
    "cite.jadu_owner_separate": {
        "en": "Gov. Code § 66333, subd. (b); HCD Handbook p. 32",
        "zh": "加州政府法规 § 66333(b)；HCD 手册 p. 32",
    },
    "cite.jadu_exterior": {
        "en": "Gov. Code §§ 66323, subd. (a)(1); 66333; HCD Handbook p. 16–17, 28",
        "zh": "加州政府法规 § 66323(a)(1)；§ 66333；HCD 手册 p. 16-17, 28",
    },
    "cite.min_size": {
        "en": "HCD ADU Handbook p. 38 (efficiency units); HSC § 17958.1",
        "zh": "HCD ADU 手册 p. 38（效率单元）；HSC § 17958.1",
    },
    "cite.stories": {
        "en": "Gov. Code § 66321, subd. (b)(4)(D); HCD Handbook p. 24",
        "zh": "加州政府法规 § 66321(b)(4)(D)；HCD 手册 p. 24",
    },
    "cite.rear_setback": {
        "en": "Gov. Code § 66314, subd. (d)(7); HCD Handbook p. 37",
        "zh": "加州政府法规 § 66314(d)(7)；HCD 手册 p. 37",
    },
    "cite.front_setback": {
        "en": "Gov. Code § 66321, subd. (b)(3); HCD Handbook p. 37",
        "zh": "加州政府法规 § 66321(b)(3)；HCD 手册 p. 37",
    },
    "cite.height": {
        "en": "Gov. Code § 66321, subd. (b)(4); HCD Handbook p. 24",
        "zh": "加州政府法规 § 66321(b)(4)；HCD 手册 p. 24",
    },
    "cite.height_jadu": {
        "en": "Gov. Code § 66323, subd. (a)(1); HCD Handbook p. 39–40",
        "zh": "加州政府法规 § 66323(a)(1)；HCD 手册 p. 39-40",
    },
    "cite.separation": {
        "en": "HCD ADU Handbook p. 37; Gov. Code § 66314, subd. (d)(8)",
        "zh": "HCD ADU 手册 p. 37；加州政府法规 § 66314(d)(8)",
    },
    "cite.lot": {
        "en": "Gov. Code § 66314, subd. (b)(1); HCD Handbook p. 38",
        "zh": "加州政府法规 § 66314(b)(1)；HCD 手册 p. 38",
    },
    "cite.ceiling": {
        "en": "2025 California Residential Code; HCD ADU Handbook",
        "zh": "2025 加州住宅法规；HCD ADU 手册",
    },
    "cite.impact": {
        "en": "Gov. Code § 66311.5, subds. (a)–(d); HCD Handbook p. 45–46",
        "zh": "加州政府法规 § 66311.5(a)-(d)；HCD 手册 p. 45-46",
    },
    "cite.parking": {
        "en": "Gov. Code §§ 66322, 66314, subd. (d)(10); HCD Handbook p. 33",
        "zh": "加州政府法规 § 66322、§ 66314(d)(10)；HCD 手册 p. 33",
    },
    # Misc strings
    "actual.unknown": {"en": "Unknown", "zh": "未知"},
    "actual.yes": {"en": "Yes", "zh": "是"},
    "actual.no": {"en": "No", "zh": "否"},
    "actual.not_provided": {"en": "Not provided", "zh": "未提供"},
    "required.yes_in_dwelling": {
        "en": "Yes — entirely within existing or proposed single-family residence (not accessory structures only)",
        "zh": "是 — 完全位于现有或拟建独户住宅内部（非仅附属建筑）",
    },
    "required.yes": {"en": "Yes", "zh": "是"},
    "actual.sanitation_separate": {"en": "Sanitation not shared with primary", "zh": "未与主屋共用卫生设施"},
    "actual.sanitation_unknown": {"en": "Unknown whether sanitation is shared", "zh": "是否共用卫生设施未知"},
    "req.sanitation_declare": {
        "en": "Declare shared vs. separate sanitation — owner-occupancy is required when facilities are shared.",
        "zh": "请声明共用或独立卫生设施 — 共用时需满足业主自住要求。",
    },
    "cite.ceiling_crc": {
        "en": "2025 CRC / HCD ADU Handbook (habitability); HCD Glossary p. 6",
        "zh": "2025 加州住宅法规 / HCD ADU 手册（可居住性）；HCD 术语表 p. 6",
    },
    "required.detached": {"en": "Detached | Attached | JADU", "zh": "Detached | Attached | JADU"},
    # Long required descriptions
    "req.jadu_sanitation_separate": {
        "en": "No additional interior-entrance requirement solely for sanitation (HCD Handbook p. 28).",
        "zh": "仅卫生设施相关，无额外的内部入口要求（HCD 手册 p. 28）。",
    },
    "req.jadu_entrance_needed": {
        "en": "Interior entrance to the primary dwelling main living area (when JADU lacks separate bathroom)",
        "zh": "通往主屋主要生活区的内部入口（当 JADU 无独立卫生间时）",
    },
    "req.jadu_bathroom_unknown": {
        "en": "Provide whether the JADU has a separate bathroom; if not, confirm interior entrance to main living area per § 66333(e)(2).",
        "zh": "请说明 JADU 是否有独立卫生间；如无，请确认通往主屋主要生活区的内部入口（§ 66333(e)(2)）。",
    },
    "req.jadu_owner_shared": {
        "en": "Yes — owner must reside in the primary residence or the JADU when sanitation is shared (AB 1154, eff. Jan. 1, 2026)",
        "zh": "是 — 共用卫生设施时，业主必须居住在主屋或 JADU 中（AB 1154，2026 年 1 月 1 日生效）",
    },
    "req.jadu_owner_not_required": {
        "en": "Owner-occupancy is not required by state law when the JADU does not share sanitation (subject to narrow exceptions in § 66333(b)).",
        "zh": "当 JADU 不共用卫生设施时，州法律不要求业主自住（§ 66333(b) 有少数例外）。",
    },
    "req.jadu_exterior": {
        "en": "State law does not require a separate exterior entrance for every JADU; access rules depend on configuration (HCD FAQ p. 28).",
        "zh": "州法律不要求每个 JADU 都设置独立外部入口；通道规则取决于具体配置（HCD FAQ p. 28）。",
    },
    "req.min_size": {
        "en": "≥ 150 sq ft for a typical standalone efficiency unit (local ordinance may not prohibit efficiency units this small; HSC § 17958.1)",
        "zh": "≥ 150 平方英尺（典型独立效率单元；地方法规不得禁止此面积的效率单元；HSC § 17958.1）",
    },
    "req.stories_info": {
        "en": "No statutory maximum number of stories; local agency must allow at least two stories if height/building standards can accommodate (HCD Handbook p. 24).",
        "zh": "州法律未规定最高层数；如高度和建筑标准允许，地方政府须允许至少两层（HCD 手册 p. 24）。",
    },
    "req.rear_setback": {
        "en": "≥ 4 ft from rear lot line (local agency may not require more than 4 ft for attached/detached ADU; HCD Handbook p. 37)",
        "zh": "≥ 4 英尺（距离后地界线；地方政府不得要求附属/独立 ADU 退距超过 4 英尺；HCD 手册 p. 37）",
    },
    "req.side_setback": {
        "en": "≥ 4 ft from side lot line (same standard; HCD Handbook p. 37)",
        "zh": "≥ 4 英尺（距离侧边地界线；与后退标准相同；HCD 手册 p. 37）",
    },
    "req.front_setback": {
        "en": "Front setbacks may apply locally but cannot preclude an ADU of at least 800 sf with 4-ft rear/side setbacks (Gov. Code § 66321, subd. (b)(3); HCD Handbook p. 37).",
        "zh": "地方可适用前院退距要求，但不得妨碍建造至少 800 平方英尺且后/侧退距 4 英尺的 ADU（§ 66321(b)(3)；HCD 手册 p. 37）。",
    },
    "req.separation": {
        "en": "State ADU Law does not set a minimum distance between structures; comply with Building/Fire Code and any objective local standards (HCD Handbook p. 37).",
        "zh": "州 ADU 法律未规定建筑间的最小距离；需遵守建筑/消防规范及地方客观标准（HCD 手册 p. 37）。",
    },
    "req.lot_min_impose": {
        "en": "Local governments may not impose minimum lot size requirements for ADUs (Gov. Code § 66314, subd. (b)(1); HCD Handbook p. 38).",
        "zh": "地方政府不得对 ADU 施加最小地块面积要求（§ 66314(b)(1)；HCD 手册 p. 38）。",
    },
    "req.lot_min_standards": {
        "en": "Minimum lot size standards may not be applied to ADUs under state law.",
        "zh": "根据州法律，最小地块面积标准不得适用于 ADU。",
    },
    "req.ceiling_typical": {
        "en": "Habitable space must comply with California Residential Code; typical living areas require at least 7 ft ceiling height (CRC; confirm room type).",
        "zh": "可居住空间须符合加州住宅法规；典型生活区要求至少 7 英尺层高（CRC；需确认房间类型）。",
    },
    "req.ceiling_7ft": {
        "en": "≥ 7 ft 0 in for habitable space per typical CRC Table R304 (verify kitchen/bath/bedroom rules)",
        "zh": "≥ 7 英尺 0 英寸（典型 CRC 表 R304 可居住空间标准；请核实厨房/卫生间/卧室规则）",
    },
    "req.impact_exempt": {
        "en": "ADUs with ≤ 750 sf interior livable space: impact fees shall not be imposed (Gov. Code § 66311.5); larger ADUs — fees must be proportionate to primary dwelling.",
        "zh": "室内居住面积 ≤ 750 平方英尺的 ADU：不得征收影响费（§ 66311.5）；更大 ADU — 费用须与主屋成比例。",
    },
    "req.impact_larger": {
        "en": "> 750 sf — impact fees, if any, must be proportionate to burden vs. primary dwelling (HCD Handbook p. 45–46).",
        "zh": "> 750 平方英尺 — 如有影响费，须与主屋负担成比例（HCD 手册 p. 45-46）。",
    },
    "req.impact_jadu": {
        "en": "JADUs ≤ 500 sf: follow § 66311.5 fee rules and assessable-space provisions (HCD Handbook p. 45–46).",
        "zh": "JADU ≤ 500 平方英尺：遵循 § 66311.5 费用规则及可评估空间条款（HCD 手册 p. 45-46）。",
    },
    "req.parking_exempt": {
        "en": "Within one-half mile walking distance of public transit (or other § 66322(a) criteria): parking standards shall not be imposed.",
        "zh": "位于公交站点半英里步行范围内（或满足其他 § 66322(a) 条件）：不得施加停车标准。",
    },
    "req.parking_default": {
        "en": "Transit proximity not declared — review Gov. Code § 66322(a) list (historic districts, tandem, car share, etc.); parking may not exceed one space per unit or bedroom, whichever is less.",
        "zh": "未声明邻近公交 — 请参阅 § 66322(a) 清单（历史街区、串联停车、共享汽车等）；停车位不得超过每单元或每卧室一个（取较少者）。",
    },
    "req.parking_see": {
        "en": "See Gov. Code §§ 66322(a) (exemptions), 66314, subd. (d)(10) (parking cap); HCD Handbook p. 33.",
        "zh": "参见 § 66322(a)（豁免）、§ 66314(d)(10)（停车上限）；HCD 手册 p. 33。",
    },
    "req.cap_note_detached": {
        "en": "Up to 18 ft on a lot within one-half mile of a major transit stop or HQTC (§ 66321(b)(4)(B)), including allowance described for roof pitch aligned with primary dwelling.",
        "zh": "距主要公交站点或 HQTC 半英里范围内的地块最高 18 英尺（§ 66321(b)(4)(B)），含与主屋屋顶坡度一致的额外高度。",
    },
    "req.cap_note_detached_base": {
        "en": "At least 16 ft maximum height must be allowed for detached ADUs (§ 66321(b)(4)(A)).",
        "zh": "独立 ADU 必须允许至少 16 英尺最大高度（§ 66321(b)(4)(A)）。",
    },
    "req.cap_note_attached_with_ph": {
        "en": "min(25 ft, primary zoning height {ph:.1f} ft) = {cap:.1f} ft",
        "zh": "min(25 英尺, 主屋限高 {ph:.1f} 英尺) = {cap:.1f} 英尺",
    },
    "req.cap_note_attached_no_ph": {
        "en": "25 ft (no primary height provided — using state maximum for attached ADUs)",
        "zh": "25 英尺（未提供主屋高度 — 使用州规定的附属 ADU 最大值）",
    },
    "req.height_jadu": {
        "en": "Height is limited by the existing single-family envelope (conversions; HCD Handbook p. 39–40).",
        "zh": "高度受现有独户住宅外轮廓限制（改建类；HCD 手册 p. 39-40）。",
    },
    "req.cap_note_attached_subd": {
        "en": "Primary dwelling floor area is required to check the 50% cap.",
        "zh": "检查 50% 面积上限需要主屋面积数据。",
    },
    # Small lot note
    "note.small_lot": {
        "en": " — smaller lots may still permit ADUs; confirm utilities and access.",
        "zh": " — 较小地块仍可允许 ADU；请确认公用设施和通道。",
    },
    # Parking notes (embedded in actual field)
    "actual.parking_exempt": {
        "en": "Within one-half mile walking distance of public transit (or other § 66322(a) criteria): parking standards shall not be imposed.",
        "zh": "位于公交站点半英里步行范围内（或满足其他 § 66322(a) 条件）：不得施加停车标准。",
    },
    "actual.parking_not_declared": {
        "en": "Transit proximity not declared — review Gov. Code § 66322(a) list (historic districts, tandem, car share, etc.); parking may not exceed one space per unit or bedroom, whichever is less.",
        "zh": "未声明邻近公交 — 请参阅 § 66322(a) 清单；停车位不得超过每单元或每卧室一个（取较少者）。",
    },
}


def _t(key: str, lang: str, **kwargs: Any) -> str:
    """Look up audit i18n string. Falls back to English."""
    entry = _AUDIT_I18N.get(key, {})
    text = entry.get(lang) or entry.get("en") or key
    if kwargs:
        text = text.format(**kwargs)
    return text


def run_la_audit(params: ADUParameters, lang: str = "en") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Deterministic California pre-check aligned to HCD ADU Handbook (March 2026).
    """
    t = _norm_adu_type(params.adu_type)
    results: List[Dict[str, Any]] = []
    radar: List[Dict[str, Any]] = []

    def add_radar(axis_key: str, compliant: bool, weight: float = 1.0) -> None:
        radar.append(
            {
                "axis": _t(axis_key, lang),
                "value": 100.0 if compliant else 0.0,
                "max": 100.0,
                "weight": weight,
            }
        )

    # --- Floor area by ADU type (HCD ADU Handbook Mar 2026; Gov. Code §§ 66314, 66321, 66323) ---
    if t == "Detached":
        if _is_66323_detached_track(params, t):
            max_sq = 800.0
            cite = _t("cite.detached_66323", lang)
        else:
            max_sq = 1200.0
            cite = _t("cite.detached_66314", lang)
        ok = params.proposed_adu_sqft <= max_sq
        results.append(
            {
                "rule": _t("rule.detached_area", lang),
                "is_compliant": ok,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": f"≤ {max_sq:.0f} sq ft",
                "citation": cite,
            }
        )
        add_radar("radar.detached_area", ok)
    elif t == "Attached":
        cap, cap_note = _max_attached_sqft(
            params.primary_dwelling_sqft, params.adu_bedroom_count
        )
        if math.isnan(cap):
            ok = False
            results.append(
                {
                    "rule": _t("rule.attached_area_missing", lang),
                    "is_compliant": False,
                    "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                    "required": _t("req.cap_note_attached_subd", lang) if "required to check" in str(cap_note) else cap_note,
                    "citation": _t("cite.attached", lang),
                }
            )
        else:
            ok = params.proposed_adu_sqft <= cap
            results.append(
                {
                    "rule": _t("rule.attached_area", lang),
                    "is_compliant": ok,
                    "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                    "required": f"≤ {cap:.0f} sq ft ({cap_note})",
                    "citation": _t("cite.attached", lang),
                }
            )
        add_radar("radar.attached_area", ok)
    elif t == "JADU":
        max_sq = 500.0
        ok_area = params.proposed_adu_sqft <= max_sq
        results.append(
            {
                "rule": _t("rule.jadu_area", lang),
                "is_compliant": ok_area,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": f"≤ {max_sq:.0f} sq ft",
                "citation": _t("cite.jadu_area", lang),
            }
        )
        in_dwelling = params.is_jadu_within_primary_dwelling
        if in_dwelling is None:
            results.append(
                {
                    "rule": _t("rule.jadu_contained", lang),
                    "is_compliant": False,
                    "actual": _t("actual.unknown", lang),
                    "required": _t("required.yes_in_dwelling", lang),
                    "citation": _t("cite.jadu_contained", lang),
                }
            )
            ok_loc = False
        else:
            ok_loc = bool(in_dwelling)
            results.append(
                {
                    "rule": _t("rule.jadu_contained", lang),
                    "is_compliant": ok_loc,
                    "actual": _t("actual.yes", lang) if ok_loc else _t("actual.no", lang),
                    "required": _t("required.yes", lang),
                    "citation": _t("cite.jadu_contained", lang),
                }
            )

        # § 66333(e)(2): if no separate bathroom, interior entrance to main living area required
        sb = params.jadu_has_separate_bathroom
        ie = params.jadu_interior_entrance_to_main
        if sb is True:
            ok_bath_ent = True
            results.append(
                {
                    "rule": _t("rule.jadu_bathroom_separate", lang),
                    "is_compliant": True,
                    "actual": _t("actual.separate_bathroom", lang),
                    "required": _t("req.jadu_sanitation_separate", lang),
                    "citation": _t("cite.jadu_sanitation", lang),
                }
            )
        elif sb is False:
            ok_ent = ie is True
            results.append(
                {
                    "rule": _t("rule.jadu_bathroom_entrance", lang),
                    "is_compliant": ok_ent,
                    "actual": (
                        _t("actual.yes", lang)
                        if ie is True
                        else (_t("actual.no", lang) if ie is False else _t("actual.unknown", lang))
                    ),
                    "required": _t("req.jadu_entrance_needed", lang),
                    "citation": _t("cite.jadu_sanitation", lang),
                }
            )
            ok_bath_ent = ok_ent
        else:
            ok_bath_ent = True
            results.append(
                {
                    "rule": _t("rule.jadu_bathroom_unknown", lang),
                    "is_compliant": True,
                    "actual": _t("actual.unknown", lang),
                    "required": _t("req.jadu_bathroom_unknown", lang),
                    "citation": _t("cite.jadu_sanitation", lang),
                }
            )

        shares = params.jadu_shares_sanitation_with_primary
        own = params.owner_occupies_primary
        if shares is True:
            ok_own = own is True
            results.append(
                {
                    "rule": _t("rule.jadu_owner_shared", lang),
                    "is_compliant": ok_own,
                    "actual": (
                        _t("actual.yes", lang)
                        if own is True
                        else (_t("actual.no", lang) if own is False else _t("actual.unknown", lang))
                    ),
                    "required": _t("req.jadu_owner_shared", lang),
                    "citation": _t("cite.jadu_owner", lang),
                }
            )
        elif shares is False:
            ok_own = True
            results.append(
                {
                    "rule": _t("rule.jadu_owner_separate", lang),
                    "is_compliant": True,
                    "actual": _t("actual.sanitation_separate", lang),
                    "required": _t("req.jadu_owner_not_required", lang),
                    "citation": _t("cite.jadu_owner_separate", lang),
                }
            )
        else:
            ok_own = True
            results.append(
                {
                    "rule": _t("rule.jadu_owner_unknown", lang),
                    "is_compliant": True,
                    "actual": _t("actual.sanitation_unknown", lang),
                    "required": _t("req.sanitation_declare", lang),
                    "citation": _t("cite.jadu_owner_separate", lang),
                }
            )

        results.append(
            {
                "rule": _t("rule.jadu_exterior", lang),
                "is_compliant": True,
                "actual": _t("actual.see_66323", lang),
                "required": _t("req.jadu_exterior", lang),
                "citation": _t("cite.jadu_exterior", lang),
            }
        )

        add_radar("radar.jadu_package", ok_area and ok_loc and ok_bath_ent and ok_own)
    else:
        results.append(
            {
                "rule": _t("rule.adu_type", lang),
                "is_compliant": False,
                "actual": params.adu_type,
                "required": _t("required.detached", lang),
                "citation": "—",
            }
        )
        add_radar("radar.adu_type", False)

    # --- Minimum unit size (efficiency / CBC) — not JADU (already capped at 500 sf) ---
    if t in ("Detached", "Attached"):
        min_eff = 150.0
        ok_min = params.proposed_adu_sqft >= min_eff
        results.append(
            {
                "rule": _t("rule.min_size", lang),
                "is_compliant": ok_min,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": _t("req.min_size_fmt", lang, min=min_eff),
                "citation": _t("cite.min_size", lang),
            }
        )
        add_radar("radar.min_size", ok_min)

    # --- Stories: state law does not cap number of stories (HCD Handbook p. 24) ---
    results.append(
        {
            "rule": _t("rule.stories", lang),
            "is_compliant": True,
            "actual": f"{params.stories} story(ies)",
            "required": _t("req.stories_info", lang),
            "citation": _t("cite.stories", lang),
        }
    )
    add_radar("radar.stories", True)

    # --- Rear / side setbacks: agencies may not require more than 4 ft (§ 66314(d)(7)) ---
    rear_ok = params.rear_setback_ft >= 4.0
    results.append(
        {
            "rule": _t("rule.rear_setback", lang),
            "is_compliant": rear_ok,
            "actual": f"{params.rear_setback_ft:.1f} ft",
            "required": _t("req.rear_setback", lang),
            "citation": _t("cite.rear_setback", lang),
        }
    )
    add_radar("radar.rear_setback", rear_ok)

    side_ok = params.side_setback_ft >= 4.0
    results.append(
        {
            "rule": _t("rule.side_setback", lang),
            "is_compliant": side_ok,
            "actual": f"{params.side_setback_ft:.1f} ft",
            "required": _t("req.side_setback", lang),
            "citation": _t("cite.rear_setback", lang),
        }
    )
    add_radar("radar.side_setback", side_ok)

    fs = params.front_setback_ft
    results.append(
        {
            "rule": _t("rule.front_setback", lang),
            "is_compliant": True,
            "actual": f"{fs:.1f} ft" if fs is not None else "Not provided",
            "required": _t("req.front_setback", lang),
            "citation": _t("cite.front_setback", lang),
        }
    )
    add_radar("radar.front_setback", True)

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
                "rule": _t("rule.height_jadu", lang),
                "is_compliant": True,
                "actual": f"{params.proposed_height_ft:.1f} ft proposed",
                "required": _t("req.height_jadu", lang),
                "citation": _t("cite.height_jadu", lang),
            }
        )
    else:
        height_ok = params.proposed_height_ft <= h_max
        results.append(
            {
                "rule": _t("rule.height", lang),
                "is_compliant": height_ok,
                "actual": f"{params.proposed_height_ft:.1f} ft",
                "required": f"≤ {h_max:.0f} ft ({h_note})",
                "citation": _t("cite.height", lang),
            }
        )
    add_radar("radar.height", height_ok if t != "JADU" else True)

    # --- Structure separation: state ADU law is silent; verify under CBC / local objective standards ---
    sep = params.separation_from_primary_ft
    results.append(
        {
            "rule": _t("rule.separation", lang),
            "is_compliant": True,
            "actual": f"{sep:.1f} ft" if sep is not None else "Not provided",
            "required": _t("req.separation", lang),
            "citation": _t("cite.separation", lang),
        }
    )
    add_radar("radar.separation", True)

    # --- Lot size (HCD: no minimum lot size for ADUs) ---
    lot = params.lot_size_sqft
    if lot is not None and lot > 0:
        small_lot = lot < 3600
        results.append(
            {
                "rule": _t("rule.lot_area", lang),
                "is_compliant": True,
                "actual": f"{lot:.0f} sq ft"
                + (_t("note.small_lot", lang) if small_lot else ""),
                "required": _t("req.lot_min_impose", lang),
                "citation": _t("cite.lot", lang),
            }
        )
    else:
        results.append(
            {
                "rule": _t("rule.lot_area", lang),
                "is_compliant": True,
                "actual": _t("actual.not_provided", lang),
                "required": _t("req.lot_min_standards", lang),
                "citation": _t("cite.lot", lang),
            }
        )
    add_radar("radar.lot_area", True)

    ch = params.min_ceiling_height_ft
    if ch is None:
        results.append(
            {
                "rule": _t("rule.ceiling_missing", lang),
                "is_compliant": True,
                "actual": _t("actual.not_provided", lang),
                "required": _t("req.ceiling_typical", lang),
                "citation": _t("cite.ceiling_crc", lang),
            }
        )
        add_radar("radar.ceiling", True)
    else:
        ceiling_ok = ch >= 7.0
        results.append(
            {
                "rule": _t("rule.ceiling", lang),
                "is_compliant": ceiling_ok,
                "actual": f"{ch:.2f} ft",
                "required": _t("req.ceiling_7ft", lang),
                "citation": _t("cite.ceiling", lang),
            }
        )
        add_radar("radar.ceiling", ceiling_ok)

    # --- Impact fees (SB 543 / Gov. Code § 66311.5) ---
    if t != "JADU":
        fee_exempt = params.proposed_adu_sqft <= 750.0
        results.append(
            {
                "rule": _t("rule.impact_detached", lang),
                "is_compliant": True,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": _t("req.impact_exempt", lang)
                    if fee_exempt
                    else _t("req.impact_larger", lang),
                "citation": _t("cite.impact_detached", lang),
            }
        )
    else:
        results.append(
            {
                "rule": _t("rule.impact_jadu", lang),
                "is_compliant": True,
                "actual": f"{params.proposed_adu_sqft:.0f} sq ft",
                "required": _t("req.impact_jadu", lang),
                "citation": _t("cite.impact_jadu", lang),
            }
        )
    add_radar("radar.impact_fees", True)

    parking_exempt = params.is_near_transit
    results.append(
        {
            "rule": _t("rule.parking", lang),
            "is_compliant": True,
            "actual": _t("actual.parking_exempt", lang)
                if parking_exempt
                else _t("actual.parking_not_declared", lang),
            "required": _t("req.parking_see", lang),
            "citation": _t("cite.parking", lang),
        }
    )
    add_radar("radar.parking", True)

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
async def extract_data(file: UploadFile = File(...), lang: str = "en"):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")

    is_zh = lang == "zh"

    async def generate_response():
        yield " "

        pdf_bytes = await file.read()
        tmp_path = ""
        gemini_name = None

        # =====================================================================
        #  Primary: Gemini (native PDF understanding, structured JSON schema)
        # =====================================================================
        if gemini_client:
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(pdf_bytes)
                    tmp_path = tmp.name

                gemini_file = gemini_client.files.upload(file=tmp_path)
                gemini_name = gemini_file.name
                logger.info(f"Gemini: uploaded {file.filename}, name={gemini_name}")

                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                tmp_path = ""

                # Wait for Gemini processing
                while True:
                    gemini_file = gemini_client.files.get(name=gemini_name)
                    state = str(getattr(gemini_file, "state", ""))
                    if "PROCESSING" not in state:
                        break
                    yield " "
                    await asyncio.sleep(1)

                if is_zh:
                    prompt = "你是一位加州 ADU 录入助手。从此 PDF 项目数据表中提取字段。使用美制单位（英尺、平方英尺）。未知字段用 0 或 false。adu_type 必须是 Detached、Attached 或 JADU 之一。"
                else:
                    prompt = (
                        "You are a California ADU intake assistant. Extract fields from this Project Data Sheet PDF. "
                        "Use US customary units (feet, square feet). Use 0 or false when unknown. "
                        "adu_type must be exactly one of: Detached, Attached, JADU. "
                        "All free-text fields must be in English."
                    )

                task = asyncio.create_task(
                    gemini_client.aio.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=[prompt, gemini_file],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=EXTRACT_JSON_SCHEMA,
                        ),
                    )
                )
                while not task.done():
                    yield " "
                    await asyncio.sleep(0.5)

                response = task.result()
                data = json.loads(response.text or "{}")
                logger.info(f"Gemini extract success: {json.dumps(data, ensure_ascii=False)[:500]}")

                yield json.dumps({"status": "success", "data": data, "credits_charged": 0})
                return  # <-- success, skip fallback

            except Exception as e:
                logger.warning(f"Gemini extract failed, falling back to pypdf+DeepSeek: {e!s}")
            finally:
                if gemini_name:
                    try:
                        gemini_client.files.delete(name=gemini_name)
                    except Exception:
                        pass

        # =====================================================================
        #  Fallback: pypdf text extraction + DeepSeek JSON mode
        # =====================================================================
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
            pages_text: List[str] = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)

            logger.info(f"pypdf: {file.filename} — {len(reader.pages)} pages, {sum(len(t) for t in pages_text)} chars")
            no_text_msg = "此 PDF 中未找到可读文字，可能是扫描件或图片。" if is_zh else "No readable text found in this PDF. The file may be scanned or image-based."
            if not pages_text:
                yield json.dumps({"status": "error", "detail": no_text_msg})
                return

            full_text = "\n\n--- Page Break ---\n\n".join(pages_text)
            logger.info(f"pypdf text preview (first 300 chars): {full_text[:300]}")

            fields_desc = [
                "project_address (string)",
                "apn (string)",
                "lot_size_sqft (number)",
                "primary_dwelling_sqft (number)",
                "adu_type (string: Detached | Attached | JADU)",
                "proposed_adu_sqft (number)",
                "rear_setback_ft (number)",
                "side_setback_ft (number)",
                "front_setback_ft (number)",
                "proposed_height_ft (number)",
                "is_near_transit (boolean)",
                "is_jadu_within_primary_dwelling (boolean)",
                "stories (number)",
                "separation_from_primary_ft (number)",
                "adu_bedroom_count (number)",
                "primary_structure_height_ft (number)",
                "adu_permitting_track (string: 66314 or 66323_detached)",
                "jadu_shares_sanitation_with_primary (boolean)",
                "jadu_has_separate_bathroom (boolean)",
                "jadu_interior_entrance_to_main (boolean)",
                "owner_occupies_primary (boolean)",
                "min_ceiling_height_ft (number)",
                "roof_type_notes (string)",
            ]

            if is_zh:
                system_msg = "你是一个 JSON 数据提取器。始终返回有效的 JSON，不要包含任何解释。所有字段值使用英文（单位除外，使用美制单位如英尺、平方英尺）。"
                prompt = f"""你是一位加州 ADU 录入助手。从以下项目数据表文字中提取字段。
使用美制单位（英尺、平方英尺）。未知字段用 0 或 false。
adu_type 必须是下列之一：Detached、Attached、JADU。

只返回包含以下字段的有效 JSON 对象：
{json.dumps(fields_desc, indent=2)}

项目数据表文字：
{full_text[:12000]}"""
            else:
                system_msg = "You are a JSON-only data extractor. Always respond with valid JSON. Never include explanations."
                prompt = f"""You are a California ADU intake assistant. Extract the following fields from this project data sheet text.
Use US customary units (feet, square feet). Use 0 or false when unknown.
adu_type must be exactly one of: Detached, Attached, JADU.
All free-text fields must be in English.

Return ONLY a valid JSON object with these fields:
{json.dumps(fields_desc, indent=2)}

Project Data Sheet Text:
{full_text[:12000]}"""

            task = asyncio.create_task(
                deepseek.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
            )
            while not task.done():
                yield " "
                await asyncio.sleep(0.5)

            response = task.result()
            content = response.choices[0].message.content or "{}"
            logger.info(f"DeepSeek extract raw ({len(content)} chars): {content[:500]}")
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]
            data = json.loads(content)
            logger.info(f"DeepSeek extract parsed: {json.dumps(data, ensure_ascii=False)[:500]}")

            yield json.dumps({"status": "success", "data": data, "credits_charged": 0})
        except HTTPException as e:
            yield json.dumps({"status": "error", "detail": e.detail})
        except json.JSONDecodeError as e:
            logger.error(f"DeepSeek extract JSON parse failed: {e}")
            msg = "AI 返回了无效的 JSON。请重试。" if is_zh else "AI returned invalid JSON. Please try again."
            yield json.dumps({"status": "error", "detail": msg})
        except Exception as e:
            logger.error(f"Extract fallback also failed: {e}")
            yield json.dumps({"status": "error", "detail": f"Extraction failed: {e!s}"})

    return StreamingResponse(generate_response(), media_type="application/json")


@app.post("/api/audit")
async def run_audit(
    request: AuditRequest,
    user_id: str = Depends(get_current_user_id),
    lang: str = "en",
):
    new_balance = await deduct_credits(user_id, CREDIT_AUDIT)
    params = request.parameters
    audit_results, radar = run_la_audit(params, lang=lang)
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
        "official_reference_website": OFFICIAL_ADU_WEBSITE,
    }


@app.post("/api/advise")
async def get_advice(
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    body = await request.json()
    parameters = ADUParameters(**body["parameters"])
    failed = body.get("failed_items", [])
    lang = body.get("lang", "en")
    is_zh = lang == "zh"

    new_balance = await deduct_credits(user_id, CREDIT_ADVISE)

    params_json = parameters.model_dump()

    if is_zh:
        system_msg = "你是一位加州 ADU 合规专家。用结构清晰的 Markdown 格式回复，使用中文。"
        prompt = f"""你是加州 ADU 合规顾问。请根据以下未通过的审计项目和项目参数，提供切实可行的整改建议。请使用**中文**回复。

项目参数 (JSON):
{json.dumps(params_json, ensure_ascii=False, indent=2)}

未通过审计项 (JSON):
{json.dumps(failed, ensure_ascii=False, indent=2)}

请按以下 Markdown 结构组织回答：
1) 每项未通过规则的具体修复方案（退距、高度、面积、JADU § 66333 卫生间/入口及共用卫生设施时的业主自住要求、66323 vs 66314 面积轨道、层高等）
2) 引用相关加州基准（例如：附属 ADU 面积上限 min(1200, max(850或1000 sf, 50%主屋面积))，独立 ADU § 66314 下 1200 sf 或 § 66323(a)(2) 下 800 sf，后/侧退距最多 4 英尺，独立 ADU 16/18 英尺高度，附属 ADU 最高 25 英尺或主屋高度，§ 66322 停车豁免），并提示 LADBS 当地标准可能有所不同
3) 列出方案审查所需的缺失字段或表格

语气：简洁、专业。
只输出结果，不要做任何解释
"""
    else:
        system_msg = "You are a California ADU compliance expert. Reply in well-structured Markdown."
        prompt = f"""You are a California ADU compliance advisor. Using the failed audit items and project parameters below, produce actionable remediation guidance in **English** only.

Project parameters (JSON):
{json.dumps(params_json, ensure_ascii=False, indent=2)}

Failed audit items (JSON):
{json.dumps(failed, ensure_ascii=False, indent=2)}

Structure your answer with Markdown headings and bullets:
1) Practical fixes per failed rule (setbacks, height, area, JADU § 66333 bathroom/entrance and owner-occupancy when sanitation is shared, 66323 vs 66314 size tracks, ceiling height, etc.)
2) Cite relevant state baselines (e.g., attached cap min(1,200, max(850 or 1,000 sf, 50% primary)), detached 1,200 sf under § 66314 or 800 sf under § 66323(a)(2), 4-ft rear/side maximum required setback, detached 16/18 ft and attached up to 25 ft vs primary height, § 66322 parking exemptions) and note when LADBS local standards may differ
3) List any missing fields or sheets needed for plan check

Tone: concise, professional.
Output results only. Do not provide any explanations.
"""

    async def generate_response():
        yield " "

        try:
            task = asyncio.create_task(
                deepseek.chat.completions.create(
                    model=DEEPSEEK_MODEL,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                )
            )
            while not task.done():
                yield " "
                await asyncio.sleep(0.5)

            response = task.result()
            advice_text = response.choices[0].message.content or ""
            logger.info(f"Advice generated for user {user_id}: {len(advice_text)} chars, lang={lang}")
            logger.info(f"Advice preview: {advice_text[:400]}")

            yield json.dumps({
                "status": "success",
                "advice": advice_text,
                "credits_deducted": CREDIT_ADVISE,
                "credits_remaining": new_balance,
            })
        except Exception as e:
            logger.error(f"Advice failed for user {user_id}: {e}")
            if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
                _memory_credits[user_id] = new_balance + CREDIT_ADVISE
            else:
                bal = await get_or_init_credits(user_id)
                await _sb_patch_credits(user_id, bal + CREDIT_ADVISE)
            yield json.dumps({"status": "error", "detail": f"Advice generation failed: {e!s}"})

    return StreamingResponse(generate_response(), media_type="application/json")


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
