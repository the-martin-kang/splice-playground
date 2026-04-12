from __future__ import annotations

import html
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import streamlit as st
import streamlit.components.v1 as components
from matplotlib.patches import Rectangle


# -------------------------
# HTTP helpers
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


def http_get_text(url: str, timeout: int = 60) -> str:
    req = urllib.request.Request(url, headers={"accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {url} failed: {e.code} {e.reason}: {body[:500]}") from e


def guess_api_prefix(backend_url: str) -> str:
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

def _project_pos(pos_gene0: int, *, strand: str, gene_length: Optional[int], display_mode: str) -> int:
    if display_mode == "genomic_forward" and strand == "-" and gene_length:
        return int(gene_length - 1 - pos_gene0)
    return int(pos_gene0)


def _project_interval(start_gene0: int, end_gene0_inclusive: int, *, strand: str, gene_length: Optional[int], display_mode: str) -> Tuple[int, int]:
    if display_mode == "genomic_forward" and strand == "-" and gene_length:
        return int(gene_length - 1 - end_gene0_inclusive), int(gene_length - 1 - start_gene0)
    return int(start_gene0), int(end_gene0_inclusive)


def _draw_transcript_track(ax, start_x: int, end_x: int, *, arrow_direction: str):
    ax.plot([start_x, end_x], [0.5, 0.5], color="black", lw=1.2, zorder=1)
    span = max(1, end_x - start_x)
    n_arrows = max(4, min(9, span // 1500))
    xs = np.linspace(start_x + span * 0.05, end_x - span * 0.05, n_arrows)
    dx = max(250, int(span * 0.03))
    for x in xs:
        if arrow_direction == "left":
            ax.annotate("", xy=(x - dx, 0.5), xytext=(x, 0.5), arrowprops=dict(arrowstyle="->", lw=1.0, color="black"))
        else:
            ax.annotate("", xy=(x + dx, 0.5), xytext=(x, 0.5), arrowprops=dict(arrowstyle="->", lw=1.0, color="black"))


def _draw_exons(ax, regions: List[Dict[str, Any]], *, strand: str, gene_length: Optional[int], display_mode: str):
    for r in regions:
        if str(r.get("region_type")) != "exon":
            continue
        s0 = int(r["gene_start_idx"])
        e0 = int(r["gene_end_idx"])
        s, e = _project_interval(s0, e0, strand=strand, gene_length=gene_length, display_mode=display_mode)
        w = max(1, e - s + 1)
        rect = Rectangle((s, 0.35), w, 0.30, facecolor="0.7", edgecolor="0.2", lw=1.0, zorder=2)
        ax.add_patch(rect)
        exon_no = r.get("region_number")
        if exon_no is not None:
            ax.text(s + w / 2.0, 0.5, str(exon_no), ha="center", va="center", fontsize=7, color="0.1", zorder=3)


def _plot_overlap_spikes(ax, x, y_ref, y_alt, *, ref_color="royalblue", alt_color="lightsalmon", overlap_color="purple", label_ref="Ref", label_alt="Alt", eps=1e-8):
    x_arr = np.asarray(x)
    ref = np.asarray(y_ref, dtype=float)
    alt = np.asarray(y_alt, dtype=float)

    common = np.minimum(ref, alt)
    mask = (ref > eps) | (alt > eps)
    if not np.any(mask):
        ax.plot([], [], color=ref_color, lw=1.6, label=label_ref)
        ax.plot([], [], color=alt_color, lw=1.6, label=label_alt)
        return

    xm = x_arr[mask]
    refm = ref[mask]
    altm = alt[mask]
    commonm = common[mask]

    ax.vlines(xm, 0.0, commonm, color=overlap_color, lw=2.0, alpha=0.95, zorder=3)

    ref_extra_mask = refm > commonm + eps
    if np.any(ref_extra_mask):
        ax.vlines(xm[ref_extra_mask], commonm[ref_extra_mask], refm[ref_extra_mask], color=ref_color, lw=2.0, alpha=0.95, zorder=4)

    alt_extra_mask = altm > commonm + eps
    if np.any(alt_extra_mask):
        ax.vlines(xm[alt_extra_mask], commonm[alt_extra_mask], altm[alt_extra_mask], color=alt_color, lw=2.0, alpha=0.95, zorder=5)

    ax.plot([], [], color=ref_color, lw=1.8, label=label_ref)
    ax.plot([], [], color=alt_color, lw=1.8, label=label_alt)


def plot_splicing_payload(
    payload: Dict[str, Any],
    *,
    title: str = "",
    subtitle: Optional[str] = None,
    strand: str = "+",
    gene_length: Optional[int] = None,
    display_mode: str = "transcript",
):
    target_start = int(payload["target_start_gene0"])
    target_end = int(payload["target_end_gene0"])
    target_len = int(payload["target_len"])
    snv_pos = int(payload["snv_pos_gene0"])

    prob_ref = payload["prob_ref"]
    prob_alt = payload["prob_alt"]

    if len(prob_ref) != 3 or len(prob_alt) != 3:
        raise ValueError("prob_ref/prob_alt must be [3][L]")
    if len(prob_ref[0]) != target_len or len(prob_alt[0]) != target_len:
        raise ValueError("Probability length mismatch vs target_len")

    x_gene0 = list(range(target_start, target_end))
    if len(x_gene0) != target_len:
        x_gene0 = list(range(target_len))

    regions = payload.get("target_regions", [])

    if display_mode == "genomic_forward" and strand == "-" and gene_length:
        x = [int(gene_length - 1 - p) for p in x_gene0[::-1]]
        acc_ref = list(prob_ref[1][::-1])
        acc_alt = list(prob_alt[1][::-1])
        don_ref = list(prob_ref[2][::-1])
        don_alt = list(prob_alt[2][::-1])
        snv_display = int(gene_length - 1 - snv_pos)
        arrow_direction = "left"
        x_label = "genomic-forward local coordinate (0-based within gene span)"
    else:
        x = x_gene0
        acc_ref = prob_ref[1]
        acc_alt = prob_alt[1]
        don_ref = prob_ref[2]
        don_alt = prob_alt[2]
        snv_display = snv_pos
        arrow_direction = "right"
        x_label = "gene0 coordinate (transcript 5'→3', 0-based)"

    fig = plt.figure(figsize=(14, 9))
    gs = fig.add_gridspec(3, 1, height_ratios=[0.9, 1.2, 1.2], hspace=0.42)

    ax_top = fig.add_subplot(gs[0])
    ax_acc = fig.add_subplot(gs[1], sharex=ax_top)
    ax_don = fig.add_subplot(gs[2], sharex=ax_top)

    _draw_transcript_track(ax_top, x[0], x[-1], arrow_direction=arrow_direction)
    _draw_exons(ax_top, regions, strand=strand, gene_length=gene_length, display_mode=display_mode)
    ax_top.set_ylim(0.25, 0.7)
    ax_top.set_yticks([])
    ax_top.set_ylabel("Exons")
    ax_top.grid(False)

    _plot_overlap_spikes(ax_acc, x, acc_ref, acc_alt, label_ref="Ref", label_alt="Alt")
    ax_acc.axvline(snv_display, linestyle="--", linewidth=1.2, color="black", alpha=0.7)
    ax_acc.set_ylim(0, 1.0)
    ax_acc.set_ylabel("P(acceptor)")
    ax_acc.legend(loc="upper right")

    _plot_overlap_spikes(ax_don, x, don_ref, don_alt, label_ref="Ref", label_alt="Alt")
    ax_don.axvline(snv_display, linestyle="--", linewidth=1.2, color="black", alpha=0.7)
    ax_don.set_ylim(0, 1.0)
    ax_don.set_ylabel("P(donor)")
    ax_don.set_xlabel(x_label)
    ax_don.legend(loc="upper right")

    if title:
        fig.suptitle(title, fontsize=13)
    if subtitle:
        fig.text(0.08, 0.66, subtitle, fontsize=11)
    mode_caption = "transcript view" if display_mode == "transcript" else "genomic-forward view"
    fig.text(0.08, 0.64, f"display={mode_caption} | strand={strand}", fontsize=9)

    return fig


# -------------------------
# STEP4 helpers
# -------------------------

def _format_structure_input(file_format: str) -> str:
    ff = (file_format or "").strip().lower()
    if ff in {"cif", "mmcif"}:
        return "cif"
    if ff in {"pdb", "ent"}:
        return "pdb"
    return ff or "cif"


def _render_structure_viewer(structure_text: str, *, file_format: str, viewer_id: str, height: int = 520):
    model_text = json.dumps(structure_text)
    fmt = json.dumps(_format_structure_input(file_format))
    html_code = f"""
    <div id="{viewer_id}" style="width:100%;height:{height}px;position:relative;border:1px solid #ddd;border-radius:8px;"></div>
    <script src="https://3Dmol.org/build/3Dmol-min.js"></script>
    <script>
      const target = document.getElementById({json.dumps(viewer_id)});
      target.innerHTML = "";
      let viewer = $3Dmol.createViewer(target, {{ backgroundColor: 'white' }});
      viewer.addModel({model_text}, {fmt});
      viewer.setStyle({{}}, {{ cartoon: {{ color: 'spectrum' }} }});
      viewer.zoomTo();
      viewer.render();
    </script>
    """
    components.html(html_code, height=height + 10)


def _structure_asset_label(asset: Dict[str, Any]) -> str:
    source = asset.get("source_id") or asset.get("path") or asset.get("structure_asset_id") or "asset"
    kind = asset.get("structure_kind") or asset.get("kind") or "structure"
    chain = asset.get("source_chain_id")
    suffix = f" | chain {chain}" if chain else ""
    status = asset.get("validation_status") or asset.get("provider") or ""
    return f"{source} | {kind}{suffix} | {status}"


def _choose_asset_from_state(normal_track: Dict[str, Any], job: Optional[Dict[str, Any]], *, key_prefix: str) -> Optional[Dict[str, Any]]:
    asset_rows: List[Dict[str, Any]] = []
    if job and isinstance(job, dict):
        asset_rows = [a for a in (job.get("assets") or []) if isinstance(a, dict) and str(a.get("kind")) == "structure"]
    else:
        asset_rows = [a for a in (normal_track.get("structures") or []) if isinstance(a, dict)]
    if not asset_rows:
        return None
    labels = [_structure_asset_label(a) for a in asset_rows]
    idx = st.selectbox("Pick structure asset", options=list(range(len(labels))), format_func=lambda i: labels[i], key=f"asset_select_{key_prefix}")
    return asset_rows[int(idx)]


def _display_structure_asset(asset: Dict[str, Any], *, title: str, key_prefix: str):
    st.markdown(f"**{title}**")
    st.json(asset, expanded=False)
    signed_url = asset.get("signed_url")
    if not signed_url:
        st.info("No signed_url on this structure asset.")
        return
    try:
        structure_text = http_get_text(str(signed_url), timeout=120)
        _render_structure_viewer(structure_text, file_format=str(asset.get("file_format") or "cif"), viewer_id=f"viewer_{key_prefix}")
        st.caption(f"Loaded structure text from signed URL. format={asset.get('file_format')}")
    except Exception as e:
        st.error(f"Structure fetch/render error: {e}")


def _summary_badges(step4_state: Dict[str, Any]):
    normal_track = step4_state.get("normal_track") or {}
    user_track = step4_state.get("user_track") or {}
    predicted = user_track.get("predicted_transcript") or {}
    sanity = user_track.get("translation_sanity") or {}
    cmp = user_track.get("comparison_to_normal") or {}

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("STEP4 event", str(predicted.get("primary_event_type") or "-"))
    col2.metric("Translation OK", "yes" if sanity.get("translation_ok") else "no")
    col3.metric("Protein same as normal", "yes" if cmp.get("same_as_normal") else "no")
    col4.metric("Normal structures", len(normal_track.get("structures") or []))


def _find_job_to_display(step4_state: Dict[str, Any], job_override: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if job_override:
        return job_override
    user_track = step4_state.get("user_track") or {}
    latest = user_track.get("latest_structure_job")
    if isinstance(latest, dict) and latest:
        return latest
    jobs = user_track.get("structure_jobs") or []
    if jobs and isinstance(jobs[0], dict):
        return jobs[0]
    return None


# -------------------------
# Streamlit UI
# -------------------------

st.set_page_config(page_title="splice-playground dev GUI", layout="wide")
st.title("splice-playground dev GUI (STEP1 → STEP4)")

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
    include_parent_chain = st.checkbox("include_parent_chain", value=True)
    strict_ref_check = st.checkbox("strict_ref_check", value=True)
    return_target_sequence = st.checkbox("return_target_sequence", value=False)
    splicing_display_mode = st.selectbox(
        "STEP3 plot display mode",
        options=["transcript", "genomic_forward"],
        index=0,
        help="transcript: gene0 left→right = transcript 5'→3'. genomic_forward: flip minus-strand genes into genomic-forward display.",
    )

    st.divider()
    st.header("STEP4 options")
    step4_include_sequences = st.checkbox("STEP4 include sequences", value=True)
    step4_force = st.checkbox("STEP4 force new job", value=False)
    step4_reuse_if_identical = st.checkbox("STEP4 reuse baseline if identical", value=True)

    st.divider()
    st.caption("Tip: For deployed EC2 API + GPU worker testing, fetch STEP4 state, queue a job, then refresh until the job succeeds.")


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
                st.info("No image_url in response.")

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
                "include_parent_chain": bool(include_parent_chain),
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

    delta_summary = resp.get("delta_summary") or {}
    warnings = resp.get("warnings") or []
    state_lineage = resp.get("state_lineage") or []
    effective_edits = resp.get("effective_edits") or []
    frontend_summary = resp.get("frontend_summary") or {}
    interpreted_events = resp.get("interpreted_events") or []
    canonical_sites = resp.get("canonical_sites") or []
    novel_sites = resp.get("novel_sites") or []
    logic_thresholds = resp.get("logic_thresholds") or {}

    meta_col1, meta_col2 = st.columns(2)
    with meta_col1:
        if frontend_summary:
            st.markdown("**Frontend summary**")
            st.success(frontend_summary.get("headline") or "")
            st.caption(
                f"primary={frontend_summary.get('primary_event_type')} / "
                f"subtype={frontend_summary.get('primary_subtype')} / "
                f"confidence={frontend_summary.get('confidence')}"
            )
        if interpreted_events:
            st.markdown("**Interpreted events**")
            st.json(interpreted_events, expanded=False)
        if delta_summary:
            st.markdown("**Delta summary**")
            st.json(delta_summary, expanded=False)
        if warnings:
            st.markdown("**Warnings**")
            for w in warnings:
                st.warning(w)
    with meta_col2:
        if state_lineage:
            st.markdown("**State lineage**")
            st.write(" → ".join(state_lineage))
        if effective_edits:
            st.markdown("**Effective edits**")
            st.json(effective_edits, expanded=False)
        if logic_thresholds:
            st.markdown("**Logic thresholds**")
            st.json(logic_thresholds, expanded=False)
        if canonical_sites:
            st.markdown("**Canonical sites**")
            st.json(canonical_sites, expanded=False)
        if novel_sites:
            st.markdown("**Novel sites**")
            st.json(novel_sites, expanded=False)

    try:
        disease_name = None
        step2p = st.session_state.get("step2_payload") or {}
        gene_length = None
        if isinstance(step2p, dict):
            disease_name = ((step2p.get("disease") or {}).get("disease_name")) or None
            strand = ((step2p.get("gene") or {}).get("strand")) or resp.get("gene_strand") or "+"
            gene_length = ((step2p.get("gene") or {}).get("length")) or resp.get("gene_length") or None
        else:
            strand = resp.get("gene_strand") or "+"
            gene_length = resp.get("gene_length") or None
        title = f'{resp.get("gene_id")} | {resp.get("disease_id")} | {resp.get("model_version")} | radius={resp.get("region_radius")} flank={resp.get("flank")}'
        fig = plot_splicing_payload(
            resp,
            title=title,
            subtitle=disease_name,
            strand=strand,
            gene_length=int(gene_length) if gene_length is not None else None,
            display_mode=str(splicing_display_mode),
        )
        st.pyplot(fig, clear_figure=True)
    except Exception as e:
        st.error(f"Plot error: {e}")

st.divider()

# STEP4: two-track view + job testing
st.subheader("STEP4 - Two-track protein / structure")
if not state_id:
    st.info("Create a state first, then fetch STEP4.")
else:
    step4_col1, step4_col2, step4_col3 = st.columns([1, 1, 1])
    with step4_col1:
        if st.button("Fetch STEP4 state"):
            try:
                step4 = http_get_json(api(f"/states/{urllib.parse.quote(state_id)}/step4?include_sequences={'true' if step4_include_sequences else 'false'}"), timeout=60)
                st.session_state["step4_state"] = step4
            except Exception as e:
                st.error(str(e))
    with step4_col2:
        if st.button("Create / reuse STEP4 job"):
            try:
                body = {
                    "provider": "colabfold",
                    "force": bool(step4_force),
                    "reuse_if_identical": bool(step4_reuse_if_identical),
                }
                created = http_post_json(api(f"/states/{urllib.parse.quote(state_id)}/step4/jobs"), body, timeout=60)
                st.session_state["step4_job_create"] = created
                job = created.get("job") or {}
                if isinstance(job, dict) and job.get("job_id"):
                    st.session_state["step4_job_id"] = job.get("job_id")
                if created.get("created"):
                    st.success(created.get("message") or "STEP4 job request sent.")
                else:
                    st.info(created.get("message") or "STEP4 job creation is currently disabled.")
            except Exception as e:
                st.error(str(e))
    with step4_col3:
        if st.button("Refresh latest STEP4 job"):
            try:
                job_id = st.session_state.get("step4_job_id")
                if not job_id:
                    current_state = st.session_state.get("step4_state") or {}
                    latest_job = ((current_state.get("user_track") or {}).get("latest_structure_job") or {})
                    job_id = latest_job.get("job_id")
                if not job_id:
                    raise RuntimeError("No STEP4 job_id in session. Create a STEP4 job first.")
                latest = http_get_json(api(f"/step4-jobs/{urllib.parse.quote(str(job_id))}"), timeout=60)
                st.session_state["step4_latest_job"] = latest
                st.session_state["step4_job_id"] = latest.get("job_id")
                st.success(f"Refreshed job {latest.get('job_id')} status={latest.get('status')}")
            except Exception as e:
                st.error(str(e))

step4_state = st.session_state.get("step4_state")
if isinstance(step4_state, dict) and step4_state:
    st.json(step4_state, expanded=False)
    _summary_badges(step4_state)

    normal_track = step4_state.get("normal_track") or {}
    user_track = step4_state.get("user_track") or {}
    predicted = user_track.get("predicted_transcript") or {}
    sanity = user_track.get("translation_sanity") or {}
    cmp = user_track.get("comparison_to_normal") or {}

    left, right = st.columns(2)

    with left:
        st.markdown("### Normal track")
        baseline = normal_track.get("baseline_protein") or {}
        st.write({
            "gene_id": step4_state.get("gene_id"),
            "protein_length": baseline.get("protein_length"),
            "transcript_id": baseline.get("transcript_id"),
            "uniprot_accession": baseline.get("uniprot_accession"),
            "validation_status": baseline.get("validation_status"),
            "default_structure_asset_id": normal_track.get("default_structure_asset_id"),
        })
        with st.expander("Normal track JSON", expanded=False):
            st.json(normal_track, expanded=False)
        normal_asset = _choose_asset_from_state(normal_track, None, key_prefix="normal")
        if normal_asset:
            _display_structure_asset(normal_asset, title="Normal structure viewer", key_prefix="normal")

    with right:
        st.markdown("### User track")
        st.write({
            "primary_event_type": predicted.get("primary_event_type"),
            "primary_subtype": predicted.get("primary_subtype"),
            "included_exon_numbers": predicted.get("included_exon_numbers"),
            "excluded_exon_numbers": predicted.get("excluded_exon_numbers"),
            "translation_ok": sanity.get("translation_ok"),
            "same_as_normal": cmp.get("same_as_normal"),
            "recommended_structure_strategy": user_track.get("recommended_structure_strategy"),
            "can_reuse_normal_structure": user_track.get("can_reuse_normal_structure"),
            "structure_prediction_enabled": user_track.get("structure_prediction_enabled"),
        })
        if user_track.get("structure_prediction_message"):
            st.info(str(user_track.get("structure_prediction_message")))
        with st.expander("User track JSON", expanded=False):
            st.json(user_track, expanded=False)
        latest_job = _find_job_to_display(step4_state, st.session_state.get("step4_latest_job"))
        if latest_job:
            st.markdown("**Latest STEP4 job**")
            st.json(latest_job, expanded=False)
            user_asset = _choose_asset_from_state(normal_track, latest_job, key_prefix="user")
            if user_asset:
                _display_structure_asset(user_asset, title="User structure viewer", key_prefix="user")
        else:
            if user_track.get("structure_prediction_enabled"):
                st.info("No STEP4 structure job yet. Create one to render user structure.")
            else:
                st.info("STEP4 user-structure prediction is disabled on this backend. Use the normal structure viewer for now.")

    lower_left, lower_right = st.columns(2)
    with lower_left:
        st.markdown("### Translation sanity")
        st.json(sanity, expanded=False)
        seqs = {
            "cdna_seq": user_track.get("cdna_seq"),
            "cds_seq": user_track.get("cds_seq"),
            "protein_seq": user_track.get("protein_seq"),
        }
        with st.expander("User sequences", expanded=False):
            st.json(seqs, expanded=False)
    with lower_right:
        st.markdown("### User vs normal protein")
        st.json(cmp, expanded=False)
        job_data = _find_job_to_display(step4_state, st.session_state.get("step4_latest_job"))
        if job_data and job_data.get("structure_comparison"):
            st.markdown("### Structure comparison")
            st.json(job_data.get("structure_comparison"), expanded=False)
        if job_data and job_data.get("confidence"):
            st.markdown("### ColabFold confidence")
            st.json(job_data.get("confidence"), expanded=False)

job_create_resp = st.session_state.get("step4_job_create")
if isinstance(job_create_resp, dict) and job_create_resp:
    st.divider()
    st.subheader("Latest STEP4 job creation response")
    st.json(job_create_resp, expanded=False)
