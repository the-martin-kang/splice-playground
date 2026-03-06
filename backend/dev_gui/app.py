# Developer GUI for splice-playground backend (STEP1~STEP3)
# - STEP1: list diseases
# - STEP2: show disease payload (regions + SNV)
# - STEP2-2: create state with edits
# - STEP3: run splicing prediction (A 방식: POST /api/states/{state_id}/splicing)
#
# This UI is intentionally minimal: it's for you (developer) to verify correctness.

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import matplotlib.pyplot as plt


# -------------------------
# HTTP helpers (std lib)
# -------------------------

def _join_url(base: str, path: str) -> str:
    base = base.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return base + path


def http_get_json(url: str, timeout: int = 30) -> Any:
    req = urllib.request.Request(url, headers={"accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: {e.code} {e.reason}: {body}") from e


def http_post_json(url: str, payload: Any, timeout: int = 60) -> Any:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"POST {url} failed: {e.code} {e.reason}: {body}") from e


def guess_api_prefix(backend_url: str) -> str:
    """
    Try to detect API prefix from openapi.json.
    Prefer '/api' if present.
    """
    spec = http_get_json(_join_url(backend_url, "/openapi.json"))
    paths = spec.get("paths", {}) if isinstance(spec, dict) else {}
    if "/api/diseases" in paths:
        return "/api"
    if "/diseases" in paths:
        return ""
    # fallback: if any path starts with /api/
    for p in paths.keys():
        if isinstance(p, str) and p.startswith("/api/"):
            return "/api"
    return "/api"


# -------------------------
# Normalization helpers
# -------------------------

def normalize_edits_json(text: str) -> List[Dict[str, Any]]:
    """
    Accept user input like:
      [{"pos_gene0":109442,"from":"G","to":"T"}]
    or:
      [{"pos":109442,"from":"G","to":"T"}]

    Return normalized list with keys: pos, from, to
    """
    if not text.strip():
        return []
    try:
        arr = json.loads(text)
    except Exception as e:
        raise ValueError(f"Invalid JSON for edits: {e}") from e
    if not isinstance(arr, list):
        raise ValueError("Edits JSON must be a list")
    out: List[Dict[str, Any]] = []
    for it in arr:
        if not isinstance(it, dict):
            continue
        pos = it.get("pos")
        if pos is None:
            pos = it.get("pos_gene0")
        if pos is None:
            raise ValueError(f"Edit missing pos/pos_gene0: {it}")
        fb = it.get("from") or it.get("from_base") or it.get("ref") or it.get("base_from")
        tb = it.get("to") or it.get("to_base") or it.get("alt") or it.get("base_to")
        if not fb or not tb:
            raise ValueError(f"Edit missing from/to: {it}")
        out.append({"pos": int(pos), "from": str(fb).upper(), "to": str(tb).upper()})
    return out


# -------------------------
# Plotting
# -------------------------

def plot_splicing_payload(payload: Dict[str, Any], *, title: str = ""):
    """
    Plot acceptor/donor probabilities over the target span, overlay ref vs alt.
    payload: SplicingPredictionResponse
    """
    target_start = int(payload["target_start_gene0"])
    target_end = int(payload["target_end_gene0"])
    target_len = int(payload["target_len"])
    snv_pos = int(payload["snv_pos_gene0"])

    prob_ref = payload["prob_ref"]  # [3][L]
    prob_alt = payload["prob_alt"]  # [3][L]

    # Safety
    if len(prob_ref) != 3 or len(prob_alt) != 3:
        raise ValueError("prob_ref/prob_alt must be [3][L]")
    if len(prob_ref[0]) != target_len:
        raise ValueError(f"prob_ref length mismatch: {len(prob_ref[0])} vs target_len={target_len}")

    x = list(range(target_start, target_end))
    if len(x) != target_len:
        # defensive: if end-start differs
        x = list(range(target_len))

    # Prepare figure
    fig = plt.figure(figsize=(14, 6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 2], hspace=0.1)
    ax_top = fig.add_subplot(gs[0])
    ax = fig.add_subplot(gs[1], sharex=ax_top)

    # Region track (exons shaded)
    regions = payload.get("target_regions", [])
    for r in regions:
        s = int(r["gene_start_idx"])
        e = int(r["gene_end_idx"])
        rtype = str(r["region_type"])
        label = f'{rtype}{r["region_number"]} (rel={r["rel"]})'
        ax_top.plot([s, e], [0.5, 0.5], linewidth=6)  # default color cycle
        ax_top.text((s + e) / 2, 0.65, label, ha="center", va="bottom", fontsize=8, rotation=0)
        if rtype == "exon":
            ax.axvspan(s, e, alpha=0.12)

    ax_top.set_ylim(0, 1)
    ax_top.set_yticks([])
    ax_top.set_ylabel("regions", fontsize=9)
    ax_top.grid(False)

    # Probabilities
    # class order: neither, acceptor, donor
    acc_ref = prob_ref[1]
    don_ref = prob_ref[2]
    acc_alt = prob_alt[1]
    don_alt = prob_alt[2]

    ax.plot(x, acc_ref, label="acceptor_ref")
    ax.plot(x, acc_alt, label="acceptor_alt")
    ax.plot(x, don_ref, label="donor_ref")
    ax.plot(x, don_alt, label="donor_alt")

    # SNV line
    ax.axvline(snv_pos, linestyle="--", linewidth=1)

    ax.set_ylim(0, 1.05)
    ax.set_ylabel("P(site)")
    ax.set_xlabel("gene0 coordinate")
    ax.legend(loc="upper right", fontsize=8)
    if title:
        fig.suptitle(title, fontsize=12)

    return fig


