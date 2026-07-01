import requests
import json
import csv
import sys
import time
import zipfile
import io
import os
import re
import argparse
import warnings
import pandas as pd
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

SSL_VERIFY = False
IDMC_LOGIN_URL = "https://dm-us.informaticacloud.com"
LOGIN_WAIT_SECONDS = 180

SEARCH_TERMS = {
    "keywords": ["CDIR_CDS_CODE_COCE_DET","CDIR_CMC_ACPR_PYMT_RED","CDIR_CMC_BLCT_COMP_TOTL","CDIR_CMC_BPCD_CLM_DTL","CDIR_CMC_BPCL_CLM","CDIR_CMC_BPHM_CLM_DTL","CDIR_CMC_CDML_CL_LINE","CDIR_CMC_CDNP_NWX_PRCNG","CDIR_CMC_CKPY_PAYEE_SUM","CDIR_CMC_CLCK_CLM_CHECK","CDIR_CMC_CLCL_CLAIM","CDIR_CMC_CLHP_HOSP","CDIR_CMC_CLMF_MULT_FUNC","CDIR_CMC_CSCI_CONTACT","CDIR_CMC_GRGR_GROUP","CDIR_CMC_IPCD_PROC_CD","CDIR_CMC_LOBD_LINE_BUS","CDIR_CMC_MECM_COMM","CDIR_CMC_MEMD_MECR_DETL","CDIR_CMC_MEMI_MECR_INTF","CDIR_CMC_PDDS_PROD_DESC","CDIR_CMC_PRPR_PROV","CDIR_CMC_UMIN_INPATIENT","CDIR_CMC_UMSV_SERVICES","CDIR_NWX_NASA_ASA_XREF","CDIR_NWX_NCST_SRC_TYPE","CDIR_NWX_NRBG_RBRV_GPCI","CDIR_NWX_NRBN_RBRV_NAT","CDIR_NWX_NRBR_RBRV_RVU","CDIR_NWX_NRBZ_RBRV_ZIP","CDIR_NWX_NSCV_SCH_VALUE","CDIR_NWX_NSHC_SCHEDULES","CDIR_NWX_NSVM_SCH_MOD","CDIR_AUDIT_CMC_IPCD_PROC_CD","CDIR_AUDIT_CMC_PDDS_PROD_DESC","CDIR_AUDIT_CMC_PRPR_PROV","CDIR_XC_CMC_CDML_CL_LINE","CDIR_XC_CMC_CLCL_CLAIM","CDIR_XC_CMC_CLHP_HOSP","CDS_CODE_COCE_DET","CMC_ACPR_PYMT_RED","CMC_BLCT_COMP_TOTL","CMC_BPCD_CLM_DTL","CMC_BPCL_CLM","CMC_BPHM_CLM_DTL","CMC_CDML_CL_LINE","CMC_CDNP_NWX_PRCNG","CMC_CKPY_PAYEE_SUM","CMC_CLCK_CLM_CHECK","CMC_CLCL_CLAIM","CMC_CLHP_HOSP","CMC_CLMF_MULT_FUNC","CMC_CSCI_CONTACT","CMC_GRGR_GROUP","CMC_IPCD_PROC_CD","CMC_LOBD_LINE_BUS","CMC_MECM_COMM","CMC_MEMD_MECR_DETL","CMC_MEMI_MECR_INTF","CMC_PDDS_PROD_DESC","CMC_PRPR_PROV","CMC_UMIN_INPATIENT","CMC_UMSV_SERVICES","NWX_NASA_ASA_XREF","NWX_NCST_SRC_TYPE","NWX_NRBG_RBRV_GPCI","NWX_NRBN_RBRV_NAT","NWX_NRBR_RBRV_RVU","NWX_NRBZ_RBRV_ZIP","NWX_NSCV_SCH_VALUE","NWX_NSHC_SCHEDULES","NWX_NSVM_SCH_MOD","AUDIT_CMC_IPCD_PROC_CD","AUDIT_CMC_PDDS_PROD_DESC","AUDIT_CMC_PRPR_PROV","XC_CMC_CDML_CL_LINE","XC_CMC_CLCL_CLAIM","XC_CMC_CLHP_HOSP","COBL_SOURCE_CK","BLCT_CK","CSCI_EMAIL","WMDS_SEQ_NO","MECM_EMAIL","NCST_SOURCE_TYPE","NSHC_GEO_SRC_TP","NSHC_RVU_SRC_TP","NSHC_GPCI_SRC_TP","NSHC_ZIP_SRC_TP","NSHC_CONV_SRC_TP",]
}

SCAN_LOCATION    = "NYHP"
SCAN_ASSET_TYPES = [
    "AI_CONNECTION", "AI_SERVICE_CONNECTOR", "DTEMPLATE", "GUIDE",
    "PROCESS", "PROCESS_OBJECT", "DMAPPLET", "MTT", "DSS", "DRS",
    "DMASK", "FWCONFIG", "VISIOTEMPLATE", "PCS", "CustomSource",
    "WORKFLOW", "TASKFLOW", "SequenceGenerator", "MI_TASK",
    "DBMI_TASK", "MI_FILE_LISTENER",
]

EXPORT_BATCH_SIZE    = 50
EXPORT_POLL_INTERVAL = 3
EXPORT_TIMEOUT       = 120
PAGE_SIZE            = 200
API_RETRIES          = 2
API_RETRY_BACKOFF    = 5

