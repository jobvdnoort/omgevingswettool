# Omgevingswet GIS Extractor

Eerste MVP van een Nederlandstalige Streamlit GIS-webtool. Upload een onderzoeksgebied en zoek rakende documenten via de actuele DSO Omgevingsinformatie Ontsluiten v2 API. Voor OW-documenten worden expliciet gevonden geometrie-identificaties via Presenteren v8 en Geometrie Opvragen v1 opgehaald in EPSG:28992. Resultaten worden als GeoPackage en ZIP aangeboden.

## Mogelijkheden

- GeoJSON, GeoPackage en Shapefile als ZIP; Polygon/MultiPolygon, herstel van ongeldige geometrieën, CRS-validatie en transformatie naar RD.
- Geldigheidsdatum, toekomstige documenten, regelgevingfilter, limiet en debugoptie.
- Retry/backoff voor tijdelijke API-fouten, paginering, deduplicatie, ruwe responses en Nederlandstalige waarschuwingen.
- Lagen voor zoekgebied, inhoudelijke punten/lijnen/vlakken, metadata en relaties.

## Beperkingen

IMRO-documenten worden als metadata opgenomen, maar IMRO-detailgeometrieën zijn niet geïmplementeerd. Documentcontouren worden nog niet uit elk mogelijk ontsluitingsresponse-formaat genormaliseerd. Zie `TODO.md`. De API-respons kan evolueren.

## API's

Productie:

- Ontsluiten v2: `https://service.omgevingswet.overheid.nl/publiek/omgevingsinformatie/api/ontsluiten/v2`
- Presenteren v8: `https://service.omgevingswet.overheid.nl/publiek/omgevingsdocumenten/api/presenteren/v8`
- Geometrie Opvragen v1: `https://service.omgevingswet.overheid.nl/publiek/omgevingsdocumenten/api/geometrieopvragen/v1`

Deze URL's en requestvormen zijn gecontroleerd tegen de actuele OpenAPI-specificaties op 2 oktober 2026. Voor alle calls is een DSO API-key nodig; die wordt als `x-api-key` verstuurd en nooit gelogd.

## Installatie en starten

Vereist Python 3.12:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DSO_API_KEY='jouw sleutel'
streamlit run streamlit_app.py
```

Lokaal kan de sleutel ook in `.streamlit/secrets.toml` staan:

```toml
DSO_API_KEY = "jouw sleutel"
```

Commit nooit `.env` of `secrets.toml`.

## Streamlit Community Cloud

1. Push deze repository naar GitHub.
2. Kies `streamlit_app.py` als main file.
3. Voeg in Advanced settings bij Secrets `DSO_API_KEY = "..."` toe.
4. Deploy en controleer een kleine testzone.

## Uitvoer

De ZIP bevat `01_documenten.gpkg`, `02_inhoudelijke_geometrie.gpkg`, `metadata.json`, `export_log.csv` en `raw/` met ruwe responses. GeoPackage is open en portable. ArcGIS Pro kan het direct openen en naar File Geodatabase converteren; directe GDB-uitvoer is in dit MVP niet geactiveerd.

Resultaten uit DSO-API's zijn informatief en geen vervanging voor juridische beoordeling.
