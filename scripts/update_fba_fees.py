#!/usr/bin/env python3
"""
Scrape FBA fees de la calculadora de Amazon (amazon.es) para una lista de ASINs
y actualiza las columnas fba_fee_es/it/de/fr en la tabla COGS de Supabase.

Uso:
  python scripts/update_fba_fees.py B0DWT9QKFF B0G167B2HQ ...
  python scripts/update_fba_fees.py --dry-run B0DWT9QKFF
"""

import argparse
import os
import sys
import time
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://rzuyndmogkawqdstlnht.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

CALCULATOR_URL = "https://sellercentral.amazon.es/hz/fba/profitabilitycalculator/index?lang=es_ES"

COUNTRIES = ["ES", "IT", "DE", "FR"]

KNOWN_NON_REFERRAL = {"G200209150", "G201023020", "200612770", "GWYBC38TZGCUNRKW"}


def extract_euro_value(text: str) -> float:
    cleaned = text.replace("€", "").replace("\xa0", "").replace("\u00a0", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def select_country(page, country: str):
    """Selecciona el país en el kat-dropdown y espera a que el input esté listo."""
    page.evaluate("""
        const dd = document.querySelector('kat-dropdown');
        if (dd) dd.click();
    """)
    time.sleep(1.0)

    page.evaluate(f"""
        const options = document.querySelectorAll('kat-option');
        for (const opt of options) {{
            if (opt.getAttribute('value') === '{country}') {{
                opt.click();
                break;
            }}
        }}
    """)
    time.sleep(1.5)  # Dar tiempo a que la página se actualice tras cambiar de país

    # Esperar a que el input de búsqueda esté visible
    try:
        page.locator('input[type="text"]').first.wait_for(state="visible", timeout=8000)
    except PwTimeout:
        time.sleep(2)


def search_asin(page, asin: str):
    """Rellena el input de búsqueda y lanza la búsqueda."""
    search_input = page.locator('input[type="text"]').first
    try:
        search_input.wait_for(state="visible", timeout=8000)
    except PwTimeout:
        time.sleep(3)
    search_input.click(click_count=3)
    search_input.fill(asin)
    time.sleep(0.4)

    # Click en buscar via JS
    page.evaluate("""
        const btns = document.querySelectorAll('kat-button');
        for (const b of btns) {
            const lbl = (b.getAttribute('label') || '').toLowerCase();
            const type = b.getAttribute('type') || '';
            if (type === 'submit' || lbl.includes('buscar')) {
                b.click();
                const inner = b.shadowRoot?.querySelector('button');
                if (inner) inner.click();
                break;
            }
        }
    """)


def wait_for_results(page):
    """Espera a que aparezca la tarifa FBA en la página."""
    try:
        page.locator('kat-link[href*="G200209150"]').first.wait_for(state="visible", timeout=15000)
        time.sleep(0.5)
    except PwTimeout:
        time.sleep(3)


def extract_fees(page) -> dict:
    """Extrae referral, FBA y DST leyendo el DOM via JavaScript."""
    raw = page.evaluate("""
        () => {
            const results = [];
            const links = document.querySelectorAll('kat-link');
            for (const link of links) {
                const href = link.getAttribute('href') || '';
                const parent = link.parentElement;
                if (!parent) continue;
                const label = parent.querySelector('kat-label');
                if (!label) continue;
                // Intentar leer el valor desde el slot light-DOM o desde el atributo text
                const span = label.querySelector('span[part="label-text"]');
                const text = span ? span.textContent : (label.getAttribute('text') || '');
                results.push({ href, text: text.trim() });
            }
            return results;
        }
    """)

    fees = {"referral_fee": 0.0, "fba_fee": 0.0, "digital_services_fee": 0.0}
    referral_found = False

    for item in raw:
        href = item.get("href", "")
        text = item.get("text", "")
        if "€" not in text:
            continue
        value = extract_euro_value(text)

        if "G200209150" in href:
            fees["fba_fee"] = value
        elif href.endswith("ref_=referral") or "referral" in href.split("?")[0].split("/")[-1].lower():
            fees["digital_services_fee"] = value
        elif not any(k in href for k in KNOWN_NON_REFERRAL) and not referral_found:
            fees["referral_fee"] = value
            referral_found = True

    return fees


def update_cogs_in_supabase(asin: str, fba_es: float, fba_it: float, fba_de: float, fba_fr: float) -> int:
    if not SUPABASE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY no configurado en .env")
    url = f"{SUPABASE_URL}/rest/v1/cogs?ASIN=eq.{asin}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = {"fba_fee_es": fba_es, "fba_fee_it": fba_it, "fba_fee_de": fba_de, "fba_fee_fr": fba_fr}
    r = httpx.patch(url, headers=headers, json=payload)
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Supabase error {r.status_code}: {r.text[:200]}")
    return len(r.json()) if r.status_code == 200 else 0


def scrape_all_countries(page, asin: str) -> dict:
    """Para un ASIN, obtiene fees de los 4 países usando el dropdown."""
    result = {}
    for country in COUNTRIES:
        print(f"    [{country}] ", end="", flush=True)
        for attempt in range(2):
            select_country(page, country)
            search_asin(page, asin)
            wait_for_results(page)
            fees = extract_fees(page)
            if fees["fba_fee"] > 0 or attempt == 1:
                result[country] = fees
                print(f"Ref {fees['referral_fee']:.2f}€  FBA {fees['fba_fee']:.2f}€  DST {fees['digital_services_fee']:.2f}€")
                break
            print(f"sin resultados, reintentando... ", end="", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="Scrape FBA fees y actualiza COGS en Supabase")
    parser.add_argument("asins", nargs="*", help="ASINs a procesar")
    parser.add_argument("--file", help="Fichero con ASINs (uno por línea)")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar, no actualizar Supabase")
    args = parser.parse_args()

    asins = list(args.asins)
    if args.file:
        asins += [l.strip() for l in open(args.file) if l.strip()]
    asins = list(dict.fromkeys(asins))

    if not asins:
        parser.error("Proporciona al menos un ASIN")

    print(f"Procesando {len(asins)} ASIN(s) en modo headed...\n")
    all_results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            locale="es-ES",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        # Navegar una sola vez a la calculadora
        page.goto(CALCULATOR_URL, wait_until="domcontentloaded")
        time.sleep(2)

        # Continuar como invitado
        try:
            page.wait_for_selector('kat-button[data-testid="continue-btn"]', timeout=8000)
            page.evaluate("""
                const btn = document.querySelector('kat-button[data-testid="continue-btn"]');
                if (btn) { btn.click(); btn.shadowRoot?.querySelector('button')?.click(); }
            """)
            page.wait_for_load_state("networkidle")
            print("Sesión iniciada como invitado.\n")
        except PwTimeout:
            print("(ya en modo invitado)\n")

        for i, asin in enumerate(asins, 1):
            print(f"[{i}/{len(asins)}] {asin}")
            data = scrape_all_countries(page, asin)
            data["asin"] = asin

            fba_es = data.get("ES", {}).get("fba_fee", 0.0)
            fba_it = data.get("IT", {}).get("fba_fee", 0.0)
            fba_de = data.get("DE", {}).get("fba_fee", 0.0)
            fba_fr = data.get("FR", {}).get("fba_fee", 0.0)

            if not args.dry_run:
                try:
                    rows = update_cogs_in_supabase(asin, fba_es, fba_it, fba_de, fba_fr)
                    print(f"    → Supabase actualizado ({rows} fila(s))\n")
                except Exception as e:
                    print(f"    → ERROR Supabase: {e}\n")
            else:
                print("    → [dry-run] no se actualiza Supabase\n")

            all_results.append(data)

        browser.close()

    print("\n=== RESUMEN ===")
    print(f"{'ASIN':<15} {'FBA ES':>8} {'FBA IT':>8} {'FBA DE':>8} {'FBA FR':>8}")
    print("-" * 55)
    for d in all_results:
        print(
            f"{d['asin']:<15} "
            f"{d.get('ES', {}).get('fba_fee', 0):>7.2f}€ "
            f"{d.get('IT', {}).get('fba_fee', 0):>7.2f}€ "
            f"{d.get('DE', {}).get('fba_fee', 0):>7.2f}€ "
            f"{d.get('FR', {}).get('fba_fee', 0):>7.2f}€"
        )


if __name__ == "__main__":
    main()
