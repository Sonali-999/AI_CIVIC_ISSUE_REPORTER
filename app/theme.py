"""
theme.py
--------
The whole visual layer of the CivicAI portal: design tokens, the Gradio theme
object, and the stylesheet that turns Gradio's default form-stack into
something that reads as a product rather than a demo.

HOW THIS IS ORGANISED
=====================
Everything is driven by the custom properties on :root. Colour, spacing,
radius, elevation and motion each have one scale, and every rule below spends
those tokens instead of inventing values - which is why the dark theme is
twenty lines at the bottom rather than a second stylesheet.

Gradio injects its own CSS after ours, so component overrides need !important.
Layout and anything on our own markup does not, and does without.
"""

import gradio as gr

# ════════════════════════════════════════════════════════════════════════════
# GRADIO THEME
# ════════════════════════════════════════════════════════════════════════════
# Gradio builds its components from these before our CSS ever runs. Getting the
# radius, font and neutral ramp right here means far fewer overrides later, and
# components we never explicitly style still look like they belong.

APP_THEME = gr.themes.Soft(
    primary_hue=gr.themes.colors.teal,
    secondary_hue=gr.themes.colors.blue,
    neutral_hue=gr.themes.colors.slate,
    radius_size=gr.themes.sizes.radius_lg,
    text_size=gr.themes.sizes.text_md,
    spacing_size=gr.themes.sizes.spacing_md,
    font=(gr.themes.GoogleFont("Inter"), "ui-sans-serif", "system-ui", "sans-serif"),
    font_mono=(gr.themes.GoogleFont("JetBrains Mono"), "ui-monospace", "monospace"),
).set(
    body_background_fill="*neutral_50",
    block_background_fill="white",
    block_border_width="1px",
    block_shadow="none",
    button_large_radius="10px",
    button_small_radius="8px",
    input_radius="10px",
)


CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Sora:wght@500;600;700;800&display=swap');

/* ════════════════════════════════════════════════════════════════════════
   1. DESIGN TOKENS
   ════════════════════════════════════════════════════════════════════════ */
:root {
    /* brand */
    --navy:    #0B1F3A;
    --navy-2:  #142E52;
    --blue:    #1B4F8F;
    --sky:     #2E9BE0;
    --teal:    #0E9382;
    --teal-2:  #14B8A6;
    --teal-ink:#0A6B60;

    /* surfaces */
    --bg:        #F4F7FB;
    --bg-2:      #EDF2F8;
    --surface:   #FFFFFF;
    --surface-2: #FAFCFE;
    --border:    #E3EAF2;
    --border-2:  #D2DDEA;

    /* text */
    --text:   #101828;
    --text-2: #344054;
    --muted:  #667085;
    --faint:  #98A2B3;
    --on-dark:      rgba(255,255,255,0.96);
    --on-dark-soft: rgba(255,255,255,0.62);

    /* status */
    --ok:     #12B76A;
    --ok-bg:  rgba(18,183,106,0.10);
    --warn:   #F79009;
    --warn-bg:rgba(247,144,9,0.10);
    --danger: #F04438;
    --danger-bg: rgba(240,68,56,0.10);
    --info:   #2E9BE0;
    --info-bg:rgba(46,155,224,0.10);

    /* spacing — 4px grid */
    --s1: 4px;  --s2: 8px;  --s3: 12px; --s4: 16px;
    --s5: 20px; --s6: 24px; --s8: 32px; --s10: 40px;

    /* shape */
    --r-sm: 8px; --r-md: 12px; --r-lg: 16px; --r-xl: 22px; --r-pill: 999px;

    /* elevation — tinted with the brand navy, never neutral black */
    --e1: 0 1px 2px rgba(16,24,40,0.05);
    --e2: 0 2px 8px rgba(11,31,58,0.06), 0 1px 2px rgba(11,31,58,0.04);
    --e3: 0 8px 24px rgba(11,31,58,0.09), 0 2px 6px rgba(11,31,58,0.05);
    --e4: 0 18px 44px rgba(11,31,58,0.14), 0 4px 12px rgba(11,31,58,0.07);
    --ring: 0 0 0 3px rgba(14,147,130,0.18);

    /* motion */
    --fast: 120ms cubic-bezier(0.4,0,0.2,1);
    --base: 200ms cubic-bezier(0.4,0,0.2,1);
    --slow: 320ms cubic-bezier(0.16,1,0.3,1);

    --shell: 1320px;         /* max content width */
}