SESSION_FILE   = "idmc_session.json"
CACHE_FILE     = "idmc_content_cache.pkl"
OUTPUT_CSV     = "idmc_deep_scan_report.csv"
OUTPUT_JSON    = "idmc_deep_scan_report.json"
OUTPUT_SUMMARY = "idmc_deep_scan_summary.txt"

SKIP_FILES = [
    "exportmetadata", "exportpackage", "contentsofexportpackage",
    ".chksum", "__macosx", ".ds_store",
]

SESSION = {}
_START_TIME = None


# =========================================================================
# UTILITIES
# =========================================================================
def elapsed():
    if _START_TIME is None:
        return ""
    secs = int(time.time() - _START_TIME)
    m, s = divmod(secs, 60)
    return f"[{m:02d}:{s:02d}]"


def _api_get(url, headers, cookies, params=None, timeout=60):
    """GET with retry logic for transient failures."""
    last_err = None
    for attempt in range(1 + API_RETRIES):
        try:
            r = requests.get(url, headers=headers, cookies=cookies,
                             params=params, verify=SSL_VERIFY, timeout=timeout)
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if attempt < API_RETRIES:
                wait = API_RETRY_BACKOFF * (attempt + 1)
                print(f"  [RETRY] GET failed ({e.__class__.__name__}), retrying in {wait}s...")
                time.sleep(wait)
    raise last_err


def _api_post(url, headers, cookies, json_body=None, timeout=60):
    """POST with retry logic for transient failures."""
    last_err = None
    for attempt in range(1 + API_RETRIES):
        try:
            r = requests.post(url, headers=headers, cookies=cookies,
                              json=json_body, verify=SSL_VERIFY, timeout=timeout)
            return r
        except (requests.ConnectionError, requests.Timeout) as e:
            last_err = e
            if attempt < API_RETRIES:
                wait = API_RETRY_BACKOFF * (attempt + 1)
                print(f"  [RETRY] POST failed ({e.__class__.__name__}), retrying in {wait}s...")
                time.sleep(wait)
    raise last_err


# =========================================================================
# SESSION MANAGEMENT
# =========================================================================
def load_session():
    global SESSION
    if not os.path.exists(SESSION_FILE):
        sample = {
            "IDMC_SERVER_URL": "https://use6.dm-us.informaticacloud.com",
            "IDS_TOKEN": "",
            "USER_SESSION": "",
            "JSESSIONID": "",
            "X_INFA_ORG_ID": "",
            "XSRF_TOKEN": "",
        }
        with open(SESSION_FILE, "w") as f:
            json.dump(sample, f, indent=2)
        print(f"[ERROR] {SESSION_FILE} not found. Sample created — fill in values and re-run.")
        print(f"\n  How to get cookie values:")
        print(f"  1. Log in to IDMC via SSO in Edge/Chrome")
        print(f"  2. F12 > Network tab > click any request > Cookies tab")
        print(f"  3. Copy values into {SESSION_FILE}")
        return False

    try:
        with open(SESSION_FILE) as f:
            SESSION = json.load(f)
    except Exception as e:
        print(f"[ERROR] Bad {SESSION_FILE}: {e}")
        return False

    if not (SESSION.get("IDS_TOKEN") or SESSION.get("USER_SESSION")):
        print(f"[ERROR] No token in {SESSION_FILE}. Need IDS_TOKEN or USER_SESSION.")
        return False

    print(f"[OK]   Session loaded from {SESSION_FILE}")
    return True


def capture_cookies_via_edge():
    global SESSION
    print(f"[INFO] Launching Edge for SSO login ({IDMC_LOGIN_URL})...")
    opts = EdgeOptions()
    for a in ["--disable-gpu", "--no-sandbox", "--window-size=1280,900",
              "--disable-blink-features=AutomationControlled"]:
        opts.add_argument(a)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    driver = webdriver.Edge(options=opts)
    captured = {}
    try:
        driver.get(IDMC_LOGIN_URL)
        print("[WAIT] Complete SSO in the Edge window...")
        start = time.time()
        while time.time() - start < LOGIN_WAIT_SECONDS:
            if any(x in driver.current_url for x in
                   ["/diUI/", "/cloudUI/", "/activemonitor/", "/administrator/",
                    "/integration-design/", "/data-integration/", "/ccgf-"]):
                break
            time.sleep(2)
        time.sleep(3)
        if "use" in driver.current_url:
            driver.get(driver.current_url)
            time.sleep(2)

        for c in driver.get_cookies():
            n, v = c.get("name", ""), c.get("value", "")
            if n == "IDS_TOKEN" and v:
                captured["IDS_TOKEN"] = v
                print(f"[OK]   IDS_TOKEN ({len(v)} chars)")
            elif n == "USER_SESSION" and v:
                captured["USER_SESSION"] = v
                print(f"[OK]   USER_SESSION ({len(v)} chars)")
            elif n == "JSESSIONID" and v:
                captured["JSESSIONID"] = v
                print(f"[OK]   JSESSIONID")
            elif n == "X-INFA-ORG-ID" and v:
                captured["X_INFA_ORG_ID"] = v
                print(f"[OK]   X-INFA-ORG-ID: {v}")
            elif n == "XSRF_TOKEN" and v:
                captured["XSRF_TOKEN"] = v
                print(f"[OK]   XSRF_TOKEN")

        if not captured.get("X_INFA_ORG_ID"):
            try:
                for ck in driver.execute_script("return document.cookie").split(";"):
                    if "X-INFA-ORG-ID=" in ck:
                        captured["X_INFA_ORG_ID"] = ck.split("=", 1)[1].strip()
                        print(f"[OK]   X-INFA-ORG-ID (JS): {captured['X_INFA_ORG_ID']}")
            except Exception:
                pass
        if not captured.get("X_INFA_ORG_ID"):
            try:
                m = re.search(r'"orgId"\s*:\s*"([^"]+)"', driver.page_source)
                if m:
                    captured["X_INFA_ORG_ID"] = m.group(1)
                    print(f"[OK]   X-INFA-ORG-ID (page): {m.group(1)}")
            except Exception:
                pass

        m = re.search(r"(https://[^/]+\.informaticacloud\.com)", driver.current_url)
        if m:
            captured["IDMC_SERVER_URL"] = m.group(1)
            print(f"[OK]   Server: {m.group(1)}")
    except Exception as e:
        print(f"[ERROR] Browser: {e}")
    finally:
        driver.quit()
        print("[INFO] Browser closed.\n")

    if not (captured.get("IDS_TOKEN") or captured.get("USER_SESSION")):
        print("[ERROR] No tokens captured.")
        return False
    if not captured.get("IDMC_SERVER_URL"):
        captured["IDMC_SERVER_URL"] = "https://use6.dm-us.informaticacloud.com"
    SESSION.update(captured)
    return True


