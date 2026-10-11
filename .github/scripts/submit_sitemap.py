#!/usr/bin/env python3
"""Invia la sitemap di foresteriagenova.it ai motori di ricerca, senza passaggi manuali.

Gira in GitHub Actions dopo ogni deploy di GitHub Pages (.github/workflows/submit-sitemap.yml):
  1. Google Search Console  -> API ufficiale "sitemaps.submit" (service account)
  2. Bing Webmaster Tools   -> API ufficiale "SubmitFeed" (API key)
  3. IndexNow (Bing, Yandex, Seznam, Naver...) -> URL cambiate di recente, nessuna credenziale

I vecchi "ping" (google.com/ping, bing.com/ping) sono stati dismessi: rispondono 404 e 410.

Credenziali SOLO da variabili d'ambiente (GitHub Secrets). Nessun segreto in questo file.
  GSC_SERVICE_ACCOUNT_JSON  contenuto del file JSON del service account Google
  BING_API_KEY              API key di Bing Webmaster Tools
Se una credenziale manca, il passo corrispondente viene saltato con un avviso, non un errore.

Uso locale:  python submit_sitemap.py --check   (solo lettura: mostra cosa verrebbe inviato)
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse

import requests

DOMAIN = "foresteriagenova.it"
SITE = "https://" + DOMAIN
SITEMAP_URL = SITE + "/sitemap.xml"
# Chiave IndexNow: e' pubblica per protocollo (il file /<chiave>.txt sul sito prova la proprieta').
INDEXNOW_KEY = "14f3e156b2be73826a3ad90246be9cc7"
INDEXNOW_RECENT_DAYS = 7
TIMEOUT = 30
UA = "foresteriagenova-sitemap-submit/1.0 (+https://foresteriagenova.it/)"

CHECK_ONLY = "--check" in sys.argv
summary_lines = []


def log(msg):
    print(msg, flush=True)


def gh_warn(msg):
    log("::warning::" + msg)


def gh_error(msg):
    log("::error::" + msg)


def summary(line):
    summary_lines.append(line)


# ─────────────────────────── sitemap ───────────────────────────
def parse_sitemap(xml):
    urls = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*(.*?)\s*</loc>", block, re.S)
        mod = re.search(r"<lastmod>\s*(.*?)\s*</lastmod>", block, re.S)
        if loc:
            urls.append((loc.group(1).strip(), mod.group(1).strip() if mod else ""))
    return urls


def fetch_live_sitemap():
    """Scarica la sitemap live. Se esiste la copia del repo (checkout), aspetta che la
    versione pubblicata coincida: GitHub Pages puo' servire per qualche secondo la vecchia."""
    local = None
    local_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "sitemap.xml")
    if os.path.exists(local_path):
        with open(local_path, "r", encoding="utf-8") as f:
            local = f.read().strip()
    live = ""
    for attempt in range(1, 11):
        r = requests.get(SITEMAP_URL, params={"nc": int(time.time())},
                         headers={"User-Agent": UA, "Cache-Control": "no-cache"}, timeout=TIMEOUT)
        r.raise_for_status()
        live = r.text.strip()
        if local is None or live == local or CHECK_ONLY:
            break
        log("  sitemap live diversa dal repo (tentativo %d/10), attendo 15 s..." % attempt)
        time.sleep(15)
    else:
        gh_warn("La sitemap pubblicata non coincide ancora con quella del repo: invio comunque, "
                "Google e Bing la rileggeranno alla prossima scansione.")
    urls = parse_sitemap(live)
    if not urls:
        raise SystemExit("Sitemap live vuota o non leggibile: " + SITEMAP_URL)
    return urls


