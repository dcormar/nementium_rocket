# Actualizar tarifas FBA desde la calculadora de Amazon

Script: `scripts/update_fba_fees.py`
Scrape automáticamente las tarifas FBA de ES, IT, DE y FR desde la calculadora de Amazon Seller Central y actualiza la tabla `cogs` en Supabase.

---

## Requisitos

```bash
pip install playwright httpx python-dotenv
playwright install chromium
```

El fichero `.env` debe tener `SUPABASE_SERVICE_ROLE_KEY` (si quieres que el script actualice Supabase directamente). Si no, puedes usar el modo `--dry-run` y actualizar vía MCP de Supabase manualmente.

---

## Uso básico

### Un ASIN
```bash
python scripts/update_fba_fees.py B0DWT9QKFF
```

### Varios ASINs a la vez
```bash
python scripts/update_fba_fees.py B0DWT9QKFF B0G167B2HQ B0D8LFS7Y2
```

### Solo ver los valores sin actualizar Supabase
```bash
python scripts/update_fba_fees.py B0DWT9QKFF --dry-run
```

---

## Cómo funciona

1. Abre Chrome (ventana visible) y navega a la calculadora de Amazon ES
2. Continúa como invitado automáticamente
3. Para cada país (ES → IT → DE → FR): selecciona el país en el dropdown, busca el ASIN y extrae las tarifas
4. Actualiza `fba_fee_es`, `fba_fee_it`, `fba_fee_de`, `fba_fee_fr` en la tabla `cogs`

> **Nota:** El navegador se abre en pantalla. Es normal que veas cómo navega solo. No lo cierres hasta que termine.

---

## Qué hace con los valores a 0

Si la calculadora no devuelve tarifa para un país (el ASIN no está listado en ese marketplace), el valor queda a `0`. El backend ya tiene lógica de **fallback a ES** para países sin tarifa configurada.

---

## Copiar valores de un ASIN de referencia

Si tienes un ASIN nuevo que es variante (mismo tamaño/peso) de otro ya configurado, es más rápido copiar los valores directamente en Supabase. Ejecuta esto en el MCP o en el SQL editor de Supabase:

```sql
UPDATE cogs
SET
  fba_fee_es = s.fba_fee_es,
  fba_fee_it = s.fba_fee_it,
  fba_fee_de = s.fba_fee_de,
  fba_fee_fr = s.fba_fee_fr
FROM (
  SELECT fba_fee_es, fba_fee_it, fba_fee_de, fba_fee_fr
  FROM cogs
  WHERE "ASIN" = 'ASIN_REFERENCIA'
  LIMIT 1
) s
WHERE "ASIN" IN ('NUEVO_ASIN_1', 'NUEVO_ASIN_2');
```

Sustituye `ASIN_REFERENCIA` por el ASIN con los valores correctos y añade los ASINs destino.

---

## Solución de problemas

| Problema | Causa | Solución |
|---|---|---|
| Todos los valores a 0 | El ASIN no está en esos marketplaces | Normal. El fallback a ES funciona automáticamente |
| "sin resultados, reintentando..." | Timing de la página | Normal. El script reintenta automáticamente |
| Error de timeout | La página tardó demasiado | Vuelve a ejecutar solo ese ASIN |
| `SUPABASE_SERVICE_ROLE_KEY no configurado` | Falta la clave en `.env` | Usa `--dry-run` y actualiza vía MCP manualmente |