def save_session():
    d = dict(SESSION)
    d["saved_at"] = datetime.now().isoformat()
    with open(SESSION_FILE, "w") as f:
        json.dump(d, f, indent=2)
    print(f"[OK]   Session saved to {SESSION_FILE}")


def _is_valid_json_response(resp):
    """Check if response is a valid JSON API response (not an HTML login redirect)."""
    if resp.status_code != 200:
        return False, f"HTTP {resp.status_code}"
    ct = resp.headers.get("Content-Type", "")
    if "html" in ct.lower():
        return False, "HTML response (session expired / login redirect)"
    try:
        data = resp.json()
    except Exception:
        return False, "non-JSON response"
    if "objects" not in data or not isinstance(data["objects"], list):
        return False, "response missing 'objects' list"
    return True, data


def validate_session():
    token = SESSION.get("IDS_TOKEN") or SESSION.get("USER_SESSION", "")
    server = SESSION.get("IDMC_SERVER_URL", "").rstrip("/")
    h = {
        "Content-Type": "application/json", "Accept": "application/json",
        "icSessionId": token, "INFA-SESSION-ID": token,
        "X-XSRF-TOKEN": SESSION.get("XSRF_TOKEN", ""),
        "X-INFA-ORG-ID": SESSION.get("X_INFA_ORG_ID", ""),
    }
    c = {
        "XSRF_TOKEN": SESSION.get("XSRF_TOKEN", ""),
        "X-INFA-ORG-ID": SESSION.get("X_INFA_ORG_ID", ""),
    }
    if SESSION.get("IDS_TOKEN"):    c["IDS_TOKEN"] = SESSION["IDS_TOKEN"]
    if SESSION.get("USER_SESSION"): c["USER_SESSION"] = SESSION["USER_SESSION"]
    if SESSION.get("JSESSIONID"):   c["JSESSIONID"] = SESSION["JSESSIONID"]

    for base in ["/saas/public/core/v3", "/public/core/v3"]:
        try:
            r = _api_get(f"{server}{base}/objects", h, c, params={"limit": 1}, timeout=15)
            ok, result = _is_valid_json_response(r)
            if not ok:
                continue

            data = result
            n = len(data["objects"])
            if n == 0:
                # Double-check with limit=5 to distinguish empty org from expired session
                r2 = _api_get(f"{server}{base}/objects", h, c, params={"limit": 5}, timeout=15)
                try:
                    if len(r2.json().get("objects", [])) == 0:
                        print(f"[WARN] 0 objects returned — session may be expired.")
                        return None
                except Exception:
                    pass

            print(f"[OK]   Session valid. v3: {base} (test: {n} object(s))")
            return base
        except Exception:
            pass

    print(f"[ERROR] Session invalid. Update {SESSION_FILE} and re-run.")
    return None