# ─────────────────────────── Google ───────────────────────────
def submit_google():
    raw = os.environ.get("GSC_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        gh_warn("GSC_SERVICE_ACCOUNT_JSON mancante: invio a Google Search Console saltato.")
        summary("| Google Search Console | saltato | secret `GSC_SERVICE_ACCOUNT_JSON` mancante |")
        return True
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
        info = json.loads(raw)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/webmasters"])
        s = AuthorizedSession(creds)
        base = "https://www.googleapis.com/webmasters/v3"
        # proprieta' a cui il service account ha accesso
        r = s.get(base + "/sites", timeout=TIMEOUT)
        r.raise_for_status()
        entries = r.json().get("siteEntry", [])
        mine = [e for e in entries if DOMAIN in e.get("siteUrl", "")
                and e.get("permissionLevel") not in ("siteUnverifiedUser",)]
        if not mine:
            gh_error("Il service account %s non e' utente di nessuna proprieta' %s in Search Console. "
                     "Aggiungilo in Search Console > Impostazioni > Utenti e autorizzazioni con permesso Completo."
                     % (info.get("client_email"), DOMAIN))
            summary("| Google Search Console | ERRORE | service account non autorizzato sulla proprietà |")
            return False
        mine.sort(key=lambda e: 0 if e["siteUrl"].startswith("sc-domain:") else 1)
        prop = mine[0]["siteUrl"]
        q = urllib.parse.quote(prop, safe="") + "/sitemaps/" + urllib.parse.quote(SITEMAP_URL, safe="")
        r = s.put(base + "/sites/" + q, timeout=TIMEOUT)
        if r.status_code not in (200, 204):
            gh_error("Google sitemaps.submit HTTP %d: %s" % (r.status_code, r.text[:300]))
            summary("| Google Search Console | ERRORE | HTTP %d |" % r.status_code)
            return False
        st = s.get(base + "/sites/" + q, timeout=TIMEOUT)
        info_s = st.json() if st.ok else {}
        log("  Google: sitemap inviata su %s (permesso %s). lastSubmitted=%s pending=%s errori=%s avvisi=%s"
            % (prop, mine[0].get("permissionLevel"), info_s.get("lastSubmitted"), info_s.get("isPending"),
               info_s.get("errors", 0), info_s.get("warnings", 0)))
        summary("| Google Search Console | inviata | proprietà `%s`, lastSubmitted %s |"
                % (prop, info_s.get("lastSubmitted", "?")))
        return True
    except Exception as e:  # noqa: BLE001
        gh_error("Google: %s" % e)
        summary("| Google Search Console | ERRORE | %s |" % str(e)[:120])
        return False


# ─────────────────────────── Bing ───────────────────────────
def submit_bing():
    key = os.environ.get("BING_API_KEY", "").strip()
    if not key:
        gh_warn("BING_API_KEY mancante: invio a Bing Webmaster Tools saltato.")
        summary("| Bing Webmaster Tools | saltato | secret `BING_API_KEY` mancante |")
        return True
    try:
        base = "https://ssl.bing.com/webmaster/api.svc/json/"
        h = {"User-Agent": UA, "Content-Type": "application/json; charset=utf-8"}
        r = requests.get(base + "GetUserSites", params={"apikey": key}, headers=h, timeout=TIMEOUT)
        if r.status_code != 200:
            gh_error("Bing GetUserSites HTTP %d: %s" % (r.status_code, r.text[:300]))
            summary("| Bing Webmaster Tools | ERRORE | GetUserSites HTTP %d |" % r.status_code)
            return False
        sites = [x for x in r.json().get("d", []) if DOMAIN in x.get("Url", "")]
        if not sites:
            gh_error("Nessun sito %s nell'account Bing Webmaster collegato a questa API key." % DOMAIN)
            summary("| Bing Webmaster Tools | ERRORE | sito non trovato nell'account |")
            return False
        site_url = sites[0]["Url"]
        r = requests.post(base + "SubmitFeed", params={"apikey": key}, headers=h,
                          data=json.dumps({"siteUrl": site_url, "feedUrl": SITEMAP_URL}), timeout=TIMEOUT)
        if r.status_code == 200:
            log("  Bing: sitemap inviata per %s" % site_url)
            summary("| Bing Webmaster Tools | inviata | sito `%s` |" % site_url)
            return True
        msg = r.text[:300]
        if "already" in msg.lower() or "exist" in msg.lower():
            log("  Bing: sitemap gia' registrata per %s (%s)" % (site_url, msg))
            summary("| Bing Webmaster Tools | già registrata | sito `%s` |" % site_url)
            return True
        gh_error("Bing SubmitFeed HTTP %d: %s" % (r.status_code, msg))
        summary("| Bing Webmaster Tools | ERRORE | SubmitFeed HTTP %d |" % r.status_code)
        return False
    except Exception as e:  # noqa: BLE001
        gh_error("Bing: %s" % e)
        summary("| Bing Webmaster Tools | ERRORE | %s |" % str(e)[:120])
        return False


# ─────────────────────────── IndexNow ───────────────────────────
def submit_indexnow(urls):
    today = dt.date.today()
    recent = []
    for loc, mod in urls:
        try:
            d = dt.date.fromisoformat(mod[:10])
        except ValueError:
            continue
        if (today - d).days <= INDEXNOW_RECENT_DAYS:
            recent.append(loc)
    if not recent:
        log("  IndexNow: nessuna URL modificata negli ultimi %d giorni, niente da inviare." % INDEXNOW_RECENT_DAYS)
        summary("| IndexNow | niente da inviare | nessuna pagina cambiata negli ultimi %d giorni |" % INDEXNOW_RECENT_DAYS)
        return True
    body = {"host": DOMAIN, "key": INDEXNOW_KEY,
            "keyLocation": "%s/%s.txt" % (SITE, INDEXNOW_KEY), "urlList": recent}
    try:
        r = requests.post("https://api.indexnow.org/indexnow", data=json.dumps(body),
                          headers={"User-Agent": UA, "Content-Type": "application/json; charset=utf-8"},
                          timeout=TIMEOUT)
    except Exception as e:  # noqa: BLE001
        gh_error("IndexNow: %s" % e)
        summary("| IndexNow | ERRORE | %s |" % str(e)[:120])
        return False
    if r.status_code in (200, 202):
        log("  IndexNow: %d URL inviate (HTTP %d)" % (len(recent), r.status_code))
        summary("| IndexNow | inviate %d URL | HTTP %d |" % (len(recent), r.status_code))
        return True
    gh_error("IndexNow HTTP %d: %s (chiave %s.txt raggiungibile?)" % (r.status_code, r.text[:200], INDEXNOW_KEY))
    summary("| IndexNow | ERRORE | HTTP %d |" % r.status_code)
    return False


# ─────────────────────────── main ───────────────────────────
def main():
    log("Sitemap: " + SITEMAP_URL)
    urls = fetch_live_sitemap()
    log("  %d URL nella sitemap live, lastmod piu' recente %s" % (len(urls), max((m for _, m in urls), default="?")))
    if CHECK_ONLY:
        today = dt.date.today()
        rec = [l for l, m in urls if m and (today - dt.date.fromisoformat(m[:10])).days <= INDEXNOW_RECENT_DAYS]
        log("  [check] Google: %s | Bing: %s | IndexNow: %d URL recenti"
            % ("credenziali presenti" if os.environ.get("GSC_SERVICE_ACCOUNT_JSON") else "nessuna credenziale",
               "API key presente" if os.environ.get("BING_API_KEY") else "nessuna API key", len(rec)))
        for u in rec:
            log("    - " + u)
        return 0
    ok_g = submit_google()
    ok_b = submit_bing()
    ok_i = submit_indexnow(urls)
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        with open(step, "a", encoding="utf-8") as f:
            f.write("## Invio sitemap foresteriagenova.it\n\n| Destinazione | Esito | Dettaglio |\n|---|---|---|\n")
            f.write("\n".join(summary_lines) + "\n")
    return 0 if (ok_g and ok_b and ok_i) else 1


if __name__ == "__main__":
    sys.exit(main())
