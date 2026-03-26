#!/usr/bin/env python3
"""
Scraper de tarifas FBA/Referral de la calculadora de Amazon Seller Central.
Usa Playwright para automatizar la navegación como invitado.

Uso:
  python scripts/amazon_fees_scraper.py B0DWT9QKFF
  python scripts/amazon_fees_scraper.py B0DWT9QKFF --countries ES,IT,DE,FR
  python scripts/amazon_fees_scraper.py B0DWT9QKFF --json
"""

import argparse
import json
import sys
import time
from playwright.sync_api import sync_playwright, TimeoutError as PwTimeout

CALCULATOR_URL = "https://sellercentral.amazon.{tld}/hz/fba/profitabilitycalculator/index?lang={lang}"

COUNTRY_CONFIG = {
    "ES": {"tld": "es", "lang": "es_ES", "label": "ES"},
    "IT": {"tld": "it", "lang": "it_IT", "label": "IT"},
    "DE": {"tld": "de", "lang": "de_DE", "label": "DE"},
    "FR": {"tld": "fr", "lang": "fr_FR", "label": "FR"},
}


def extract_euro_value(text: str) -> float:
    """Extrae valor numérico de textos como '3,46\xa0€' o '3.46 €'."""
    cleaned = text.replace("€", "").replace("\xa0", "").replace("\u00a0", "").strip()
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def scrape_fees_for_country(page, asin: str, country: str, debug: bool = False) -> dict:
    """Busca un ASIN en la calculadora y extrae las tarifas para un país."""
    cfg = COUNTRY_CONFIG[country]
    url = CALCULATOR_URL.format(tld=cfg["tld"], lang=cfg["lang"])

    page.goto(url, wait_until="networkidle")

    # --- Continuar como invitado (Shadow DOM → JS click) ---
    try:
        page.wait_for_selector('kat-button[data-testid="continue-btn"]', timeout=8000)
        page.evaluate("""
            const btn = document.querySelector('kat-button[data-testid="continue-btn"]');
            if (btn) { btn.click(); btn.shadowRoot?.querySelector('button')?.click(); }
        """)
        page.wait_for_load_state("networkidle")
    except PwTimeout:
        pass

    # --- Escribir ASIN y buscar ---
    search_input = page.locator('input[placeholder*="ASIN"], input[placeholder*="asin"], input[placeholder*="SKU"]').first
    search_input.wait_for(state="visible", timeout=8000)
    search_input.fill("")
    search_input.fill(asin)
    time.sleep(0.5)

    page.evaluate("""
        const btns = document.querySelectorAll('kat-button');
        for (const b of btns) {
            if (b.getAttribute('type') === 'submit' || (b.label || '').match(/buscar|search|cerca|suchen|rechercher/i)) {
                b.click(); b.shadowRoot?.querySelector('button')?.click(); break;
            }
        }
    """)

    # --- Esperar a que carguen los resultados ---
    # Esperamos a que aparezca la tarifa de gestión logística (FBA) como señal de carga completa
    try:
        page.locator('kat-link[href*="G200209150"]').first.wait_for(state="visible", timeout=15000)
    except PwTimeout:
        # Puede que el producto no exista en este marketplace, esperamos un poco por si acaso
        time.sleep(3)
    time.sleep(1)

    # --- Extraer tarifas ---
    result = {
        "country": country,
        "asin": asin,
        "referral_fee": 0.0,
        "fba_fee": 0.0,
        "digital_services_fee": 0.0,
    }

    # Extraer tarifas usando hrefs de ayuda
    # - FBA: href contiene "G200209150" (consistente en todos los países)
    # - DST: href contiene "referral" (sin ser un help page de referral fees)
    # - Referral: primera fee link con valor € que no sea FBA, DST, packaging ni help page
    KNOWN_NON_REFERRAL = {"G200209150", "G201023020", "200612770", "GWYBC38TZGCUNRKW"}

    fee_links = page.locator("kat-link")
    fee_count = fee_links.count()

    referral_found = False
    for i in range(fee_count):
        link = fee_links.nth(i)
        href = link.get_attribute("href") or ""
        label = link.get_attribute("label") or ""

        parent = link.locator("..")
        value_label = parent.locator("kat-label")
        if value_label.count() == 0:
            continue

        value_text = value_label.first.get_attribute("text") or ""
        if "€" not in value_text:
            continue

        value = extract_euro_value(value_text)

        if debug:
            print(f"  [{i}] label='{label}' href='{href}' value='{value_text}' -> {value}")

        if "G200209150" in href:
            result["fba_fee"] = value
        elif href.endswith("ref_=referral") or "referral" in href.split("?")[0].split("/")[-1].lower():
            result["digital_services_fee"] = value
        elif not any(k in href for k in KNOWN_NON_REFERRAL) and not referral_found:
            # Primera fee con valor € que no sea conocida = referral fee
            result["referral_fee"] = value
            referral_found = True

    return result