*, *::before, *::after { box-sizing: border-box; }

/* ════════════════════════════════════════════════════════════════════════
   2. APP SHELL
   ════════════════════════════════════════════════════════════════════════ */
body, .gradio-container {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    background: var(--bg) !important;
    color: var(--text) !important;
    margin: 0 !important;
    padding: 0 !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
.gradio-container {
    max-width: 100% !important;
    padding: 0 !important;
    min-height: 100vh;
}
footer, .built-with, .show-api { display: none !important; }

/* A soft brand wash behind the whole page. Without it the shell reads as a
   white document; with it, as an application chrome. */
body::before {
    content: '';
    position: fixed; inset: 0;
    background:
        radial-gradient(900px 480px at 8% -8%,  rgba(46,155,224,0.10), transparent 60%),
        radial-gradient(760px 420px at 96% 4%, rgba(14,147,130,0.10), transparent 62%);
    pointer-events: none;
    z-index: 0;
}
.gradio-container > * { position: relative; z-index: 1; }

/* Constrain the content column without constraining full-bleed bars. */
.tabs > .tabitem, .tabitem, #component-0 > .gap > .tabitem {
    max-width: var(--shell);
    margin: 0 auto !important;
    padding: var(--s6) var(--s6) var(--s10) !important;
}

/* ════════════════════════════════════════════════════════════════════════
   3. TOP BAR
   ════════════════════════════════════════════════════════════════════════ */
#civicai-header {
    background: linear-gradient(120deg, var(--navy) 0%, var(--navy-2) 52%, var(--blue) 100%) !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: var(--e3) !important;
    padding: 0 !important;
    margin: 0 !important;
    position: sticky; top: 0; z-index: 60;
}
/* A thin brand rule along the bottom edge — the detail that reads "product". */
#civicai-header::after {
    content: '';
    position: absolute; left: 0; right: 0; bottom: 0; height: 2px;
    background: linear-gradient(90deg, var(--teal), var(--sky), var(--teal-2));
    opacity: 0.85;
}
#civicai-header-inner {
    display: flex; align-items: center; justify-content: space-between;
    gap: var(--s4);
    padding: var(--s3) var(--s6);
    max-width: var(--shell); margin: 0 auto;
}
.hdr-logo { display: flex; align-items: center; gap: var(--s3); min-width: 0; }
.hdr-logo-icon {
    width: 38px; height: 38px; flex: none;
    background: linear-gradient(135deg, var(--teal), var(--teal-2));
    border-radius: 11px;
    display: flex; align-items: center; justify-content: center;
    font-size: 19px;
    box-shadow: 0 4px 12px rgba(14,147,130,0.42);
}
.hdr-logo-name {
    font-family: 'Sora', sans-serif;
    font-size: 17px; font-weight: 700; letter-spacing: -0.3px;
    color: var(--on-dark); line-height: 1.2;
}
.hdr-logo-sub {
    font-size: 11px; font-weight: 500; letter-spacing: 0.2px;
    color: var(--on-dark-soft); margin-top: 1px;
}
.hdr-right { display: flex; align-items: center; gap: var(--s3); }
.hdr-chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 5px 11px;
    background: rgba(255,255,255,0.10);
    border: 1px solid rgba(255,255,255,0.16);
    border-radius: var(--r-pill);
    color: var(--on-dark-soft);
    font-size: 11px; font-weight: 600; letter-spacing: 0.2px;
    white-space: nowrap;
}
.hdr-chip .dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: var(--teal-2);
    box-shadow: 0 0 0 3px rgba(20,184,166,0.22);
    animation: pulse 2.4s ease-in-out infinite;
}
.hdr-user {
    display: flex; align-items: center; gap: var(--s2);
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.18);
    border-radius: var(--r-pill);
    padding: 4px 14px 4px 4px;
    color: var(--on-dark);
    font-size: 12px; font-weight: 600;
    transition: background var(--fast);
}
.hdr-user:hover { background: rgba(255,255,255,0.18); }
.hdr-user-meta { display: flex; flex-direction: column; line-height: 1.25; }
.hdr-user-mail { font-size: 12px; font-weight: 600; color: var(--on-dark); }
.hdr-user-role { font-size: 10px; font-weight: 600; letter-spacing: 0.4px;
                 text-transform: uppercase; color: var(--on-dark-soft); }