# =========================================================================
# IDMC API CLIENT
# =========================================================================
class IDMCClient:
    def __init__(self, v3_base):
        self.server = SESSION.get("IDMC_SERVER_URL", "").rstrip("/")
        self.token = SESSION.get("IDS_TOKEN") or SESSION.get("USER_SESSION", "")
        self.v3 = v3_base

    def _h(self):
        return {
            "Content-Type": "application/json", "Accept": "application/json",
            "icSessionId": self.token, "INFA-SESSION-ID": self.token,
            "X-XSRF-TOKEN": SESSION.get("XSRF_TOKEN", ""),
            "X-INFA-ORG-ID": SESSION.get("X_INFA_ORG_ID", ""),
        }

    def _c(self):
        c = {
            "XSRF_TOKEN": SESSION.get("XSRF_TOKEN", ""),
            "X-INFA-ORG-ID": SESSION.get("X_INFA_ORG_ID", ""),
        }
        if SESSION.get("IDS_TOKEN"):    c["IDS_TOKEN"] = SESSION["IDS_TOKEN"]
        if SESSION.get("USER_SESSION"): c["USER_SESSION"] = SESSION["USER_SESSION"]
        if SESSION.get("JSESSIONID"):   c["JSESSIONID"] = SESSION["JSESSIONID"]
        return c

    def get(self, path, params=None, timeout=60):
        return _api_get(f"{self.server}{path}", self._h(), self._c(),
                        params=params, timeout=timeout)

    def post(self, path, body=None, timeout=60):
        return _api_post(f"{self.server}{path}", self._h(), self._c(),
                         json_body=body, timeout=timeout)

    def find_assets(self):
        all_assets = []
        print(f"{elapsed()} Fetching assets (location='{SCAN_LOCATION}', {len(SCAN_ASSET_TYPES)} types)...")
        for atype in SCAN_ASSET_TYPES:
            skip, items = 0, []
            while True:
                try:
                    r = self.get(f"{self.v3}/objects",
                                 {"q": f"type=='{atype}'", "limit": PAGE_SIZE, "skip": skip})
                except Exception as e:
                    print(f"  [{atype:12s}] Network error: {e}")
                    break

                ok, result = _is_valid_json_response(r)
                if not ok:
                    if "expired" in str(result).lower() or "HTML" in str(result):
                        print(f"\n[ERROR] Session expired during asset fetch ({atype}: {result}).")
                        print(f"        Re-login via SSO, update {SESSION_FILE}, and re-run.")
                        return None  # Distinguish from empty list
                    break

                objs = result.get("objects", [])
                if not objs:
                    break
                items.extend(objs)
                if len(objs) < PAGE_SIZE:
                    break
                skip += PAGE_SIZE

            if SCAN_LOCATION:
                loc = SCAN_LOCATION.lower()
                items = [o for o in items
                         if o.get("path", "").lower().startswith(loc + "/")
                         or o.get("path", "").lower() == loc
                         or o.get("location", "").lower().startswith(loc)]
            if items:
                print(f"  [{atype:12s}] {len(items)}")
            all_assets.extend(items)

        print(f"[OK]   Total: {len(all_assets)} assets")
        return all_assets

    def export_batch(self, ids):
        body = {
            "name": f"scan_{datetime.now().strftime('%H%M%S')}",
            "objects": [{"id": i, "includeDependencies": False} for i in ids],
        }
        try:
            r = self.post(f"{self.v3}/export", body)
        except Exception as e:
            print(f"    [ERROR] Export POST failed: {e}")
            return None

        if r.status_code not in (200, 202):
            return None
        try:
            resp_data = r.json()
            jid = resp_data.get("jobId", resp_data.get("id", ""))
        except Exception:
            return None
        if not jid:
            return None

        t0 = time.time()
        while time.time() - t0 < EXPORT_TIMEOUT:
            try:
                sr = self.get(f"{self.v3}/export/{jid}")
            except Exception:
                time.sleep(EXPORT_POLL_INTERVAL)
                continue
            if sr.status_code == 200:
                try:
                    status_data = sr.json()
                    st = status_data.get("status", {}).get("state",
                         status_data.get("jobStatus", {}).get("state", ""))
                except Exception:
                    st = ""
                if st in ("SUCCESSFUL", "SUCCESS", "COMPLETED"):
                    break
                if st in ("FAILED", "ERROR"):
                    return None
            time.sleep(EXPORT_POLL_INTERVAL)
        else:
            print(f"    [WARN] Export timed out after {EXPORT_TIMEOUT}s")
            return None

        try:
            dl = _api_get(
                f"{self.server}{self.v3}/export/{jid}/package",
                self._h(), self._c(), timeout=120,
            )
            return dl.content if dl.status_code == 200 and len(dl.content) > 0 else None
        except Exception as e:
            print(f"    [ERROR] Package download failed: {e}")
            return None


# =========================================================================
# ZIP EXTRACTION → DATAFRAME
# =========================================================================
ASSET_TYPE_EXTENSIONS = [
    (".TASKFLOW.", "TASKFLOW"),
    (".DTEMPLATE",  "MAPPING"),
    (".MTT",        "MTT"),
    (".MAPPLET.",   "MAPPLET"),
    (".DSS.",       "DSS"),
    (".DRS.",       "DRS"),
    (".FWCONFIG.",  "FWCONFIG"),
    (".DBMI_TASK.", "DBMI_TASK"),
]


def parse_asset_path(filepath):
    bn = os.path.basename(filepath)
    dp = re.sub(r"^Explore/?", "", os.path.dirname(filepath))
    for ext, at in ASSET_TYPE_EXTENSIONS:
        if ext in bn:
            name = bn.split(ext)[0]
            return (f"{dp}/{name}" if dp else name), at
    return (f"{dp}/{bn}" if dp else bn), "UNKNOWN"


def _match_api(name, amap):
    n = name.split("/")[-1].lower()
    for oid, info in amap.items():
        if info["name"].split("/")[-1].lower() == n:
            return oid
    return ""


def extract_zip_to_rows(zip_bytes, asset_map):
    rows = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return rows

    for fn in zf.namelist():
        if any(s in fn.lower() for s in SKIP_FILES):
            continue
        raw = zf.read(fn)

        if fn.lower().endswith(".zip"):
            aname, atype = parse_asset_path(fn)
            aid = _match_api(aname, asset_map)
            try:
                izf = zipfile.ZipFile(io.BytesIO(raw))
                for ifn in izf.namelist():
                    try:
                        ct = izf.read(ifn).decode("utf-8", errors="ignore")
                    except Exception:
                        continue
                    if len(ct.strip()) < 10:
                        continue
                    rows.append({
                        "asset_name": aname, "asset_type": atype,
                        "asset_id": aid, "source_file": ifn, "content": ct,
                    })
            except zipfile.BadZipFile:
                try:
                    ct = raw.decode("utf-8", errors="ignore")
                    if len(ct.strip()) >= 10:
                        rows.append({
                            "asset_name": aname, "asset_type": atype,
                            "asset_id": aid, "source_file": fn, "content": ct,
                        })
                except Exception:
                    pass
        else:
            try:
                ct = raw.decode("utf-8", errors="ignore")
            except Exception:
                continue
            if len(ct.strip()) < 10:
                continue
            aname, atype = parse_asset_path(fn)
            if atype == "UNKNOWN" and fn.endswith(".json"):
                continue
            aid = _match_api(aname, asset_map)
            rows.append({
                "asset_name": aname, "asset_type": atype,
                "asset_id": aid, "source_file": fn, "content": ct,
            })

    zf.close()
    return rows