# -------------------------
# Streamlit UI
# -------------------------

st.set_page_config(page_title="splice-playground dev GUI", layout="wide")
st.title("splice-playground dev GUI (STEP1 → STEP3)")

with st.sidebar:
    st.header("Backend")
    backend_url = st.text_input("BACKEND_URL", value="http://localhost:8000")
    if st.button("Detect API prefix"):
        try:
            pref = guess_api_prefix(backend_url)
            st.session_state["api_prefix"] = pref
            st.success(f"Detected API prefix: {pref!r}")
        except Exception as e:
            st.error(str(e))

    api_prefix = st.text_input("API prefix", value=st.session_state.get("api_prefix", "/api"))
    st.divider()

    st.header("STEP3 options")
    region_radius = st.number_input("region_radius (3 => 7 regions)", min_value=0, max_value=10, value=3, step=1)
    flank = st.number_input("flank (nt each side)", min_value=0, max_value=20000, value=5000, step=500)
    include_disease_snv = st.checkbox("include_disease_snv", value=True)
    strict_ref_check = st.checkbox("strict_ref_check", value=True)
    return_target_sequence = st.checkbox("return_target_sequence", value=False)

    st.divider()
    st.caption("Tip: If endpoint 404, check prefix (/api) and redeploy backend.")


def api(path: str) -> str:
    return _join_url(backend_url, api_prefix + path)


# STEP1: list diseases
st.subheader("STEP1 - Diseases")
colA, colB = st.columns([2, 3])

with colA:
    if st.button("Load diseases"):
        try:
            d = http_get_json(api("/diseases?limit=200&offset=0"))
            st.session_state["diseases_resp"] = d
        except Exception as e:
            st.error(str(e))

diseases_resp = st.session_state.get("diseases_resp")
items = []
if isinstance(diseases_resp, dict):
    items = diseases_resp.get("items") or []

if items:
    disease_options = {f'{it.get("disease_id")} | {it.get("disease_name")}': it.get("disease_id") for it in items}
    pick_label = st.selectbox("Pick disease", options=list(disease_options.keys()))
    disease_id = disease_options[pick_label]
    st.session_state["disease_id"] = disease_id
else:
    disease_id = st.session_state.get("disease_id")

with colB:
    if items and disease_id:
        selected = next((it for it in items if it.get("disease_id") == disease_id), None)
        if selected:
            st.json(selected)
            img_url = selected.get("image_url")
            if img_url:
                st.image(img_url, caption=selected.get("image_path") or "")
            else:
                st.info("No image_url in response (check storage signed URL logic).")

st.divider()

# STEP2: disease payload
st.subheader("STEP2 - Disease payload")
if not disease_id:
    st.info("Load diseases and pick one.")
else:
    if st.button("Fetch STEP2 payload"):
        try:
            payload = http_get_json(api(f"/diseases/{urllib.parse.quote(disease_id)}?include_sequence=true"))
            st.session_state["step2_payload"] = payload
        except Exception as e:
            st.error(str(e))

payload = st.session_state.get("step2_payload")
if isinstance(payload, dict):
    st.json(payload, expanded=False)

st.divider()

# STEP2-2: create state
st.subheader("STEP2-2 - Create state (apply edits)")
default_edits = '[{"pos_gene0":109442,"from":"G","to":"T"}]'
edits_text = st.text_area("Edits JSON (list)", value=st.session_state.get("edits_text", default_edits), height=120)
st.session_state["edits_text"] = edits_text

create_col, state_col = st.columns([1, 3])
with create_col:
    if st.button("Create state"):
        try:
            edits = normalize_edits_json(edits_text)
            body = {"applied_edit": {"type": "user", "edits": edits}}
            resp = http_post_json(api(f"/diseases/{urllib.parse.quote(disease_id)}/states"), body)
            st.session_state["state_resp"] = resp
            st.session_state["state_id"] = resp.get("state_id")
            st.success(f"Created state: {resp.get('state_id')}")
        except Exception as e:
            st.error(str(e))

with state_col:
    st.json(st.session_state.get("state_resp") or {}, expanded=False)

state_id = st.session_state.get("state_id")

st.divider()

# STEP3: splicing prediction
st.subheader("STEP3 - Splicing prediction (state-based)")
if not state_id:
    st.info("Create a state first.")
else:
    if st.button("Run STEP3 splicing"):
        try:
            req = {
                "region_radius": int(region_radius),
                "flank": int(flank),
                "include_disease_snv": bool(include_disease_snv),
                "strict_ref_check": bool(strict_ref_check),
                "return_target_sequence": bool(return_target_sequence),
            }
            resp = http_post_json(api(f"/states/{urllib.parse.quote(state_id)}/splicing"), req)
            st.session_state["step3_resp"] = resp
        except Exception as e:
            st.error(str(e))

resp = st.session_state.get("step3_resp")
if isinstance(resp, dict) and resp:
    st.json(resp, expanded=False)

    # Plot
    try:
        title = f'{resp.get("gene_id")} | {resp.get("disease_id")} | {resp.get("model_version")} | radius={resp.get("region_radius")} flank={resp.get("flank")}'
        fig = plot_splicing_payload(resp, title=title)
        st.pyplot(fig, clear_figure=True)
    except Exception as e:
        st.error(f"Plot error: {e}")