.hdr-avatar {
    width: 28px; height: 28px; flex: none; border-radius: 50%;
    background: linear-gradient(135deg, var(--teal), var(--sky));
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: #fff;
    box-shadow: inset 0 0 0 1.5px rgba(255,255,255,0.28);
}

@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }

/* ════════════════════════════════════════════════════════════════════════
   4. TAB BAR — a segmented control, not a row of links
   ════════════════════════════════════════════════════════════════════════
   Gradio renamed this element from .tab-nav to .tab-container between v4 and
   v6, so both are matched: the styling then survives whichever version the
   environment happens to install. */
.tab-nav, .tab-container {
    display: flex !important;
    justify-content: center !important;
    gap: var(--s1) !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: var(--s5) var(--s6) 0 !important;
    margin: 0 !important;
}
.tab-nav button, .tab-container button {
    position: relative;
    background: transparent !important;
    border: 1px solid transparent !important;
    border-radius: var(--r-pill) !important;
    padding: 9px 20px !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 13.5px !important;
    font-weight: 600 !important;
    color: var(--muted) !important;
    transition: all var(--base) !important;
}
.tab-nav button:hover, .tab-container button:hover {
    color: var(--text-2) !important;
    background: rgba(11,31,58,0.045) !important;
}
.tab-nav button.selected, .tab-container button.selected {
    background: var(--surface) !important;
    color: var(--teal-ink) !important;
    border-color: var(--border) !important;
    box-shadow: var(--e2) !important;
}
.tab-nav button:focus-visible, .tab-container button:focus-visible { outline: none !important; box-shadow: var(--ring) !important; }

/* ════════════════════════════════════════════════════════════════════════
   5. GRADIO PRIMITIVES
   ════════════════════════════════════════════════════════════════════════ */
.block, .form, .panel, .gr-box, .gr-group {
    border-color: var(--border) !important;
    background: transparent !important;
    box-shadow: none !important;
}

/* Inputs */
input[type="text"], input[type="password"], input[type="number"],
input[type="email"], textarea, select, .gr-text-input {
    background: var(--surface) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    color: var(--text) !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    padding: 10px 13px !important;
    transition: border-color var(--fast), box-shadow var(--fast), background var(--fast) !important;
}
input:hover:not(:focus), textarea:hover:not(:focus) { border-color: var(--border-2) !important; }
input:focus, textarea:focus, select:focus {
    border-color: var(--teal) !important;
    box-shadow: var(--ring) !important;
    outline: none !important;
}
input::placeholder, textarea::placeholder { color: var(--faint) !important; }

label, .gr-label, span[data-testid="block-info"] {
    font-size: 12.5px !important;
    font-weight: 600 !important;
    color: var(--text-2) !important;
    letter-spacing: 0.1px !important;
}

