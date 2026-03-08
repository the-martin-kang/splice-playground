
# Developer GUI for splice-playground backend (STEP1~STEP3)
# - STEP1: list diseases
# - STEP2: show disease payload (regions + SNV)
# - STEP2-2: create state with edits
# - STEP3: run splicing prediction (A 방식: POST /api/states/{state_id}/splicing)
#
# This UI is intentionally minimal: it's for you (developer) to verify correctness.

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

import streamlit as st
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np


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
# Plotting (Mission6-style)
# -------------------------

def _infer_strand_from_regions(regions: List[Dict[str, Any]]) -> str:
    # Backend STEP3 response may not include strand. For display only.
    # Prefer explicit payload['strand'] when available; otherwise default '+'.
    return "+"


def _draw_transcript_track(ax, start_x: int, end_x: int, strand: str):
    ax.plot([start_x, end_x], [0.5, 0.5], color="black", lw=1.2, zorder=1)
    span = max(1, end_x - start_x)
    n_arrows = max(4, min(9, span // 1500))
    xs = np.linspace(start_x + span * 0.05, end_x - span * 0.05, n_arrows)
    dx = max(250, int(span * 0.03))
    for x in xs:
        if strand == "-":
            ax.annotate("", xy=(x - dx, 0.5), xytext=(x, 0.5),
                        arrowprops=dict(arrowstyle="->", lw=1.0, color="black"))
        else:
            ax.annotate("", xy=(x + dx, 0.5), xytext=(x, 0.5),
                        arrowprops=dict(arrowstyle="->", lw=1.0, color="black"))


def _draw_exons(ax, regions: List[Dict[str, Any]]):
    # Mission6-like: show exon boxes only, no overlapping intron labels.
    for r in regions:
        if str(r.get("region_type")) != "exon":
            continue
        s = int(r["gene_start_idx"])
        e = int(r["gene_end_idx"])
        w = max(1, e - s + 1)
        rect = Rectangle((s, 0.35), w, 0.30, facecolor="0.7", edgecolor="0.2", lw=1.0, zorder=2)
        ax.add_patch(rect)




def _plot_overlap_spikes(ax, x, y_ref, y_alt, *, ref_color="royalblue", alt_color="lightsalmon", overlap_color="purple", label_ref="Ref", label_alt="Alt", eps=1e-8):
    """
    Mission6-style sparse spike plot with explicit purple overlap.
    For each x:
      common = min(ref, alt) -> purple
      extra ref  = ref-common -> blue above common
      extra alt  = alt-common -> orange above common
    This avoids one line hiding the other and makes exact overlap visually purple.
    """
    x_arr = np.asarray(x)
    ref = np.asarray(y_ref, dtype=float)
    alt = np.asarray(y_alt, dtype=float)

    common = np.minimum(ref, alt)
    mask = (ref > eps) | (alt > eps)
    if not np.any(mask):
        # still create legend handles
        ax.plot([], [], color=ref_color, lw=1.6, label=label_ref)
        ax.plot([], [], color=alt_color, lw=1.6, label=label_alt)
        return

    xm = x_arr[mask]
    refm = ref[mask]
    altm = alt[mask]
    commonm = common[mask]

    # overlap first
    ax.vlines(xm, 0.0, commonm, color=overlap_color, lw=2.0, alpha=0.95, zorder=3)

    # ref-only above overlap
    ref_extra_mask = refm > commonm + eps
    if np.any(ref_extra_mask):
        ax.vlines(
            xm[ref_extra_mask],
            commonm[ref_extra_mask],
            refm[ref_extra_mask],
            color=ref_color,
            lw=2.0,
            alpha=0.95,
            zorder=4,
        )

    # alt-only above overlap
    alt_extra_mask = altm > commonm + eps
    if np.any(alt_extra_mask):
        ax.vlines(
            xm[alt_extra_mask],
            commonm[alt_extra_mask],
            altm[alt_extra_mask],
            color=alt_color,
            lw=2.0,
            alpha=0.95,
            zorder=5,
        )

    # tiny invisible handles for legend
    ax.plot([], [], color=ref_color, lw=1.8, label=label_ref)
    ax.plot([], [], color=alt_color, lw=1.8, label=label_alt)

def plot_splicing_payload(
    payload: Dict[str, Any],
    *,
    title: str = "",
    subtitle: Optional[str] = None,
    strand: str = "+",
):
    """
    Plot in mission6 style:
      - top: exon track only
      - middle: acceptor (Ref vs Alt)
      - bottom: donor (Ref vs Alt)
    """
    target_start = int(payload["target_start_gene0"])
    target_end = int(payload["target_end_gene0"])
    target_len = int(payload["target_len"])
    snv_pos = int(payload["snv_pos_gene0"])

    prob_ref = payload["prob_ref"]  # [3][L]
    prob_alt = payload["prob_alt"]  # [3][L]

    if len(prob_ref) != 3 or len(prob_alt) != 3:
        raise ValueError("prob_ref/prob_alt must be [3][L]")
    if len(prob_ref[0]) != target_len or len(prob_alt[0]) != target_len:
        raise ValueError("Probability length mismatch vs target_len")

    x = list(range(target_start, target_end))
    if len(x) != target_len:
        x = list(range(target_len))

    regions = payload.get("target_regions", [])

    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(3, 1, height_ratios=[0.9, 1.2, 1.2], hspace=0.42)

    ax_top = fig.add_subplot(gs[0])
    ax_acc = fig.add_subplot(gs[1], sharex=ax_top)
    ax_don = fig.add_subplot(gs[2], sharex=ax_top)

    # --- Top track: mission6-style exon boxes + arrows ---
    _draw_transcript_track(ax_top, x[0], x[-1], strand)
    _draw_exons(ax_top, regions)
    ax_top.set_ylim(0.25, 0.7)
    ax_top.set_yticks([])
    ax_top.set_ylabel("Exons")
    ax_top.grid(False)

    # --- Middle: acceptor (Ref/Alt overlap shown in purple) ---
    acc_ref = prob_ref[1]
    acc_alt = prob_alt[1]
    _plot_overlap_spikes(ax_acc, x, acc_ref, acc_alt, label_ref="Ref", label_alt="Alt")
    ax_acc.axvline(snv_pos, linestyle="--", linewidth=1.2, color="black", alpha=0.7)
    ax_acc.set_ylim(0, 1.0)
    ax_acc.set_ylabel("P(acceptor)")
    ax_acc.legend(loc="upper right")

    # --- Bottom: donor (Ref/Alt overlap shown in purple) ---
    don_ref = prob_ref[2]
    don_alt = prob_alt[2]
    _plot_overlap_spikes(ax_don, x, don_ref, don_alt, label_ref="Ref", label_alt="Alt")
    ax_don.axvline(snv_pos, linestyle="--", linewidth=1.2, color="black", alpha=0.7)
    ax_don.set_ylim(0, 1.0)
    ax_don.set_ylabel("P(donor)")
    ax_don.set_xlabel("gene0 coordinate")
    ax_don.legend(loc="upper right")

    if title:
        fig.suptitle(title, fontsize=13)
    if subtitle:
        fig.text(0.08, 0.66, subtitle, fontsize=11)

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

    try:
        # title / subtitle in mission6-style spirit
        disease_name = None
        step2p = st.session_state.get("step2_payload") or {}
        if isinstance(step2p, dict):
            disease_name = ((step2p.get("disease") or {}).get("disease_name")) or None
            strand = ((step2p.get("gene") or {}).get("strand")) or "+"
        else:
            strand = "+"

        title = f'{resp.get("gene_id")} | {resp.get("disease_id")} | {resp.get("model_version")} | radius={resp.get("region_radius")} flank={resp.get("flank")}'
        fig = plot_splicing_payload(resp, title=title, subtitle=disease_name, strand=strand)
        st.pyplot(fig, clear_figure=True)
    except Exception as e:
        st.error(f"Plot error: {e}")