def build_dataframe(client):
    assets = client.find_assets()
    if assets is None:
        # Session expired during fetch — propagate as None
        return None
    if not assets:
        return pd.DataFrame()

    rows, total = [], len(assets)
    failed_batches = 0
    print(f"\n{elapsed()} Exporting {total} assets in batches of {EXPORT_BATCH_SIZE}...")

    for i in range(0, total, EXPORT_BATCH_SIZE):
        batch = assets[i : i + EXPORT_BATCH_SIZE]
        ids = [a["id"] for a in batch if a.get("id")]
        amap = {
            a["id"]: {"name": a.get("path", a.get("name", "")), "type": a.get("type", "")}
            for a in batch if a.get("id")
        }
        bnum = i // EXPORT_BATCH_SIZE + 1
        pct = min(100, int((i + len(batch)) / total * 100))
        names_preview = ", ".join(a.get("path", "?") for a in batch)[:80]
        print(f"  Batch {bnum} ({pct}%): {names_preview}...")

        zb = client.export_batch(ids)
        if zb:
            r = extract_zip_to_rows(zb, amap)
            rows.extend(r)
            print(f"    {len(r)} content rows extracted")
        else:
            failed_batches += 1
            print(f"    Export failed — batch skipped")

    if failed_batches:
        print(f"\n[WARN] {failed_batches} batch(es) failed to export")

    df = pd.DataFrame(rows)
    if not df.empty:
        df["content_length"] = df["content"].str.len()
        print(f"\n[OK]   DataFrame: {len(df)} rows, {df['asset_name'].nunique()} unique assets")
        print(f"       Total content: {df['content_length'].sum():,} chars")
        type_counts = dict(df.groupby("asset_type")["asset_name"].nunique())
        print(f"       Types: {type_counts}")
    return df


# =========================================================================
# TASKFLOW XML COMPONENT PARSER (multi-pass, line ownership)
# =========================================================================
def parse_taskflow_xml(xml_content):
    lines = xml_content.split("\n")
    line_to_component = {}
    components = []

    svc_type_map = {
        "icsexecutedatatask":       "DataTask",
        "emailnotificationservice": "Notification",
        "icsexpression":            "Expression",
        "icscommand":               "Command",
        "icssubtaskflow":           "SubTaskflow",
        "icswait":                  "Wait",
        "icsthrow":                 "Throw",
        "icsjump":                  "Jump",
        "icsrestservice":           "RestService",
        "icshumantask":             "HumanTask",
        "icsfilelistener":          "FileListener",
        "icsdecision":              "Decision",
        "icsassignment":            "Assignment",
        "icsnotification":          "Notification",
    }

    def find_close(tag, start):
        close = f"</{tag}>"
        for j in range(start + 1, len(lines)):
            if close in lines[j]:
                return j
        return len(lines) - 1

    def get_tag_val(start, end, tag):
        for j in range(start, min(end + 1, len(lines))):
            m = re.search(rf"<{tag}>([^<]+)</{tag}>", lines[j])
            if m:
                return m.group(1)
        return None

    def claim(start, end, comp_type, comp_name):
        comp = {
            "type": comp_type, "name": comp_name,
            "start": start, "end": end, "line_nums": [],
        }
        for j in range(start, end + 1):
            if j not in line_to_component:
                line_to_component[j] = len(components)
                comp["line_nums"].append(j)
        components.append(comp)

    # Pass 1: <service> blocks — atomic steps (DataTask, Notification, etc.)
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if "<service " in low and i not in line_to_component:
            end = find_close("service", i)
            title = get_tag_val(i, end, "title") or f"service_{i}"
            svc_name = get_tag_val(i, end, "serviceName") or "UnknownService"
            comp_type = svc_type_map.get(svc_name.strip().lower(), svc_name)
            claim(i, end, comp_type, title)

    # Pass 2: <assignment> blocks
    for i, line in enumerate(lines):
        if "<assignment " in line.strip().lower() and i not in line_to_component:
            end = find_close("assignment", i)
            title = get_tag_val(i, end, "title") or f"assignment_{i}"
            claim(i, end, "Assignment", title)

    # Pass 3: <end> blocks
    for i, line in enumerate(lines):
        if "<end " in line.strip().lower() and i not in line_to_component:
            end = find_close("end", i)
            title = get_tag_val(i, end, "title") or f"end_{i}"
            claim(i, end, "End", title)

    # Pass 4: <condition> blocks inside <link> — belong to Decisions
    container_ranges = []
    for i, line in enumerate(lines):
        low = line.strip().lower()
        if "<container " in low and 'type="exclusive"' in low:
            end = find_close("container", i)
            title = get_tag_val(i, end, "title") or f"decision_{i}"
            container_ranges.append((i, end, title))

    for i, line in enumerate(lines):
        if i in line_to_component:
            continue
        low = line.strip().lower()
        if "<condition" in low:
            end = find_close("condition", i) if "</condition>" not in low else i
            parent_name = "decision_unknown"
            for cs, ce, ct in container_ranges:
                if cs <= i <= ce:
                    parent_name = ct
                    break
            claim(i, end, "Decision/Condition", parent_name)

    # Pass 5: <input> and <tempFields> (header sections, early in the file)
    for i, line in enumerate(lines):
        if "<input>" in line.strip().lower() and i not in line_to_component and i < 200:
            end = find_close("input", i)
            claim(i, end, "InputParameters", "input_parameters")
            break

    for i, line in enumerate(lines):
        if "<tempfields>" in line.strip().lower() and i not in line_to_component and i < 300:
            end = find_close("tempFields", i)
            claim(i, end, "TempFields", "temp_fields")
            break

    # Pass 6: <catch> blocks (error handlers)
    for i, line in enumerate(lines):
        if i in line_to_component:
            continue
        if "<catch " in line.strip().lower():
            end = find_close("catch", i) if "</catch>" not in line else i
            name_m = re.search(r'name="([^"]+)"', line)
            cname = name_m.group(1) if name_m else f"catch_{i}"
            parent_name = "unknown_parent"
            for cs, ce, ct in container_ranges:
                if cs <= i <= ce:
                    parent_name = ct
                    break
            claim(i, end, "ErrorHandler", f"{cname} ({parent_name})")

    return components, lines, line_to_component