/* ── Buttons ─────────────────────────────────────────────────────────────
   One geometry, four intents. Lift on hover, settle on press: the press state
   is what makes a control feel physical rather than painted on. */
button.lg, button.sm, .gr-button {
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    border-radius: var(--r-sm) !important;
    transition: transform var(--fast), box-shadow var(--fast),
                background var(--fast), border-color var(--fast) !important;
}
.primary-btn button, .success-btn button, .secondary-btn button,
.signout-btn button, .update-btn button, .link-btn button {
    width: 100%;
    border-radius: var(--r-sm) !important;
    font-size: 13.5px !important;
    font-weight: 600 !important;
    padding: 11px 18px !important;
    letter-spacing: 0.1px !important;
    border: 1.5px solid transparent !important;
}
.primary-btn button {
    background: linear-gradient(135deg, var(--navy), var(--blue)) !important;
    color: #fff !important;
    box-shadow: 0 2px 8px rgba(11,31,58,0.24) !important;
}
.primary-btn button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 8px 20px rgba(11,31,58,0.30) !important;
}
.success-btn button {
    background: linear-gradient(135deg, var(--teal), var(--teal-2)) !important;
    color: #fff !important;
    box-shadow: 0 2px 8px rgba(14,147,130,0.30) !important;
    font-size: 14px !important;
    padding: 13px 20px !important;
}
.success-btn button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 10px 24px rgba(14,147,130,0.36) !important;
}
.secondary-btn button {
    background: var(--surface) !important;
    color: var(--text-2) !important;
    border-color: var(--border-2) !important;
    box-shadow: var(--e1) !important;
}
.secondary-btn button:hover {
    background: var(--surface-2) !important;
    border-color: var(--teal) !important;
    color: var(--teal-ink) !important;
    transform: translateY(-1px) !important;
}
.signout-btn button {
    background: var(--surface) !important;
    color: var(--danger) !important;
    border-color: rgba(240,68,56,0.28) !important;
    max-width: 180px;
}
.signout-btn button:hover {
    background: var(--danger-bg) !important;
    border-color: var(--danger) !important;
}
.update-btn button {
    background: linear-gradient(135deg, var(--teal), var(--teal-2)) !important;
    color: #fff !important;
    font-size: 13px !important;
    box-shadow: 0 2px 8px rgba(14,147,130,0.28) !important;
}
.update-btn button:hover { transform: translateY(-1px) !important; }
.link-btn button {
    background: transparent !important;
    color: var(--teal-ink) !important;
    box-shadow: none !important;
}
button:active { transform: translateY(0) scale(0.99) !important; }
button:focus-visible { box-shadow: var(--ring) !important; outline: none !important; }

/* Upload + image widgets */
[data-testid="image"], .image-container, .image-display-card {
    border-radius: var(--r-md) !important;
    border: 1.5px dashed var(--border-2) !important;
    background: var(--surface-2) !important;
    transition: border-color var(--base), background var(--base) !important;
}
[data-testid="image"]:hover { border-color: var(--teal) !important; background: rgba(14,147,130,0.03) !important; }
.image-display-card { border-style: solid !important; overflow: hidden; }

/* ════════════════════════════════════════════════════════════════════════
   6. AUTH SCREEN
   ════════════════════════════════════════════════════════════════════════ */
.auth-wrapper {
    display: flex; align-items: center; justify-content: center;
    min-height: calc(100vh - 220px);
    padding: var(--s8) var(--s4);
}
.auth-card {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--r-xl) !important;
    box-shadow: var(--e4) !important;
    padding: var(--s8) !important;
    max-width: 452px !important;
    margin: var(--s8) auto var(--s10) !important;
    animation: rise var(--slow) both;
}
.auth-brand { text-align: center; margin-bottom: var(--s6); }
.auth-mark {
    width: 58px; height: 58px; margin: 0 auto var(--s4);
    border-radius: 18px;
    background: linear-gradient(135deg, var(--navy), var(--teal));
    display: flex; align-items: center; justify-content: center;
    font-size: 27px;
    box-shadow: 0 10px 26px rgba(11,31,58,0.28);
}
.auth-title {
    font-family: 'Sora', sans-serif;
    font-size: 23px; font-weight: 700; letter-spacing: -0.5px;
    color: var(--text);
}
.auth-sub { font-size: 13.5px; color: var(--muted); margin-top: 5px; }