def main():
    parser = argparse.ArgumentParser(description="Scraper de tarifas FBA de Amazon")
    parser.add_argument("asin", help="ASIN del producto")
    parser.add_argument(
        "--countries",
        default="ES,IT,DE,FR",
        help="Países separados por coma (default: ES,IT,DE,FR)",
    )
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON")
    parser.add_argument("--headed", action="store_true", help="Mostrar el navegador (debug)")
    parser.add_argument("--debug", action="store_true", help="Mostrar detalle de cada fee encontrado")
    args = parser.parse_args()

    countries = [c.strip().upper() for c in args.countries.split(",")]
    invalid = [c for c in countries if c not in COUNTRY_CONFIG]
    if invalid:
        print(f"Error: países no soportados: {invalid}. Usa: {list(COUNTRY_CONFIG.keys())}")
        sys.exit(1)

    results = []

    with sync_playwright() as p:
        launch_args = [] if args.headed else ["--window-position=-32000,-32000", "--window-size=1280,900"]
        browser = p.chromium.launch(headless=False, args=launch_args)
        context = browser.new_context(
            locale="es-ES",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        for country in countries:
            for attempt in range(2):
                try:
                    if not args.json:
                        label = f"(retry) " if attempt > 0 else ""
                        print(f"{label}Consultando {args.asin} en {country}...", end=" ", flush=True)
                    fees = scrape_fees_for_country(page, args.asin, country, debug=args.debug)
                    # Si no encontró FBA, reintentar una vez
                    if fees["fba_fee"] == 0 and attempt == 0:
                        if not args.json:
                            print("sin resultados, reintentando...")
                        continue
                    results.append(fees)
                    if not args.json:
                        print(
                            f"Referral: {fees['referral_fee']:.2f}€  "
                            f"FBA: {fees['fba_fee']:.2f}€  "
                            f"DST: {fees['digital_services_fee']:.2f}€"
                        )
                    break
                except Exception as e:
                    if attempt == 1 or not isinstance(e, (PwTimeout, Exception)):
                        if not args.json:
                            print(f"ERROR: {e}")
                        results.append({
                            "country": country,
                            "asin": args.asin,
                            "error": str(e),
                        })
                        break

        browser.close()

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
    elif results:
        print("\n--- Resumen ---")
        print(f"{'País':<6} {'Referral':>10} {'FBA':>10} {'DST':>10} {'Total':>10}")
        print("-" * 50)
        for r in results:
            if "error" in r:
                print(f"{r['country']:<6} ERROR: {r['error']}")
            else:
                total = r["referral_fee"] + r["fba_fee"] + r["digital_services_fee"]
                print(
                    f"{r['country']:<6} "
                    f"{r['referral_fee']:>9.2f}€ "
                    f"{r['fba_fee']:>9.2f}€ "
                    f"{r['digital_services_fee']:>9.2f}€ "
                    f"{total:>9.2f}€"
                )


if __name__ == "__main__":
    main()