# =========================================================================
# SEARCH ENGINE
# =========================================================================
def search_content(df, search_terms):
    if df.empty:
        return pd.DataFrame()

    results = []

    for ti in search_terms:
        term, category = ti["term"], ti["category"]
        pat = re.compile(re.escape(term), re.IGNORECASE)

        mask = df["content"].str.contains(term, case=False, na=False, regex=False)

        for _, row in df[mask].iterrows():
            content = row["content"]
            asset_name = row["asset_name"]
            asset_type = row["asset_type"]
            asset_id = row["asset_id"]
            src = row["source_file"]

            is_xml = (asset_type == "TASKFLOW" or src.endswith(".xml"))
            is_bin = ("@3.bin" in src or ("bin/" in src and not src.endswith(".jpeg")))
            is_mtt = ("mtTask" in src or (asset_type == "MTT" and src.endswith(".json")))
            is_mapping_json = ("mappingTemplate" in src)

            content_lines = content.split("\n")
            matched_line_nums = [i for i, l in enumerate(content_lines) if pat.search(l)]

            if not matched_line_nums:
                continue

            # ---- TASKFLOW XML: attribute matches to parsed components ----
            if is_xml:
                comps, _, line_map = parse_taskflow_xml(content)

                grouped = {}
                for lnum in matched_line_nums:
                    if lnum in line_map:
                        cidx = line_map[lnum]
                        comp = comps[cidx]
                        key = (comp["type"], comp["name"])
                    else:
                        key = ("TaskflowBody", "unclaimed_xml")
                    if key not in grouped:
                        grouped[key] = []
                    grouped[key].append(content_lines[lnum].strip())

                for (ctype, cname), mlines in grouped.items():
                    results.append({
                        "search_term": term, "category": category,
                        "asset_name": asset_name, "asset_type": asset_type,
                        "asset_id": asset_id,
                        "component_type": ctype, "component_name": cname,
                        "match_count": sum(len(pat.findall(l)) for l in mlines),
                        "matched_lines": mlines[:10],
                    })

            # ---- MAPPING BIN or MAPPING JSON: parse JSON structure ----
            elif is_bin or is_mapping_json:
                try:
                    jdata = json.loads(content)
                    if isinstance(jdata, list):
                        jdata = jdata[0] if jdata else {}
                    if isinstance(jdata, dict):
                        content_obj = jdata.get("content", jdata)
                    else:
                        content_obj = {}
                    if isinstance(content_obj, list):
                        # Some mappings nest content as a list of dicts
                        merged = {}
                        for idx, item in enumerate(content_obj):
                            if isinstance(item, dict):
                                merged[f"item_{idx}"] = item
                        content_obj = merged
                    if isinstance(content_obj, dict):
                        for key, val in content_obj.items():
                            if key.startswith("$$"):
                                continue
                            val_str = json.dumps(val, default=str) if not isinstance(val, str) else val
                            founds = list(pat.finditer(val_str))
                            if not founds:
                                continue
                            mlines = []
                            for f in founds:
                                s = max(0, f.start() - 80)
                                e = min(len(val_str), f.end() + 80)
                                mlines.append(val_str[s:e].replace("\n", " ").strip())
                            ctype = "MappingProperty"
                            if isinstance(val, list):
                                ctype = "MappingTransformation"
                            elif isinstance(val, dict):
                                ctype = "MappingObject"
                            results.append({
                                "search_term": term, "category": category,
                                "asset_name": asset_name, "asset_type": asset_type,
                                "asset_id": asset_id,
                                "component_type": ctype, "component_name": key,
                                "match_count": len(founds),
                                "matched_lines": mlines[:10],
                            })
                except json.JSONDecodeError:
                    mlines = [content_lines[i].strip() for i in matched_line_nums]
                    results.append({
                        "search_term": term, "category": category,
                        "asset_name": asset_name, "asset_type": asset_type,
                        "asset_id": asset_id,
                        "component_type": "MappingRaw", "component_name": src,
                        "match_count": len(matched_line_nums),
                        "matched_lines": mlines[:10],
                    })

            # ---- MTT JSON: parse task config sections ----
            elif is_mtt:
                try:
                    jdata = json.loads(content)
                    if isinstance(jdata, list):
                        jdata = jdata[0] if jdata else {}
                    for key, val in jdata.items():
                        val_str = json.dumps(val, default=str) if not isinstance(val, str) else val
                        founds = list(pat.finditer(val_str))
                        if not founds:
                            continue
                        mlines = []
                        for f in founds:
                            s = max(0, f.start() - 80)
                            e = min(len(val_str), f.end() + 80)
                            mlines.append(val_str[s:e].replace("\n", " ").strip())
                        results.append({
                            "search_term": term, "category": category,
                            "asset_name": asset_name, "asset_type": asset_type,
                            "asset_id": asset_id,
                            "component_type": "TaskConfig", "component_name": key,
                            "match_count": len(founds),
                            "matched_lines": mlines[:10],
                        })
                except json.JSONDecodeError:
                    mlines = [content_lines[i].strip() for i in matched_line_nums]
                    results.append({
                        "search_term": term, "category": category,
                        "asset_name": asset_name, "asset_type": asset_type,
                        "asset_id": asset_id,
                        "component_type": "TaskRaw", "component_name": src,
                        "match_count": len(matched_line_nums),
                        "matched_lines": mlines[:10],
                    })

            # ---- EVERYTHING ELSE: general line-level match ----
            else:
                mlines = [content_lines[i].strip() for i in matched_line_nums]
                results.append({
                    "search_term": term, "category": category,
                    "asset_name": asset_name, "asset_type": asset_type,
                    "asset_id": asset_id,
                    "component_type": "General", "component_name": src,
                    "match_count": len(matched_line_nums),
                    "matched_lines": mlines[:10],
                })

    rdf = pd.DataFrame(results)
    if not rdf.empty:
        rdf = rdf.groupby(
            ["asset_name", "search_term", "component_type", "component_name"]
        ).agg({
            "category": "first",
            "asset_type": "first",
            "asset_id": "first",
            "match_count": "sum",
            "matched_lines": lambda x: [l for sub in x for l in sub][:10],
        }).reset_index()
    return rdf