/* Role selector — two big, obviously-clickable cards */
.role-selector { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s3); margin: var(--s2) 0 var(--s5); }
.role-btn {
    display: flex !important; flex-direction: column; align-items: center; gap: 6px;
    padding: var(--s4) var(--s3) !important;
    background: var(--surface-2) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: var(--r-md) !important;
    color: var(--muted) !important;
    font-size: 13px !important; font-weight: 600 !important;
    cursor: pointer;
    transition: all var(--base) !important;
}
.role-btn:hover { border-color: var(--border-2) !important; transform: translateY(-1px) !important; }
.role-icon { font-size: 21px; line-height: 1; }
.role-btn.active-citizen {
    background: rgba(14,147,130,0.08) !important;
    border-color: var(--teal) !important;
    color: var(--teal-ink) !important;
    box-shadow: var(--ring) !important;
}
.role-btn.active-admin {
    background: rgba(27,79,143,0.08) !important;
    border-color: var(--blue) !important;
    color: var(--blue) !important;
    box-shadow: 0 0 0 3px rgba(27,79,143,0.16) !important;
}
.auth-divider {
    display: flex; align-items: center; gap: var(--s3);
    margin: var(--s5) 0;
    font-size: 11.5px; font-weight: 600; letter-spacing: 0.6px;
    text-transform: uppercase; color: var(--faint);
}
.auth-divider::before, .auth-divider::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
}
.forgot-link { text-align: right; margin: -4px 0 var(--s2); }
.forgot-link a {
    font-size: 12.5px; font-weight: 600; color: var(--teal-ink);
    text-decoration: none; transition: color var(--fast);
}
.forgot-link a:hover { color: var(--teal); text-decoration: underline; }
.auth-foot { text-align: center; font-size: 12.5px; color: var(--muted); margin-bottom: var(--s2); }

/* ════════════════════════════════════════════════════════════════════════
   7. KPI TILES
   ════════════════════════════════════════════════════════════════════════ */
.stat-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: var(--s4);
    margin-bottom: var(--s6);
}
/* White tiles with a coloured accent rail. Four saturated gradient blocks
   compete with the data; a rail identifies the metric without shouting. */
.stat-card {
    position: relative; overflow: hidden;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--e2);
    padding: var(--s5) var(--s5) var(--s5) var(--s6);
    transition: transform var(--base), box-shadow var(--base);
}
.stat-card::before {
    content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
    background: var(--accent, var(--teal));
}
.stat-card:hover { transform: translateY(-2px); box-shadow: var(--e3); }
.stat-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s2); }
.stat-lbl {
    font-size: 11px; font-weight: 700; letter-spacing: 0.7px;
    text-transform: uppercase; color: var(--muted);
}
.stat-ico {
    width: 30px; height: 30px; flex: none; border-radius: var(--r-sm);
    display: flex; align-items: center; justify-content: center;
    font-size: 15px;
    background: var(--accent-bg, var(--teal-bg, rgba(14,147,130,0.10)));
}
.stat-val {
    font-family: 'Sora', sans-serif;
    font-size: 32px; font-weight: 700; line-height: 1.1;
    letter-spacing: -1px; color: var(--text);
    margin-top: var(--s3);
    font-variant-numeric: tabular-nums;
}
.stat-foot { font-size: 12px; color: var(--faint); margin-top: 5px; }

/* ════════════════════════════════════════════════════════════════════════
   8. CARDS & CONTENT
   ════════════════════════════════════════════════════════════════════════ */
.section-title {
    display: flex; align-items: center; gap: var(--s2);
    font-family: 'Sora', sans-serif;
    font-size: 15px; font-weight: 700; letter-spacing: -0.2px;
    color: var(--text);
    margin: var(--s6) 0 var(--s3);
}
.section-title::after {
    content: ''; flex: 1; height: 1px; background: var(--border);
}
.section-sub { font-size: 12.5px; color: var(--muted); margin: -6px 0 var(--s4); }

.panel-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--e2);
    padding: var(--s5);
}

.complaint-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--e3);
    overflow: hidden;
    animation: rise var(--slow) both;
}
.complaint-card-header {
    background: linear-gradient(120deg, var(--navy), var(--blue));
    color: #fff;
    padding: var(--s4) var(--s5);
    font-size: 13.5px; font-weight: 700; letter-spacing: 0.1px;
    display: flex; align-items: center; gap: var(--s2);
}
.complaint-card-body { padding: var(--s5); }

.info-badge {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-md);
    padding: var(--s3) var(--s4);
    margin-bottom: var(--s3);
}
.info-badge-label {
    font-size: 10.5px; font-weight: 700; letter-spacing: 0.6px;
    text-transform: uppercase; color: var(--muted);
}
.info-badge-value {
    font-size: 14px; font-weight: 600; color: var(--text);
    margin-top: 3px; line-height: 1.45;
}
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s3); }