# =========================================================================
# REPORTS
# =========================================================================
def write_reports(rdf, search_terms):
    if rdf.empty:
        print("\n[WARN] No matches found.")
        return

    # --- CSV ---
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "search_term", "category", "asset_name", "asset_type",
            "component_type", "component_name", "match_count", "matched_lines",
        ])
        for _, r in rdf.iterrows():
            ml = " ||| ".join(r["matched_lines"][:5]) if isinstance(r["matched_lines"], list) else ""
            w.writerow([
                r["search_term"], r["category"], r["asset_name"], r["asset_type"],
                r["component_type"], r["component_name"], r["match_count"], ml,
            ])
    print(f"[OK]   CSV: {OUTPUT_CSV}")

    # --- JSON ---
    rj = rdf.copy()
    rj["matched_lines"] = rj["matched_lines"].apply(lambda x: x if isinstance(x, list) else [])
    rj.to_json(OUTPUT_JSON, orient="records", indent=2)
    print(f"[OK]   JSON: {OUTPUT_JSON}")

    # --- CONSOLE SUMMARY ---
    print("\n" + "=" * 80)
    print("  IMPACT ANALYSIS RESULTS")
    print("=" * 80)
    print(f"\n  Total matches : {len(rdf)}")
    print(f"  Unique assets : {rdf['asset_name'].nunique()}")
    print(f"  Unique terms  : {rdf['search_term'].nunique()}/{len(search_terms)}")

    # By term
    by_term = rdf.groupby("search_term").agg(
        category=("category", "first"),
        assets=("asset_name", "nunique"),
        hits=("match_count", "sum"),
    ).sort_index()

    print(f"\n  {'TERM':<40s} {'CATEGORY':<15s} {'ASSETS':>6s} {'HITS':>6s}")
    print(f"  {'-' * 40} {'-' * 15} {'-' * 6} {'-' * 6}")
    for t, r in by_term.iterrows():
        print(f"  {t:<40s} {r['category']:<15s} {r['assets']:>6d} {r['hits']:>6.0f}")

    # Not found
    not_found = set(t["term"] for t in search_terms) - set(rdf["search_term"].unique())
    if not_found:
        print(f"\n  NOT FOUND ({len(not_found)}):")
        for t in sorted(not_found):
            print(f"    - {t}")

    # By asset type
    if rdf["asset_type"].nunique() > 1:
        print(f"\n  BY ASSET TYPE:")
        by_atype = rdf.groupby("asset_type").agg(
            assets=("asset_name", "nunique"), hits=("match_count", "sum"),
        ).sort_values("assets", ascending=False)
        print(f"  {'TYPE':<20s} {'ASSETS':>6s} {'HITS':>6s}")
        print(f"  {'-' * 20} {'-' * 6} {'-' * 6}")
        for at, r in by_atype.iterrows():
            print(f"  {at:<20s} {r['assets']:>6d} {r['hits']:>6.0f}")

    # Component detail
    print(f"\n  COMPONENT DETAIL:")
    print(f"  {'ASSET':<40s} {'COMP_TYPE':<22s} {'COMP_NAME':<30s} {'TERM':<25s} {'HITS':>5s}")
    print(f"  {'-' * 40} {'-' * 22} {'-' * 30} {'-' * 25} {'-' * 5}")
    for _, r in rdf.sort_values(["asset_name", "component_type"]).head(50).iterrows():
        a = r["asset_name"][-40:] if len(r["asset_name"]) > 40 else r["asset_name"]
        ct = str(r["component_type"])[:22]
        cn = str(r["component_name"])[:30]
        st = str(r["search_term"])[:25]
        print(f"  {a:<40s} {ct:<22s} {cn:<30s} {st:<25s} {r['match_count']:>5.0f}")

    # Matched lines sample
    print(f"\n  MATCHED LINES (sample):")
    print(f"  {'-' * 100}")
    count = 0
    for _, r in rdf.sort_values(["asset_name", "component_type"]).iterrows():
        if count >= 30:
            break
        ml = r.get("matched_lines", [])
        if isinstance(ml, list):
            for l in ml[:2]:
                if count >= 30:
                    break
                aname = r["asset_name"].split("/")[-1][:20]
                cname = str(r["component_name"])[:20]
                print(f"  [{aname}] [{cname}] {l[:90]}")
                count += 1

    print("\n" + "=" * 80)

    # --- SUMMARY FILE ---
    with open(OUTPUT_SUMMARY, "w", encoding="utf-8") as f:
        f.write(f"IDMC Impact Analysis — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Project: {SCAN_LOCATION}\n")
        f.write(f"Total matches: {len(rdf)}\n")
        f.write(f"Unique assets: {rdf['asset_name'].nunique()}\n")
        f.write(f"Search terms: {len(search_terms)} ({rdf['search_term'].nunique()} found)\n\n")

        for t, tdf in rdf.groupby("search_term"):
            cat = tdf.iloc[0]["category"]
            f.write(f"\n{'=' * 70}\n")
            f.write(f"{t} ({cat}): {tdf['asset_name'].nunique()} assets, {tdf['match_count'].sum():.0f} hits\n")
            f.write(f"{'=' * 70}\n")
            for _, r in tdf.sort_values("asset_name").iterrows():
                f.write(f"\n  Asset: {r['asset_name']}\n")
                f.write(f"  Component: [{r['component_type']}] {r['component_name']}\n")
                f.write(f"  Hits: {r['match_count']:.0f}\n")
                ml = r.get("matched_lines", [])
                if isinstance(ml, list):
                    for l in ml[:5]:
                        f.write(f"    >> {l[:150]}\n")

        if not_found:
            f.write(f"\n\nNOT FOUND:\n")
            for t in sorted(not_found):
                f.write(f"  - {t}\n")

    print(f"[OK]   Summary: {OUTPUT_SUMMARY}")