/* Admin complaint rows */
.dept-header {
    display: flex; align-items: center; gap: var(--s2);
    margin: var(--s8) 0 var(--s4);
    padding: var(--s3) var(--s4);
    background: linear-gradient(120deg, var(--navy), var(--navy-2));
    border-radius: var(--r-md);
    color: var(--on-dark);
    font-family: 'Sora', sans-serif;
    font-size: 12.5px; font-weight: 700; letter-spacing: 0.8px;
    box-shadow: var(--e2);
}
.admin-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 3px solid var(--status, var(--border-2));
    border-radius: var(--r-md);
    box-shadow: var(--e1);
    padding: var(--s5);
    margin-bottom: var(--s3);
    transition: transform var(--base), box-shadow var(--base), border-color var(--base);
}
.admin-card:hover { transform: translateY(-1px); box-shadow: var(--e3); }
.admin-meta-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
    gap: var(--s2);
    margin-top: var(--s3);
}
.admin-meta-box {
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: var(--r-sm);
    padding: var(--s2) var(--s3);
}
.admin-meta-lbl {
    font-size: 9.5px; font-weight: 700; letter-spacing: 0.6px;
    text-transform: uppercase; color: var(--faint);
}
.admin-meta-val {
    font-size: 12.5px; font-weight: 600; color: var(--text); margin-top: 2px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mono { font-family: 'JetBrains Mono', ui-monospace, monospace; }

/* Pills */
.pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 4px 11px;
    border-radius: var(--r-pill);
    font-size: 11.5px; font-weight: 600; white-space: nowrap;
    border: 1px solid transparent;
}
.pill .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pill-ok     { background: var(--ok-bg);     color: #067647; border-color: rgba(18,183,106,0.24); }
.pill-warn   { background: var(--warn-bg);   color: #B54708; border-color: rgba(247,144,9,0.24); }
.pill-danger { background: var(--danger-bg); color: #B42318; border-color: rgba(240,68,56,0.24); }
.pill-info   { background: var(--info-bg);   color: #175CD3; border-color: rgba(46,155,224,0.24); }
.pill-muted  { background: var(--bg-2);      color: var(--muted); border-color: var(--border); }

/* Empty states — a placeholder that explains itself beats a grey box */
.empty-state {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    text-align: center;
    padding: var(--s10) var(--s6);
    background: var(--surface);
    border: 1.5px dashed var(--border-2);
    border-radius: var(--r-lg);
    color: var(--muted);
}
.empty-ico {
    width: 52px; height: 52px; margin-bottom: var(--s3);
    border-radius: var(--r-md);
    background: var(--bg-2);
    display: flex; align-items: center; justify-content: center;
    font-size: 24px;
}
.empty-title { font-size: 14.5px; font-weight: 700; color: var(--text-2); }
.empty-body  { font-size: 13px; color: var(--muted); margin-top: 5px; max-width: 320px; line-height: 1.6; }

/* Status toasts */
.status-success, .status-error {
    display: flex; align-items: flex-start; gap: var(--s2);
    padding: var(--s3) var(--s4);
    border-radius: var(--r-md);
    font-size: 13.5px; font-weight: 600;
    border: 1px solid;
    animation: rise var(--base) both;
    margin-top: var(--s3);
}
.status-success { background: var(--ok-bg);     color: #067647; border-color: rgba(18,183,106,0.30); }
.status-error   { background: var(--danger-bg); color: #B42318; border-color: rgba(240,68,56,0.30); }

/* Confidence meter */
.conf-track {
    flex: 1; height: 7px; border-radius: var(--r-pill);
    background: var(--bg-2); overflow: hidden;
}
.conf-fill {
    height: 100%; border-radius: var(--r-pill);
    transition: width var(--slow);
}

/* ════════════════════════════════════════════════════════════════════════
   9. NOTIFICATIONS
   ════════════════════════════════════════════════════════════════════════ */
.notif-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--e4);
    overflow: hidden;
    animation: rise var(--base) both;
    margin-bottom: var(--s4);
}
.notif-panel-header {
    background: linear-gradient(120deg, var(--navy), var(--blue));
    color: #fff;
    padding: var(--s3) var(--s5);
    display: flex; justify-content: space-between; align-items: center;
    font-size: 13.5px; font-weight: 700;
}
.notif-item {
    display: flex; gap: var(--s3);
    padding: var(--s3) var(--s5);
    border-bottom: 1px solid var(--border);
    transition: background var(--fast);
}
.notif-item:last-child { border-bottom: none; }
.notif-item.unread { background: rgba(14,147,130,0.045); box-shadow: inset 3px 0 0 var(--teal); }
.notif-item:hover { background: var(--bg-2); }
.notif-item-title { font-size: 13px; font-weight: 700; color: var(--text); }
.notif-item-body  { font-size: 12.5px; color: var(--muted); margin-top: 3px; line-height: 1.5; }
.notif-item-time  { font-size: 11px; color: var(--faint); margin-top: 4px; }
.notif-empty { padding: var(--s10) var(--s6); text-align: center; color: var(--muted); font-size: 13.5px; }
.notif-bell-wrap { display: flex; justify-content: flex-end; align-items: center; gap: var(--s2); }
.badge-pill {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 19px; height: 19px; padding: 0 5px;
    background: var(--danger); color: #fff;
    border: 2px solid var(--surface);
    border-radius: var(--r-pill);
    font-size: 10.5px; font-weight: 700;
}

/* ════════════════════════════════════════════════════════════════════════
   10. ADMIN CONTROLS & GALLERY
   ════════════════════════════════════════════════════════════════════════ */
.status-select select {
    border: 1.5px solid var(--border) !important;
    border-radius: var(--r-sm) !important;
    padding: 9px 12px !important;
    font-size: 13px !important; font-weight: 600 !important;
    color: var(--text) !important;
    background: var(--surface) !important;
    cursor: pointer !important;
}
#admin-gallery, .fixed-gallery {
    border: 1px solid var(--border) !important;
    border-radius: var(--r-lg) !important;
    background: var(--surface) !important;
    box-shadow: var(--e2) !important;
    padding: var(--s3) !important;
}
#admin-gallery img, .fixed-gallery img {
    border-radius: var(--r-sm) !important;
    transition: transform var(--base) !important;
}
#admin-gallery button:hover img { transform: scale(1.03) !important; }

.toolbar {
    display: flex; align-items: center; justify-content: space-between;
    gap: var(--s4); flex-wrap: wrap;
    padding: var(--s4) var(--s5);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--r-lg);
    box-shadow: var(--e2);
    margin-bottom: var(--s4);
}
.toolbar-title {
    font-family: 'Sora', sans-serif;
    font-size: 17px; font-weight: 700; letter-spacing: -0.3px; color: var(--text);
}
.toolbar-sub { font-size: 12.5px; color: var(--muted); margin-top: 2px; }

/* ════════════════════════════════════════════════════════════════════════
   11. MOTION
   ════════════════════════════════════════════════════════════════════════ */
@keyframes rise {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: none; }
}
@keyframes fadeUp {   /* kept: older inline markup still references it */
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
    }
}