# =========================================================================
# MAIN
# =========================================================================
def main():
    global _START_TIME
    _START_TIME = time.time()

    parser = argparse.ArgumentParser(description="IDMC Deep Impact Analysis")
    parser.add_argument("--no-cache", action="store_true",
                        help="Ignore cached content, force fresh export")
    parser.add_argument("--cache-only", action="store_true",
                        help="Only search cached data, skip API calls if cache missing")
    args = parser.parse_args()

    print("=" * 80)
    print("  IDMC Object-Level Impact Analysis  (v3)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    terms = [
        {"term": t.strip(), "category": c}
        for c, lst in SEARCH_TERMS.items()
        for t in lst if t.strip()
    ]
    if not terms:
        print("\n[ERROR] No search terms. Edit SEARCH_TERMS in the script.")
        sys.exit(1)

    print(f"\n  Search terms: {len(terms)}")
    for c, lst in SEARCH_TERMS.items():
        active = [t for t in lst if t.strip()]
        if active:
            print(f"    {c}: {', '.join(active[:5])}{'...' if len(active) > 5 else ''}")

    df = None

    # --- Cache handling ---
    if not args.no_cache and os.path.exists(CACHE_FILE):
        print(f"\n[INFO] Cache found: {CACHE_FILE}")
        try:
            df = pd.read_pickle(CACHE_FILE)
            age = datetime.now() - datetime.fromtimestamp(os.path.getmtime(CACHE_FILE))
            print(f"[OK]   {len(df)} rows, {df['asset_name'].nunique()} assets (age: {age})")
            if input("\n  Use cache? (y/n): ").strip().lower() != "y":
                df = None
        except Exception as e:
            print(f"[WARN] Cache error: {e}")
            df = None

    if df is None and args.cache_only:
        print("[ERROR] --cache-only set but no usable cache found.")
        sys.exit(1)

    # --- Fresh export ---
    if df is None:
        v3 = None
        if load_session():
            v3 = validate_session()
        if not v3:
            print(f"\n[INFO] Launching Edge for SSO...\n")
            if not capture_cookies_via_edge():
                sys.exit(1)
            save_session()
            v3 = validate_session()
            if not v3:
                print("[ERROR] Auth failed.")
                sys.exit(1)

        client = IDMCClient(v3)
        df = build_dataframe(client)

        if df is None:
            print("[ERROR] Session expired during export. Re-login and retry.")
            sys.exit(1)

        if not df.empty:
            df.to_pickle(CACHE_FILE)
            print(f"[OK]   Cached: {CACHE_FILE}")

    if df is None or df.empty:
        print("[ERROR] No content to search.")
        sys.exit(1)

    # --- Search ---
    print(f"\n{elapsed()} Searching {len(df)} rows for {len(terms)} terms...")
    rdf = search_content(df, terms)
    print(f"[OK]   {len(rdf)} matches found")

    write_reports(rdf, terms)

    total_secs = int(time.time() - _START_TIME)
    m, s = divmod(total_secs, 60)
    print(f"\n[DONE] Completed in {m}m {s}s")


if __name__ == "__main__":
    main()