/* ════════════════════════════════════════════════════════════════════════
   12. RESPONSIVE
   ════════════════════════════════════════════════════════════════════════ */
@media (max-width: 860px) {
    .tabs > .tabitem, .tabitem { padding: var(--s4) var(--s4) var(--s8) !important; }
    #civicai-header-inner { padding: var(--s3) var(--s4); }
    .hdr-chip, .hdr-user-mail { display: none; }
    .tab-nav, .tab-container { padding: var(--s4) var(--s3) 0 !important; overflow-x: auto; justify-content: flex-start !important; }
    .tab-nav button, .tab-container button { padding: 8px 14px !important; font-size: 12.5px !important; white-space: nowrap; }
    .info-grid { grid-template-columns: 1fr; }
    .auth-card { padding: var(--s6) !important; margin: var(--s5) var(--s1) !important; }
    .stat-val { font-size: 27px; }
}

/* ════════════════════════════════════════════════════════════════════════
   13. DARK THEME
   ════════════════════════════════════════════════════════════════════════
   Only the surface and text tokens are redefined. The brand hues stay put -
   they are already dark-legible - and every rule above inherits the change. */
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
        --bg:        #0A0F16;
        --bg-2:      #131C27;
        --surface:   #111A24;
        --surface-2: #16212D;
        --border:    #1F2C3A;
        --border-2:  #2C3D4F;
        --text:      #E7EEF7;
        --text-2:    #C3D0DE;
        --muted:     #8FA1B5;
        --faint:     #6B7D91;
        --e1: 0 1px 2px rgba(0,0,0,0.42);
        --e2: 0 2px 8px rgba(0,0,0,0.46);
        --e3: 0 8px 24px rgba(0,0,0,0.52);
        --e4: 0 18px 44px rgba(0,0,0,0.60);
    }
    :root:not([data-theme="light"]) body::before {
        background:
            radial-gradient(900px 480px at 8% -8%,  rgba(46,155,224,0.13), transparent 60%),
            radial-gradient(760px 420px at 96% 4%, rgba(14,147,130,0.13), transparent 62%);
    }
    :root:not([data-theme="light"]) .pill-ok     { color: #6CE9A6; }
    :root:not([data-theme="light"]) .pill-warn   { color: #FEC84B; }
    :root:not([data-theme="light"]) .pill-danger { color: #FDA29B; }
    :root:not([data-theme="light"]) .pill-info   { color: #84CAFF; }
    :root:not([data-theme="light"]) .status-success { color: #6CE9A6; }
    :root:not([data-theme="light"]) .status-error   { color: #FDA29B; }
    :root:not([data-theme="light"]) .tab-nav button:hover,
    :root:not([data-theme="light"]) .tab-container button:hover { background: rgba(255,255,255,0.05) !important; }
    :root:not([data-theme="light"]) .tab-nav button.selected,
    :root:not([data-theme="light"]) .tab-container button.selected { color: var(--teal-2) !important; }
}
"""
